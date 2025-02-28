# Remplacer app.py

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
import time
import traceback

from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from dotenv import load_dotenv

# Imports depuis le code optimisé
from base_de_donnees import SessionLocal, Conversation, init_db
from chatbot import ChatBot
from configuration import logger, global_cache
from search_factory import search_factory

# Variables globales pour le suivi de l'initialisation
_is_initialized = False
_initialization_started = False
# Chargement des variables d'environnement
load_dotenv()

# Configuration de Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'its_help_secret_key')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialisation du chatbot
chatbot = None

# Statistiques et monitoring
stats = {
    "requests_total": 0,
    "error_count": 0,
    "avg_response_time": 0,
    "last_errors": []
}

@app.route('/')
def index():
    """Page d'accueil du chatbot"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Endpoint de vérification de santé pour Render"""
    # Vérification de l'état d'initialisation
    global _is_initialized, _initialization_started
    
    if not _initialization_started:
        status = "starting"
    elif not _is_initialized:
        status = "initializing"
    else:
        status = "ok"
    
    # Stats de base
    health_stats = {
        "uptime": time.time() - app.config.get('start_time', time.time()),
        "requests": stats.get("requests_total", 0),
        "errors": stats.get("error_count", 0),
        "avg_response_time": stats.get("avg_response_time", 0),
        "initialization_status": status
    }
    
    # Vérification plus détaillée seulement si l'initialisation est terminée
    checks = {
        "database": _is_initialized,
        "chatbot": chatbot is not None,
        "openai": _is_initialized,
        "qdrant": _is_initialized
    }
    
    try:
        # Vérification de l'état du cache si disponible et initialisé
        if _is_initialized and hasattr(global_cache, 'get_stats'):
            # Utilisation d'un thread pour l'opération async
            import threading
            cache_stats = {}
            
            def get_cache_stats():
                nonlocal cache_stats
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    cache_stats = loop.run_until_complete(global_cache.get_stats())
                finally:
                    loop.close()
            
            # Exécuter de manière non bloquante avec timeout
            stats_thread = threading.Thread(target=get_cache_stats)
            stats_thread.daemon = True
            stats_thread.start()
            stats_thread.join(timeout=2.0)  # Attendre max 2 secondes
            
            if cache_stats:
                health_stats["cache"] = cache_stats
    except:
        checks["cache"] = False
    
    return jsonify({
        "status": status, 
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
        "stats": health_stats
    })

@socketio.on('connect')
def handle_connect():
    """Gestion de la connexion SocketIO"""
    logger.info(f"Client connecté: {request.sid}")
    emit('response', {'message': 'Connexion établie avec ITS Help'})

@socketio.on('disconnect')
def handle_disconnect():
    """Gestion de la déconnexion SocketIO"""
    logger.info(f"Client déconnecté: {request.sid}")

@socketio.on('message')
def handle_message(data):
    """Gestion des messages entrants via SocketIO"""
    global chatbot, stats
    stats["requests_total"] += 1
    
    user_id = data.get('user_id', request.sid)
    message = data.get('message', '')
    
    # Si le chatbot n'est pas encore initialisé
    if not chatbot:
        # Vérifier si l'initialisation est en cours
        if _initialization_started and not _is_initialized:
            emit('response', {
                'message': 'Le service est en cours d\'initialisation, veuillez patienter quelques instants...',
                'type': 'status',
                'initializing': True
            })
        else:
            # Problème d'initialisation
            emit('response', {
                'message': 'Le chatbot n\'est pas initialisé correctement. Veuillez contacter l\'administrateur.',
                'type': 'error'
            })
        return
    
    # Envoi d'un accusé de réception
    emit('response', {'message': 'Message reçu, traitement en cours...', 'type': 'status'})
    
    # Traitement asynchrone du message
    socketio.start_background_task(process_message, user_id, message)

