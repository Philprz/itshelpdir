# Imports standards
import os
import json
import asyncio
import logging
import time
import traceback
import uuid
from functools import wraps
from importlib.util import find_spec

# Imports Flask et extensions
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from dotenv import load_dotenv

# Imports pour la gestion des erreurs
import sqlalchemy.orm.exc as sa_exc
from openai import OpenAIError

# Imports internes
from configuration import logger, global_cache
from base_de_donnees import init_db
from adapter_web_chatbot import adapter, initialize_adapter

# Vérification de disponibilité des libs de transport pour Socket.IO
has_eventlet = find_spec("eventlet") is not None
has_gevent = find_spec("gevent") is not None

# Classe pour gérer les travaux asynchrones avec système de priorité
class AsyncWorkerPool:
    """
    Pool de workers asynchrones avec file d'attente prioritaire.
    Remplace l'utilisation de threads par des tâches asyncio.
    """
    def __init__(self, max_workers=10, loop=None):
        self.max_workers = max_workers
        self.active_tasks = set()
        self.queue = asyncio.PriorityQueue()
        self.loop = loop or asyncio.get_event_loop()
        self.logger = logging.getLogger('ITS_HELP.worker_pool')
        
    async def submit(self, coroutine, priority=0, user_id=None, timeout=None):
        """
        Soumet une tâche coroutine au pool avec gestion de priorité.
        
        Args:
            coroutine: Coroutine à exécuter
            priority: Priorité (plus petit = plus prioritaire)
            user_id: Identifiant utilisateur pour le traçage
            timeout: Timeout en secondes (None = pas de timeout)
        """
        # Placer la tâche dans la file d'attente avec sa priorité
        task_id = f"{user_id or 'system'}_{int(time.time())}"
        await self.queue.put((priority, (coroutine, user_id, task_id, timeout)))
        self.logger.debug(f"Tâche {task_id} ajoutée à la file d'attente avec priorité {priority}")
        
        # Déclencher le traitement si des workers sont disponibles
        if len(self.active_tasks) < self.max_workers:
            asyncio.create_task(self._process_queue())
            
        return task_id
    
    async def _process_queue(self):
        """Traite la file d'attente des tâches en respectant la priorité"""
        while not self.queue.empty() and len(self.active_tasks) < self.max_workers:
            # Extraction de la tâche avec la plus haute priorité
            _, (coroutine, user_id, task_id, timeout) = await self.queue.get()
            
            # Création et exécution de la tâche
            task = asyncio.create_task(self._run_task(coroutine, user_id, task_id, timeout))
            self.active_tasks.add(task)
            
            # Nettoyer la tâche quand elle termine
            task.add_done_callback(lambda t: self.active_tasks.remove(t) 
                                   if t in self.active_tasks else None)
            
    async def _run_task(self, coroutine, user_id, task_id, timeout):
        """Exécute une tâche avec timeout et gestion d'erreurs"""
        start_time = time.monotonic()
        self.logger.info(f"Démarrage tâche {task_id} pour utilisateur {user_id}")
        
        try:
            # Exécution avec timeout si spécifié
            if timeout:
                return await asyncio.wait_for(coroutine, timeout=timeout)
            else:
                return await coroutine
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            self.logger.error(f"Timeout pour tâche {task_id} après {elapsed:.2f}s")
            return None
        except Exception as e:
            self.logger.error(f"Erreur dans tâche {task_id}: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None
        finally:
            elapsed = time.monotonic() - start_time
            self.logger.info(f"Fin tâche {task_id}, durée: {elapsed:.2f}s")
            
    def get_stats(self):
        """Retourne des statistiques sur l'état du pool"""
        return {
            "active_tasks": len(self.active_tasks),
            "queued_tasks": self.queue.qsize(),
            "max_workers": self.max_workers
        }

# Classe pour gérer l'état global de l'application
class ApplicationContext:
    """
    Gère l'état global et les dépendances de l'application.
    Cette classe centralise les initialisations et permet un accès unifié
    aux différentes ressources partagées.
    """
    
    def __init__(self):
        """Initialise les attributs mais n'effectue pas les initialisations couteuses"""
        self.db_initialized = False
        self.chatbot = None
        self.initialized = False
        self.initialization_attempt = False
        self.initialization_time = None
        self.logger = logging.getLogger('ITS_HELP.app_context')
        self.errors = []
        self.initialization_lock = asyncio.Lock()
    
    async def init_database(self):
        """Initialise la base de données"""
        if self.db_initialized:
            return True
            
        self.logger.info("Initialisation de la base de données")
        try:
            # Initialiser la base de données
            await init_db()
            self.db_initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation de la base de données: {str(e)}")
            self.errors.append(str(e))
            return False
    
    async def init_cache(self):
        """Initialise et préchauffe le cache"""
        self.logger.info("Initialisation du cache")
        try:
            # Préchargement des données de cache fréquemment utilisées
            global_cache.clear('embeddings')  # Assurer que le cache démarre proprement
            
            # Vérification du cache
            cache_status = global_cache.status()
            self.logger.info(f"État du cache: {json.dumps(cache_status)}")
            
            # Cache initialisé avec succès
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du cache: {str(e)}")
            self.errors.append(str(e))
            return False
    
    async def init_search_factory(self):
        """Initialise la factory de recherche"""
        from search_factory import search_factory
        self.logger.info("Initialisation de la factory de recherche")
        try:
            # Initialisation de la factory de recherche
            await search_factory.initialize()
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation de la factory de recherche: {str(e)}")
            self.errors.append(str(e))
            return False
    
    async def init_chatbot(self):
        """Initialise le chatbot"""
        from chatbot import ChatBot
        self.logger.info("Initialisation du chatbot")
        try:
            # Récupération des clés nécessaires depuis les variables d'environnement
            openai_key = os.getenv('OPENAI_API_KEY')
            qdrant_url = os.getenv('QDRANT_URL')
            qdrant_api_key = os.getenv('QDRANT_API_KEY')
            
            if not openai_key or not qdrant_url:
                self.logger.error("Clés API manquantes: OPENAI_API_KEY ou QDRANT_URL non définies")
                self.errors.append("Clés API requises non définies dans les variables d'environnement")
                return False
                
            self.chatbot = ChatBot(
                openai_key=openai_key,
                qdrant_url=qdrant_url,
                qdrant_api_key=qdrant_api_key
            )
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du chatbot: {str(e)}")
            self.errors.append(str(e))
            return False

# Création de l'instance globale du contexte
app_context = ApplicationContext()

# Création de l'instance globale du pool de workers
worker_pool = AsyncWorkerPool(max_workers=10)

def process_data(data):
    logger.info("process_data called with data: %s", data)
    print("process_data called with data:", data)
    # Fonction d'exemple pour traiter le message reçu via la route /process
    # Remplacer "test_user" par l'identifiant utilisateur réel si nécessaire
    user_id = "test_user"
    run_process_message(user_id, data)

# Configuration de Flask
app = Flask(__name__)

# Détection du meilleur mode asynchrone disponible
async_mode = None
if has_eventlet:
    async_mode = 'eventlet'
elif has_gevent:
    async_mode = 'gevent'
else:
    async_mode = 'threading'  # Fallback sûr pour tous les environnements

logger.info(f"Utilisation du mode asynchrone: {async_mode}")

# Configuration de SocketIO avec détection du meilleur mode disponible
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode=async_mode,  # Mode détecté automatiquement
    ping_timeout=30,  
    ping_interval=15,  
    max_http_buffer_size=1024 * 1024,  
    engineio_logger=True if os.getenv('DEBUG', 'false').lower() == 'true' else False
)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'its_help_secret_key')
# Augmentation des timeouts
app.config['TIMEOUT'] = 60  
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  

