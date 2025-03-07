# app.py

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
import time
import threading
import traceback
from functools import wraps
from gevent import monkey
monkey.patch_all()
import nest_asyncio
nest_asyncio.apply()
from flask import Flask, render_template, request, jsonify, session, current_app
from flask_socketio import SocketIO, emit
from flask_cors import CORS
def process_data(data):
    logger.info("process_data called with data: %s", data)
    print("process_data called with data:", data)
    # Fonction d'exemple pour traiter le message reçu via la route /process
    # Remplacer "test_user" par l'identifiant utilisateur réel si nécessaire
    user_id = "test_user"
    run_process_message(user_id, data)
from dotenv import load_dotenv
from sqlalchemy import text
# Imports depuis le code optimisé
from base_de_donnees import SessionLocal, Conversation, init_db
from chatbot import ChatBot
from configuration import logger, global_cache
from search_factory import search_factory
# Configuration de Flask
app = Flask(__name__)
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='gevent',  # Utiliser gevent pour une meilleure compatibilité avec Gunicorn et Render
    ping_timeout=30,  # 30 secondes pour le ping timeout
    ping_interval=15,  # 15 secondes pour l'intervalle de ping
    max_http_buffer_size=1024 * 1024,  # 1MB buffer
    engineio_logger=True  # Activer les logs Engine.IO pour le debugging
)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'its_help_secret_key')
# Augmentation des timeouts
app.config['TIMEOUT'] = 60  # 60 secondes pour les requêtes
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 heure pour les sessions

# Configuration de CORS avec options explicites
CORS(app, resources={r"/*": {"origins": "*", "supports_credentials": True}})
"""Exemple de remplacement d'un appel asyncio.run par start_background_task """
@app.route('/process')
def process():
    data = request.args.get('data')
    socketio.start_background_task(process_data, data)
    return "Processing started"

# Variables globales et initialisations différées
chatbot = None
_is_initialized = False
_initialization_started = False
_db_initialized = False
_search_factory_initialized = False
_cache_initialized = False

# Chargement des variables d'environnement
load_dotenv()

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
    print("handle_connect: tentative de connexion SocketIO")
    """Gestion de la connexion SocketIO"""
    logger.info(f"Client connecté: {request.sid}")
    emit('response', {'message': 'Connexion établie avec ITS Help'})

@socketio.on('disconnect')
def handle_disconnect():
    """Gestion de la déconnexion SocketIO"""
    logger.info(f"Client déconnecté: {request.sid}")

@socketio.on('message')
def handle_message(data):
    # Traitement synchrone
    user_id = data.get('user_id', request.sid)
    if 'action' in data:
        action = data.get('action', {})
        action_type = action.get('type', '')
        action_value = action.get('value', '')
        logger.info("Action reçue: %s, value: %s", action_type, action_value)
    
    message = data.get('message', '')
    logger.info("handle_message déclenché, user_id: %s, message: %s", user_id, message)
    print("handle_message déclenché, data reçues:", data)
    if not chatbot:
        emit('response', {
            'message': 'Le service est en cours d\'initialisation, veuillez patienter quelques instants...',
            'type': 'status',
            'initializing': True
        })
        return
        
    # Envoi d'un accusé de réception
    emit('response', {'message': 'Message reçu, traitement en cours...', 'type': 'status'})
    
    # Utiliser une tâche de fond SocketIO pour le traitement asynchrone
    socketio.start_background_task(run_process_message, user_id, message)


def run_process_message(user_id, message):
    def target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Exécution avec une future pour capture d'erreurs
            future = asyncio.ensure_future(process_message(user_id, message), loop=loop)
            loop.run_until_complete(future)
        except Exception as e:
            logger.error(f"Erreur dans run_process_message: {str(e)}", exc_info=True)
        finally:
            loop.close()

    import threading
    t = threading.Thread(target=target)
    t.daemon = True
    t.start()