async def process_message(user_id, message):
    """Traite le message de manière asynchrone avec gestion améliorée des erreurs"""
    start_time = time.monotonic()
    global stats
    
    try:
        # Gestion de la conversation
        async with SessionLocal() as db:
            # Récupération ou création de la conversation
            result = await db.execute(f"SELECT * FROM conversations WHERE user_id = '{user_id}'")
            conversation = result.fetchone()
            
            if not conversation:
                # Création d'une nouvelle conversation
                await db.execute(f"""
                    INSERT INTO conversations (user_id, context, last_updated) 
                    VALUES ('{user_id}', '{"{}"}', '{datetime.now(timezone.utc)}')
                """)
                await db.commit()
                result = await db.execute(f"SELECT * FROM conversations WHERE user_id = '{user_id}'")
                conversation = result.fetchone()
            
            # Traitement du message par le chatbot
            response = await chatbot.process_web_message(message, conversation, user_id)
            
            # Mise à jour des statistiques
            elapsed_time = time.monotonic() - start_time
            stats["avg_response_time"] = (stats["avg_response_time"] * (stats["requests_total"] - 1) + elapsed_time) / stats["requests_total"]
            
            # Mise à jour de la dernière interaction
            await db.execute(f"""
                UPDATE conversations 
                SET last_interaction = '{datetime.now(timezone.utc)}' 
                WHERE user_id = '{user_id}'
            """)
            await db.commit()
            
            # Envoi de la réponse via SocketIO
            response_size = len(json.dumps(response)) if isinstance(response, dict) else 0
            logger.info(f"Réponse envoyée à {user_id} en {elapsed_time:.2f}s (taille: {response_size/1024:.1f} KB)")
            socketio.emit('response', {
                'message': response.get('text', 'Pas de réponse'),
                'blocks': response.get('blocks', []),
                'type': 'message',
                'response_time': round(elapsed_time, 2)
            }, room=user_id)
            
    except Exception as e:
        # Journalisation détaillée de l'erreur
        error_details = {
            "timestamp": datetime.now().isoformat(),
            "message": str(e),
            "traceback": traceback.format_exc()
        }
        
        logger.error(f"Erreur traitement message: {str(e)}\n{traceback.format_exc()}")
        stats["error_count"] += 1
        
        # Conservation des 10 dernières erreurs
        stats["last_errors"].append(error_details)
        if len(stats["last_errors"]) > 10:
            stats["last_errors"].pop(0)
            
        # Envoi d'un message d'erreur formaté
        socketio.emit('response', {
            'message': f"Erreur lors du traitement: {str(e)}",
            'type': 'error',
            'error_id': stats["error_count"]
        }, room=user_id)