# Configuration de CORS avec options explicites
CORS(app, resources={r"/*": {"origins": "*", "supports_credentials": True}})

"""Exemple de remplacement d'un appel asyncio.run par start_background_task """
@app.route('/process')
def process():
    data = request.args.get('data')
    socketio.start_background_task(process_data, data)
    return "Processing started"

# Chargement des variables d'environnement
load_dotenv()

# Définition de la fonction ensure_initialization
def initialize_wrapper():
    """Wrapper non-async pour lancer la fonction initialize dans un environnement asynchrone"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize())
    loop.close()

def ensure_initialization():
    """S'assure que l'initialisation est lancée dans le contexte de l'application"""
    if not app_context.initialization_attempt:
        logger.info("Démarrage de l'initialisation du chatbot")
        socketio.start_background_task(initialize_wrapper)

# Démarrer l'initialisation au lancement de l'application
ensure_initialization()

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
    # Ne pas envoyer de message automatique pour éviter les doublons

@socketio.on('disconnect')
def handle_disconnect():
    """Gestion de la déconnexion SocketIO"""
    logger.info(f"Client déconnecté: {request.sid}")

@socketio.on('message')
def handle_message(data):
    # Traitement synchrone
    user_id = data.get('user_id', request.sid)
    message = data.get('message', '')
    # EXTRAIRE le mode (par défaut "detail")
    mode = data.get('mode', 'detail')
    logger.info("handle_message déclenché, user_id: %s, message: %s, mode: %s", user_id, message, mode)
    print("SOCKET.IO MESSAGE REÇU:", data)  # Ajout d'un log plus visible

    if 'action' in data:
        action = data.get('action', {})
        action_type = action.get('type', '')
        action_value = action.get('value', '')
        logger.info("Action reçue: %s, value: %s", action_type, action_value)
    
    message = data.get('message', '')
    logger.info("handle_message déclenché, user_id: %s, message: %s", user_id, message)
    print("handle_message déclenché, data reçues:", data)
    
    # Utilisation du chatbot depuis le contexte d'application
    if not app_context.chatbot:
        logger.info("Le chatbot n'est pas initialisé! Démarrage de l'initialisation...")
        ensure_initialization()  # Déclencher l'initialisation si pas encore fait
        emit('response', {
            'message': 'Le service est en cours d\'initialisation, veuillez patienter quelques instants...',
            'type': 'status',
            'initializing': True
        })
        # Passer le message à la file d'attente pour traitement ultérieur
        socketio.start_background_task(run_process_message, user_id, message, mode)
        return
    
    # Traiter directement le message de façon synchrone dans un thread de fond
    # pour éviter les problèmes avec les event loops asynchrones
    try:
        # Lancer le traitement dans un thread distinct géré par socketio
        socketio.start_background_task(
            process_message_background,
            user_id=user_id, 
            message=message, 
            mode=mode
        )
        # Envoi d'un accusé de réception
        emit('response', {'message': 'Message reçu, traitement en cours...', 'type': 'status'})
    except Exception as e:
        logger.error(f"Erreur lors du démarrage du traitement: {str(e)}")
        emit('response', {'message': 'Erreur lors du traitement: ' + str(e), 'type': 'error'})

