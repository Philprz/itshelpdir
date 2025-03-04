# Remplacer app.py

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
import time
import traceback
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, current_app
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
_db_initialized = False
_search_factory_initialized = False
_cache_initialized = False

# Chargement des variables d'environnement
load_dotenv()

# Configuration de Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'its_help_secret_key')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Initialisation du chatbot
chatbot = None

# Statistiques et monitoring
stats = {
    "requests_total": 0,
    "error_count": 0,
    "avg_response_time": 0,
    "last_errors": []
}

# Décorateur pour les routes asynchrones
def async_route(f):
    """Décorateur pour les routes asynchrones"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Création d'une nouvelle boucle événementielle
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Exécution de la fonction asynchrone
            result = loop.run_until_complete(f(*args, **kwargs))
            return result
        finally:
            # Fermeture de la boucle événementielle
            loop.close()
    return decorated_function

@app.route('/')
def index():
    """Page d'accueil du chatbot"""
    return render_template('index.html')


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

# Correction pour la fonction process_message dans app.py

async def process_message(user_id, message):
    """Traite le message de manière asynchrone avec gestion améliorée des erreurs"""
    start_time = time.monotonic()
    global stats
    
    try:
        # Création d'une session dédiée à la conversation
        async with SessionLocal() as db:
            # Récupération ou création de la conversation
            # Utilisation de paramètres de requête pour éviter les injections SQL
            result = await db.execute(
                "SELECT * FROM conversations WHERE user_id = :user_id",
                {"user_id": user_id}
            )
            conversation = result.fetchone()
        
            if not conversation:
                # Création d'une nouvelle conversation avec paramètres sécurisés
                current_time = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    """
                    INSERT INTO conversations (user_id, context, last_updated) 
                    VALUES (:user_id, :context, :updated)
                    """,
                    {
                        "user_id": user_id,
                        "context": "{}",
                        "updated": current_time
                    }
                )
                await db.commit()
                
                # Récupération de la conversation nouvellement créée
                result = await db.execute(
                    "SELECT * FROM conversations WHERE user_id = :user_id",
                    {"user_id": user_id}
                )
                conversation = result.fetchone()
        
            # Traitement du message par le chatbot
            response = await chatbot.process_web_message(message, conversation, user_id)
        
            # Mise à jour des statistiques
            elapsed_time = time.monotonic() - start_time
            stats["avg_response_time"] = (stats["avg_response_time"] * (stats["requests_total"] - 1) + elapsed_time) / stats["requests_total"]
        
            # Mise à jour de la dernière interaction avec paramètres sécurisés
            current_time = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """
                UPDATE conversations 
                SET last_interaction = :interaction_time
                WHERE user_id = :user_id
                """,
                {
                    "interaction_time": current_time,
                    "user_id": user_id
                }
            )
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
def ensure_initialization():
    """S'assure que l'initialisation est lancée dans le contexte de l'application"""
    global _initialization_started
    if not _initialization_started:
        initialize()

def initialize():
    """Initialisation progressive des composants au démarrage"""
    global chatbot, _is_initialized, _initialization_started
    
    # Éviter les initialisations multiples
    if _is_initialized:
        return
        
    # S'assurer qu'on est dans un contexte d'application Flask
    if not current_app:  # Si nous sommes hors du contexte d'application
        with app.app_context():  # Créer un contexte d'application
            _do_initialize()
    else:
        _do_initialize()
        
def _do_initialize():
    """Effectue l'initialisation réelle dans un contexte d'application"""
    global chatbot, _is_initialized, _initialization_started
    
    app.config['start_time'] = time.time()
    _initialization_started = True
    
    # Lancer un thread séparé pour l'initialisation asynchrone
    import threading
    def async_init():
        global _db_initialized, _search_factory_initialized, _cache_initialized, _is_initialized, chatbot
        
        # Créer une nouvelle boucle pour ce thread
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        
        try:
            # Utiliser le contexte de l'application pour l'initialisation
            with app.app_context():
                # Initialisation de la base de données
                try:
                    new_loop.run_until_complete(asyncio.wait_for(init_db(), timeout=15.0))
                    _db_initialized = True
                    logger.info("Base de données initialisée avec succès")
                except Exception as e:
                    logger.error(f"Erreur lors de l'initialisation de la base de données: {str(e)}")
                
                # Initialisation du search factory
                try:
                    new_loop.run_until_complete(asyncio.wait_for(search_factory.initialize(), timeout=15.0))
                    _search_factory_initialized = True
                    logger.info("Search factory initialisé avec succès")
                except Exception as e:
                    logger.error(f"Erreur lors de l'initialisation du search factory: {str(e)}")
                
                # Initialiser le chatbot seulement si les composants essentiels sont prêts
                if _db_initialized and _search_factory_initialized:
                    try:
                        chatbot = ChatBot(
                            openai_key=os.getenv('OPENAI_API_KEY'),
                            qdrant_url=os.getenv('QDRANT_URL'),
                            qdrant_api_key=os.getenv('QDRANT_API_KEY')
                        )
                        # L'initialisation du cache se fera plus tard, sur demande
                        _cache_initialized = True
                        _is_initialized = True
                        logger.info("Chatbot initialisé avec succès")
                    except Exception as e:
                        logger.critical(f"Erreur initialisation chatbot: {str(e)}")
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