# Définir un drapeau global
_is_initialized = False
def initialize():
    """Initialisation améliorée des composants au démarrage"""
    global chatbot, _is_initialized
    
    # Éviter les initialisations multiples
    if _is_initialized:
        return
        
    app.config['start_time'] = time.time()
    
    try:
        # Utiliser l'event loop existant au lieu d'en créer un nouveau
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Pour les environnements où la boucle est déjà en cours d'exécution
            # comme avec Gunicorn+gevent, nous utilisons une approche non-bloquante
            _is_initialized = True  # Marquer comme initialisé pour éviter les appels ultérieurs
            
            # Lancer un thread séparé pour l'initialisation asynchrone
            import threading
            def async_init():
                # Créer une nouvelle boucle pour ce thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    # Exécuter les initialisations
                    new_loop.run_until_complete(init_db())
                    new_loop.run_until_complete(search_factory.initialize())
                    
                    if hasattr(global_cache, 'start_cleanup_task'):
                        new_loop.run_until_complete(global_cache.start_cleanup_task())
                        
                    # Initialiser le chatbot (opération synchrone)
                    global chatbot
                    chatbot = ChatBot(
                        openai_key=os.getenv('OPENAI_API_KEY'),
                        qdrant_url=os.getenv('QDRANT_URL'),
                        qdrant_api_key=os.getenv('QDRANT_API_KEY')
                    )
                    logger.info("Initialisation complète effectuée avec succès")
                except Exception as e:
                    logger.critical(f"Erreur dans le thread d'initialisation: {str(e)}")
                finally:
                    new_loop.close()
            
            # Démarrer le thread d'initialisation en arrière-plan
            init_thread = threading.Thread(target=async_init)
            init_thread.daemon = True
            init_thread.start()
            
            # Retourner immédiatement pour ne pas bloquer les requêtes
            logger.info("Initialisation démarrée en arrière-plan")
            return
        else:
            # Pour les environnements où nous pouvons exécuter directement (rare avec Flask+Gunicorn)
            loop.run_until_complete(init_db())
            loop.run_until_complete(search_factory.initialize())
            
            # Initialisation du chatbot
            chatbot = ChatBot(
                openai_key=os.getenv('OPENAI_API_KEY'),
                qdrant_url=os.getenv('QDRANT_URL'),
                qdrant_api_key=os.getenv('QDRANT_API_KEY')
            )
            logger.info("Chatbot initialisé")
            
            # Initialisation du cache global
            if hasattr(global_cache, 'start_cleanup_task'):
                loop.run_until_complete(global_cache.start_cleanup_task())
                logger.info("Tâche de nettoyage du cache démarrée")
            
            _is_initialized = True
        
    except Exception as e:
        logger.critical(f"Erreur critique d'initialisation: {str(e)}\n{traceback.format_exc()}")
        raise
# Utiliser before_request comme alternative
@app.before_request
def before_request_func():
    global _is_initialized, _initialization_started

    # Si déjà initialisé, continuer normalement
    if _is_initialized and chatbot is not None:
        return None
        
    # Si l'initialisation n'a pas encore commencé
    if not _initialization_started:
        _initialization_started = True
        initialize()
        
    # Si l'initialisation est en cours mais pas terminée
    if not _is_initialized or chatbot is None:
        if request.path == '/health':
            # Permettre aux health checks de passer
            return None
        else:
            # Pour les autres routes, indiquer que le service est en cours d'initialisation
            return jsonify({
                "status": "initializing",
                "message": "Le service est en cours d'initialisation, veuillez réessayer dans quelques instants"
            }), 503  # Service Unavailable
# Routes pour la gestion de l'interface utilisateur (pourraient être ajoutées)
@app.route('/api/stats')
def get_stats():
    """API pour récupérer les statistiques d'utilisation"""
    return jsonify(stats)

@app.route('/api/cache/stats')
def get_cache_stats():
    """API pour récupérer les statistiques du cache"""
    if hasattr(global_cache, 'get_stats'):
        return jsonify(asyncio.run(global_cache.get_stats()))
    return jsonify({"error": "Cache stats not available"}), 404

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """API pour vider le cache"""
    if hasattr(global_cache, 'invalidate'):
        asyncio.run(global_cache.invalidate())
        return jsonify({"status": "Cache cleared"}), 200
    return jsonify({"error": "Cache control not available"}), 404

@app.route('/api/embeddings/stats')
def get_embedding_stats():
    """API pour récupérer les statistiques d'embedding"""
    if chatbot and hasattr(chatbot.embedding_service, 'get_stats'):
        return jsonify(chatbot.embedding_service.get_stats())
    return jsonify({"error": "Embedding stats not available"}), 404

if __name__ == '__main__':
    # Configuration avancée du logging
    level = logging.INFO
    if os.getenv('LOG_LEVEL', '').upper() == 'DEBUG':
        level = logging.DEBUG
    elif os.getenv('LOG_LEVEL', '').upper() == 'WARNING':
        level = logging.WARNING
        
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Configuration des loggers spécifiques
    for logger_name in ['werkzeug', 'engineio', 'socketio']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    # Démarrage du serveur
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Démarrage du serveur sur le port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=True)