def run_process_message(user_id, message, mode="detail"):
    """
    Version compatible de l'ancienne fonction utilisant le pool de workers.
    Cette fonction est maintenue pour compatibilité avec le code existant.
    """
    try:
        # Lancer directement le traitement dans un thread distinct
        socketio.start_background_task(
            process_message_background,
            user_id=user_id, 
            message=message, 
            mode=mode
        )
        logger.info(f"Tâche de traitement lancée pour message: {message[:30]}...")
    except Exception as e:
        logger.error(f"Erreur lors du lancement du traitement: {str(e)}")

def process_message_background(user_id, message, mode):
    """Wrapper synchrone pour appeler la coroutine process_message de manière sécurisée"""
    # Créer une nouvelle boucle asyncio pour ce thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Exécuter la coroutine process_message de manière synchrone
        loop.run_until_complete(process_message(user_id, message, mode))
    except Exception as e:
        logger.error(f"Erreur dans process_message_background: {str(e)}")
        stacktrace = traceback.format_exc()
        logger.error(f"Stack trace: {stacktrace}")
        # Notification d'erreur à l'utilisateur via socket.io
        socketio.emit('response', {
            'message': f"Une erreur s'est produite lors du traitement: {str(e)}",
            'type': 'error'
        }, room=user_id)
    finally:
        # Fermer proprement la boucle
        try:
            # Annuler toutes les tâches pendantes
            pending = asyncio.all_tasks(loop=loop)
            for task in pending:
                task.cancel()
            
            # Exécuter jusqu'à ce que toutes les tâches annulées soient terminées
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            
            loop.close()
        except Exception as close_e:
            logger.error(f"Erreur lors de la fermeture de la boucle: {str(close_e)}")