@app.before_request
def before_request_func():
    global _is_initialized, _initialization_started, chatbot
    global _db_initialized, _search_factory_initialized

    # Pour les health checks, permettre l'accès même pendant l'initialisation
    if request.path == '/health':
        return None
        
    # Si déjà initialisé, continuer normalement
    if _is_initialized and chatbot is not None:
        return None
        
    # Si l'initialisation n'a pas encore commencé, la démarrer
    if not _initialization_started:
        with app.app_context():
            initialize()
        return jsonify({
            "status": "starting",
            "message": "Le service démarre, veuillez réessayer dans quelques instants"
        }), 503  # Service Unavailable
    
    # Tentative d'initialisation tardive du chatbot si les composants essentiels sont prêts
    if _db_initialized and _search_factory_initialized and not _is_initialized:
        try:
            chatbot = ChatBot(
                openai_key=os.getenv('OPENAI_API_KEY'),
                qdrant_url=os.getenv('QDRANT_URL'),
                qdrant_api_key=os.getenv('QDRANT_API_KEY')
            )
            _is_initialized = True
            logger.info("Chatbot initialisé avec succès (late init)")
            return None
        except Exception as e:
            logger.error(f"Erreur initialisation tardive du chatbot: {str(e)}")
    
    # Pour les autres routes, renvoyer un statut d'initialisation détaillé
    components = {
        "database": _db_initialized,
        "search_factory": _search_factory_initialized,
        "cache": _cache_initialized
    }
    
    return jsonify({
        "status": "initializing",
        "message": "Le service est en cours d'initialisation, veuillez réessayer dans quelques instants",
        "components": components
    }), 503  # Service Unavailable
# Décorateur de timeout
def timeout_handler(seconds=2, default_response=None):
    """Décorateur pour ajouter un timeout aux routes Flask"""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def wrapped(*args, **kwargs):
            from threading import Thread
            import queue
            
            result_queue = queue.Queue()

            def target():
                try:
                    result_queue.put(f(*args, **kwargs))
                except Exception as e:
                    logger.error(f"Erreur dans route avec timeout: {str(e)}")
                    result_queue.put(jsonify({
                        "status": "error",
                        "message": f"Erreur interne: {str(e)}"
                    }), 500)
            
            thread = Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout=seconds)

            if thread.is_alive():
                logger.warning(f"Timeout de {seconds}s atteint pour {f.__name__}")
                return jsonify({
                    "status": "timeout",
                    "message": f"La requête a pris plus de {seconds}s et a été interrompue"
                }), 503
            
            return result_queue.get_nowait() if not result_queue.empty() else jsonify({
                "status": "error",
                "message": "Aucune réponse du serveur"
            }), 500
        
        return wrapped
    return decorator

@app.route('/health')
@timeout_handler(seconds=2, default_response=jsonify({"status": "timeout", "message": "Health check timeout"}))
def health():
    """Endpoint de vérification de santé avec état détaillé"""
    global _is_initialized, _initialization_started
    global _db_initialized, _search_factory_initialized, _cache_initialized
    
    if not _initialization_started:
        status = "starting"
    elif not _is_initialized:
        status = "initializing"
    else:
        status = "ok"

    # Vérifier si 'start_time' est défini avant de calculer l'uptime
    start_time = app.config.get('start_time', time.time())  # Fallback à time.time() si non défini
    uptime = time.time() - start_time

    health_stats = {
        "uptime": uptime,
        "requests": stats.get("requests_total", 0),
        "errors": stats.get("error_count", 0),
        "avg_response_time": stats.get("avg_response_time", 0),
        "initialization_status": status
    }

    components = {
        "database": _db_initialized,
        "search_factory": _search_factory_initialized,
        "cache": _cache_initialized,
        "chatbot": _is_initialized and chatbot is not None
    }

    health_stats["components"] = components

    return jsonify({
        "status": status, 
        "timestamp": datetime.now().isoformat(),
        "checks": components,
        "stats": health_stats
    })


@app.route('/api/stats')
def get_stats():
    """API pour récupérer les statistiques d'utilisation"""
    return jsonify(stats)

@app.route('/api/cache/stats')
@async_route
async def get_cache_stats():
    """API pour récupérer les statistiques du cache"""
    if hasattr(global_cache, 'get_stats'):
        return jsonify(await global_cache.get_stats())
    return jsonify({"error": "Cache stats not available"}), 404

@app.route('/api/cache/clear', methods=['POST'])
@async_route
async def clear_cache():
    """API pour vider le cache"""
    if hasattr(global_cache, 'invalidate'):
        await global_cache.invalidate()
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