async def process_message(user_id, message):
    """Traite le message de manière asynchrone avec gestion améliorée des erreurs"""
    start_time = time.monotonic()
    global stats
    
    try:
        # Création d'une session dédiée à la conversation
        async with SessionLocal() as db:
            # Récupération ou création de la conversation
            result = await db.execute(
                text("SELECT * FROM conversations WHERE user_id = :user_id"),
                {"user_id": user_id}
            )
            conversation = result.fetchone()
        
            if not conversation:
                # Création d'une nouvelle conversation
                current_time = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    text("""
                    INSERT INTO conversations (user_id, context, last_updated) 
                    VALUES (:user_id, :context, :updated)
                    """),
                    {
                        "user_id": user_id,
                        "context": "{}",
                        "updated": current_time
                    }
                )
                await db.commit()
                
                # Récupération de la conversation nouvellement créée
                result = await db.execute(
                    text("SELECT * FROM conversations WHERE user_id = :user_id"),
                    {"user_id": user_id}
                )
                conversation = result.fetchone()
        
            # Traitement du message par le chatbot
            response = await chatbot.process_web_message(message, conversation, user_id)
            
            # Mise à jour du contexte avec les résultats de recherche
            try:
                context = json.loads(conversation.context) if conversation.context else {}
                # Mise à jour du contexte avec les derniers résultats
                if hasattr(chatbot, '_last_search_results'):
                    context['last_results'] = chatbot._last_search_results
                # Mettre à jour le contexte dans la base de données
                await db.execute(
                    text("""
                    UPDATE conversations 
                    SET context = :context, last_updated = :updated_time
                    WHERE user_id = :user_id
                    """),
                    {
                        "context": json.dumps(context),
                        "updated_time": datetime.now(timezone.utc).isoformat(),
                        "user_id": user_id
                    }
                )
                await db.commit()
            except Exception as ctx_err:
                logger.error(f"Erreur mise à jour contexte: {str(ctx_err)}")
        
            # Mise à jour des statistiques
            elapsed_time = time.monotonic() - start_time
            stats["requests_total"] = stats.get("requests_total", 0) + 1
            stats["response_time_sum"] = stats.get("response_time_sum", 0) + elapsed_time
            if stats["requests_total"] > 0:
                stats["avg_response_time"] = stats["response_time_sum"] / stats["requests_total"]
            else:
                stats["avg_response_time"] = 0
        
            # Mise à jour de la dernière interaction
            current_time = datetime.now(timezone.utc).isoformat()
            await db.execute(
                text("""
                UPDATE conversations 
                SET last_interaction = :interaction_time
                WHERE user_id = :user_id
                """),
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
        stats["error_count"] = stats.get("error_count", 0) + 1
        
        # Conservation des 10 dernières erreurs
        if "last_errors" not in stats:
            stats["last_errors"] = []
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
        
async def verify_clients_loaded():
    try:
        from sqlalchemy import func, select
        from base_de_donnees import SessionLocal, Client
        async with SessionLocal() as session:
            result = await session.execute(select(func.count()).select_from(Client))
            count = result.scalar()
            logger.info(f"Base clients initialisée avec {count} entrées")
    except Exception as e:
        logger.error(f"Échec vérification clients: {str(e)}")

def _do_initialize():
    global chatbot, _is_initialized, _initialization_started, _db_initialized
    
    app.config['start_time'] = time.time()
    _initialization_started = True
    
    # Marquer la BD comme initialisée
    _db_initialized = True

    # Lancer l'initialisation dans un thread séparé avec timeout global
    import threading
    def async_init():
        global _is_initialized, chatbot
        
        # Créer une nouvelle boucle pour ce thread
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        
        try:
            with app.app_context():
                try:
                    # Création du chatbot sans attendre la BD
                    chatbot = ChatBot(
                        openai_key=os.getenv('OPENAI_API_KEY'),
                        qdrant_url=os.getenv('QDRANT_URL'),
                        qdrant_api_key=os.getenv('QDRANT_API_KEY')
                    )
                    _is_initialized = True
                    logger.info("Chatbot initialisé avec succès")
                    
                    # Lancer l'initialisation de la BD en arrière-plan
                    new_loop.create_task(init_db())
                    # Appel de l'initialisation des clients
                    from gestion_clients import initialize_clients_with_validation
                    new_loop.create_task(initialize_clients_with_validation())
                    logger.info("Initialisation des clients lancée")
                except Exception as e:
                    logger.critical(f"Erreur initialisation chatbot: {str(e)}")
                    logger.critical(traceback.format_exc())
        except Exception as e:
            logger.critical(f"Erreur dans le thread d'initialisation: {str(e)}")
            logger.critical(traceback.format_exc())
        finally:
            # Garder la boucle en vie pour les tâches en arrière-plan
            try:
                new_loop.run_forever()
            except Exception:
                pass
    
    # Démarrer le thread d'initialisation en arrière-plan
    init_thread = threading.Thread(target=async_init)
    init_thread.daemon = True
    init_thread.start()
    logger.info("Thread d'initialisation démarré")
    
async def init_minimal_db(engine):
    """Initialisation minimale de la base de données en cas d'urgence"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    from base_de_donnees import Base  # Import explicite de Base
    
    # Création d'une session en mémoire
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    return async_session
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
                response_data = default_response or {"status": "timeout", "message": f"La requête a pris plus de {seconds}s et a été interrompue"}
                return jsonify(response_data), 503
            
            return result_queue.get_nowait() if not result_queue.empty() else jsonify({
                "status": "error",
                "message": "Aucune réponse du serveur"
            }), 500
        
        return wrapped
    return decorator

@app.route('/health')
@timeout_handler(seconds=2, default_response={"status": "timeout", "message": "Health check timeout"})
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
    
    # Démarrage du serveur via SocketIO (pour compatibilité avec WebSocket)
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Démarrage du serveur sur le port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=True)