async def process_message(user_id, message, mode):
    """Traite le message de manière asynchrone avec gestion améliorée des erreurs"""
    start_time = time.time()
    logger.info(f"Début de traitement du message pour user_id: {user_id}")
    
    # Créer un ID de corrélation unique pour tracer les logs    
    correlation_id = str(uuid.uuid4())
    context_logger = logging.LoggerAdapter(
        logger, 
        {'correlation_id': correlation_id, 'user_id': user_id}
    )
    
    # Afficher un message de chargement
    socketio.emit('response', {
        'message': 'Analyse en cours...',
        'type': 'thinking',
        'correlation_id': correlation_id
    }, room=user_id)
    
    # Vérifier si l'initialisation est terminée
    if not app_context.initialized:
        await wait_for_initialization(user_id, max_wait=30)  # Max 30 secondes
        if not app_context.initialized:
            socketio.emit('response', {
                'message': 'Le service n\'est pas encore disponible, veuillez réessayer dans quelques instants.',
                'type': 'error'
            }, room=user_id)
            return
    
    try:
        # Extraire les options de formatage si disponibles (pour compatibilité avec interface web)
        options = {}
        
        if isinstance(message, dict):
            message_text = message.get('text', '')
            options = {
                'debug_zendesk': message.get('debug_zendesk', False),
                'progressive': message.get('progressive', True),  # Par défaut, activer le formatage progressif
                'timeout': message.get('timeout', 60)  # Timeout par défaut à 60 secondes
            }
        else:
            message_text = message
            options = {
                'debug_zendesk': False,
                'progressive': True,  # Par défaut, activer le formatage progressif
                'timeout': 60  # Timeout par défaut à 60 secondes
            }
        
        # Mesure du temps de traitement
        context_logger.info(f"Appel du chatbot pour analyser: {message_text[:50]}...")
        
        # Utilisation de l'adaptateur pour traiter le message
        response = await adapter.process_message(
            message=message_text,
            user_id=user_id,
            mode=mode,
            debug_zendesk=options['debug_zendesk'],
            progressive=options['progressive'],
            timeout=options['timeout']
        )
        
        processing_time = time.time() - start_time
        context_logger.info(f"Traitement terminé en {processing_time:.2f}s")
        
        # Vérification et normalisation de la réponse avant émission
        if not response:
            context_logger.error("Réponse vide reçue de l'adaptateur")
            socketio.emit('response', {
                'message': "Une erreur est survenue lors du traitement de votre demande.",
                'type': 'error'
            }, room=user_id)
            return
            
        # S'assurer que la réponse a le bon format pour l'UI
        if isinstance(response, dict):
            # S'assurer que les champs essentiels sont présents
            if 'type' not in response:
                response['type'] = 'result'
                
            # Transformer 'text' en 'message' si nécessaire (convention UI)
            if 'message' not in response and 'text' in response:
                response['message'] = response['text']
                
            # Vérifier la présence de blocs pour l'affichage
            if 'blocks' not in response or not response['blocks']:
                context_logger.warning("Réponse sans blocs, application d'un format par défaut")
                if 'message' in response:
                    response['blocks'] = [{
                        'type': 'section',
                        'text': {'type': 'mrkdwn', 'text': response['message']}
                    }]
                elif 'text' in response:
                    response['blocks'] = [{
                        'type': 'section',
                        'text': {'type': 'mrkdwn', 'text': response['text']}
                    }]
                    
            # Log des informations de blocs
            if 'blocks' in response:
                context_logger.info(f"Émission d'une réponse avec {len(response['blocks'])} blocs")
                
        # Format de réponse attendu pour la compatibilité
        socketio.emit('response', response, room=user_id)

    except OpenAIError as e:
        context_logger.error(f"Erreur OpenAI: {str(e)}")
        socketio.emit('response', {
            'message': f"Erreur lors de l'analyse: {str(e)}",
            'type': 'error'
        }, room=user_id)
    except sa_exc.NoResultFound as e:
        context_logger.error(f"Erreur base de données (no result): {str(e)}")
        socketio.emit('response', {
            'message': "Session non trouvée, veuillez réessayer.",
            'type': 'error'
        }, room=user_id)
    except Exception as e:
        error_info = traceback.format_exc()
        context_logger.error(f"Erreur inattendue: {str(e)}")
        context_logger.error(error_info)
        
        # Formatting résultat
        if hasattr(e, 'format_as_blocks'):
            try:
                blocks = e.format_as_blocks()
                socketio.emit('response', {
                    'blocks': blocks,
                    'type': 'error'
                }, room=user_id)
                return
            except Exception as format_err:
                context_logger.error(f"Erreur formatage résultats: {str(format_err)}")
                
        # Émission du message d'erreur
        socketio.emit('response', {
            'message': "Une erreur est survenue lors du traitement de votre demande.",
            'error': str(e),
            'type': 'error'
        }, room=user_id)

async def wait_for_initialization(user_id, max_wait=30):
    """Attend que l'initialisation soit terminée avec un timeout"""
    start_time = time.time()
    while not app_context.initialized and time.time() - start_time < max_wait:
        # Feedback à l'utilisateur sur l'état de l'initialisation
        socketio.emit('response', {
            'message': f'Initialisation en cours ({time.time() - start_time:.1f}s)...',
            'type': 'status'
        }, room=user_id)
        
        # Attendre un peu avant de vérifier à nouveau
        await asyncio.sleep(2)
    
    return app_context.initialized

async def initialize():
    """Initialisation progressive des composants au démarrage"""
    async with app_context.initialization_lock:
        if app_context.initialization_attempt:
            return
        
        app_context.initialization_attempt = True
        
        await app_context.init_database()
        await app_context.init_cache()
        await app_context.init_search_factory()
        await initialize_adapter()
        app_context.chatbot = adapter
        app_context.initialized = True

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