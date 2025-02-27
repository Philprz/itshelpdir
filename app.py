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
    # Vérification de base
    status = "ok"
    checks = {
        "database": True,
        "chatbot": chatbot is not None,
        "openai": True,
        "qdrant": True
    }
    
    # Stats de base
    health_stats = {
        "uptime": time.time() - app.config.get('start_time', time.time()),
        "requests": stats["requests_total"],
        "errors": stats["error_count"],
        "avg_response_time": stats["avg_response_time"]
    }
    
    try:
        # Vérification de l'état du cache si disponible
        if hasattr(global_cache, 'get_stats'):
            cache_stats = asyncio.run(global_cache.get_stats())
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
    
    if not chatbot:
        emit('response', {'message': 'Le chatbot n\'est pas initialisé', 'type': 'error'})
        return
    
    user_id = data.get('user_id', request.sid)
    message = data.get('message', '')
    
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
    global chatbot
    app.config['start_time'] = time.time()
    
    try:
        # Utilisation de la boucle d'événements existante
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Créer une nouvelle boucle si celle-ci est déjà en cours d'exécution
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            new_loop.run_until_complete(init_db())
            new_loop.run_until_complete(search_factory.initialize())
            new_loop.close()
        else:
            # Utiliser la boucle existante
            loop.run_until_complete(init_db())
            loop.run_until_complete(search_factory.initialize())
        
        logger.info("Base de données et factory de recherche initialisés")
        
        # Initialisation du chatbot
        chatbot = ChatBot(
            openai_key=os.getenv('OPENAI_API_KEY'),
            qdrant_url=os.getenv('QDRANT_URL'),
            qdrant_api_key=os.getenv('QDRANT_API_KEY')
        )
        logger.info("Chatbot initialisé")
        
        # Initialisation du cache global
        if hasattr(global_cache, 'start_cleanup_task'):
            asyncio.run(global_cache.start_cleanup_task())
            logger.info("Tâche de nettoyage du cache démarrée")
        
    except Exception as e:
        logger.critical(f"Erreur critique d'initialisation: {str(e)}\n{traceback.format_exc()}")
        raise
# Utiliser before_request comme alternative
@app.before_request
def before_request_func():
    global _is_initialized
    if not _is_initialized:
        initialize()
        _is_initialized = True
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