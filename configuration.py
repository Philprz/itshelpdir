# configuration.py

# 1. Imports directs (bibliothèques standards)
import asyncio
import logging
import os
import sys
import json
import types
import time
import logging.handlers

from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from collections import OrderedDict

# 2. Imports de bibliothèques tierces
from typing import Dict, Optional, AsyncGenerator
from openai import AsyncOpenAI
from qdrant_client import QdrantClient
from pydantic import BaseModel, Field, ValidationError


DETAILED_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s | %(name)s | %(levelname)s | User:%(user)s | %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'detailed_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'detailed.log',
            'formatter': 'detailed',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5
        }
    },
    'loggers': {
        'ITS_HELP': {
            'handlers': ['detailed_file'],
            'level': 'DEBUG',
            'propagate': True
        }
    }
}
# Timeouts centralisés et cohérents
TIMEOUTS = {
    "openai": {
        "default": 45,  # Augmenté de 30 à 45
        "embedding": 25, # Augmenté de 15 à 25
        "completion": 60, # Augmenté de 45 à 60
        "chat": 30       # Ajout pour les appels chat.completions
    },
    "qdrant": {
        "default": 30,  # Doublé de 10 à 20
        "search": 45,   # Doublé de 15 à 30
        "erp_search":60,
        "upload": 45,
        "batch": 60      # Ajout pour les opérations batch
    },
    "global": 90,       # Augmenté de 60 à 90
    "slack_bot": {
        "websocket": 45,
        "recherche": 35,
        "ping": 30
    }
}

MAX_SEARCH_RESULTS = int(os.getenv('MAX_SEARCH_RESULTS', '3'))
def setup_logging():
    """Initialise un système de logging unifié avec filtrage des doublons et gestion améliorée des logs."""

    # Suppression des handlers existants
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Format unifié
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    # Handler console avec filtre de duplication
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Filtre pour éviter les messages dupliqués
    class DuplicateFilter(logging.Filter):
        def __init__(self, max_size=1000):
            super().__init__()
            self._msgs = OrderedDict()

        def filter(self, record):
            msg = record.getMessage()
            if msg in self._msgs:
                return False
            self._msgs[msg] = None
            if len(self._msgs) > 1000:  # Limite de stockage
                self._msgs.popitem(last=False)  # Supprime l'entrée la plus ancienne
            return True
    console_handler.addFilter(DuplicateFilter())
    

    # Ajout d'un handler de fichier
    file_handler = logging.FileHandler("app.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(DuplicateFilter())

    # Configuration dynamique des loggers
    logging_levels = {
        'ITS_HELP': logging.INFO,
        'ITS_HELP.qdrant': logging.WARNING, 
        'ITS_HELP.slack_bot': logging.INFO,
        'ITS_HELP.database': logging.WARNING,
        'aiosqlite': logging.ERROR,
        'slack_bolt.AsyncApp': logging.WARNING,
        'httpcore': logging.ERROR,
        'httpx': logging.ERROR,
        'openai': logging.WARNING
    }

    for logger_name, level in logging_levels.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.handlers = []
        logger.addHandler(console_handler)
        logger.propagate = False
class Config:
    def __init__(self):
        self.config = {}
        self._config = self.config  # Ajout de l'attribut _config
        
    def update(self, updates):
        if isinstance(updates, dict):
            self.config.update(updates)

    def __getitem__(self, key):
        return self.config.get(key)

    def __setitem__(self, key, value):
        self.config[key] = value

    def get(self, key, default=None):
        return self.config.get(key, default)  # Utilisation de self.config au lieu de self._config
def get_slack_bot(config: Config):
    from chatbot import SlackBot
    if not all([
        config.get("SLACK_BOT_TOKEN"),
        config.get("SLACK_APP_TOKEN"),
        config.get("OPENAI_API_KEY")
    ]):
        raise ConfigError("Tokens manquants pour l'initialisation du SlackBot")
        
    return SlackBot(
        slack_token=config.config["SLACK_BOT_TOKEN"],
        app_token=config.config["SLACK_APP_TOKEN"], 
        openai_key=config.config["OPENAI_API_KEY"]
    )
class GlobalCache:
    """Cache global partagé entre toutes les instances avec gestion de la mémoire."""
    
    def __init__(self, max_size=10000, ttl=3600):
        self._cache = {}
        self._access_times = {}
        self._size_tracker = {}  # Pour suivre la taille des objets en mémoire
        self._max_size = max_size
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._total_memory = 0
        self._max_memory = 100 * 1024 * 1024  # 100MB par défaut
        self._cleanup_task = None
        
    async def start_cleanup_task(self):
        """Démarre une tâche périodique de nettoyage du cache."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
    async def _periodic_cleanup(self):
        """Nettoie périodiquement les entrées expirées."""
        try:
            while True:
                await asyncio.sleep(300)  # Toutes les 5 minutes
                await self._cleanup_expired()
        except asyncio.CancelledError:
            logger.info("Tâche de nettoyage du cache annulée")
        
    async def _cleanup_expired(self):
        """Supprime les entrées expirées du cache."""
        now = time.monotonic()
        async with self._lock:
            expired_keys = [k for k, t in self._access_times.items() 
                          if now - t > self._ttl]
            for key in expired_keys:
                self._remove_item(key)
            
            # Si toujours trop de mémoire utilisée, supprimer les entrées les moins utilisées
            if self._total_memory > self._max_memory:
                oldest_keys = sorted(self._access_times.items(), key=lambda x: x[1])
                to_remove = int(len(oldest_keys) * 0.1)  # Supprimer 10% des entrées
                for key, _ in oldest_keys[:to_remove]:
                    self._remove_item(key)
    
    def _remove_item(self, key):
        """Supprime un élément du cache et met à jour les compteurs."""
        if key in self._cache:
            size = self._size_tracker.get(key, 0)
            self._total_memory -= size
            del self._cache[key]
            del self._access_times[key]
            if key in self._size_tracker:
                del self._size_tracker[key]
    
    def _estimate_size(self, value):
        """Estime la taille mémoire d'un objet."""
        if isinstance(value, list) and len(value) > 0:
            # Pour les embeddings (listes de floats)
            if isinstance(value[0], float):
                return len(value) * 8  # 8 octets par float
            # Pour les listes d'autres types
            return sum(sys.getsizeof(item) for item in value[:10]) * (len(value) / 10)
        elif isinstance(value, dict):
            # Estimation pour les dictionnaires
            sample_size = min(10, len(value))
            if sample_size > 0:
                sample_keys = list(value.keys())[:sample_size]
                avg_size = sum(sys.getsizeof(k) + sys.getsizeof(value[k]) for k in sample_keys) / sample_size
                return avg_size * len(value)
        return sys.getsizeof(value)
            
    async def get(self, key, namespace="default"):
        """Récupère une valeur du cache avec namespace."""
        full_key = f"{namespace}:{key}"
        async with self._lock:
            if full_key not in self._cache:
                return None
                
            if time.monotonic() - self._access_times[full_key] > self._ttl:
                self._remove_item(full_key)
                return None
                
            # Mettre à jour le temps d'accès
            self._access_times[full_key] = time.monotonic()
            return self._cache[full_key]
            
    async def set(self, key, value, namespace="default"):
        """Stocke une valeur dans le cache avec namespace."""
        full_key = f"{namespace}:{key}"
        async with self._lock:
            # Si la clé existe déjà, on la supprime d'abord
            if full_key in self._cache:
                self._remove_item(full_key)
                
            # Vérification de la capacité
            if len(self._cache) >= self._max_size:
                # Supprimer les 10% les plus anciens
                oldest = sorted(self._access_times.items(), key=lambda x: x[1])
                to_remove = int(len(oldest) * 0.1)
                for old_key, _ in oldest[:to_remove]:
                    self._remove_item(old_key)
                    
            # Estimation de la taille
            size = self._estimate_size(value)
            
            # Vérification de la mémoire disponible
            if self._total_memory + size > self._max_memory:
                # Libérer au moins 20% de la mémoire
                to_free = max(size, self._max_memory * 0.2)
                freed = 0
                oldest = sorted(self._access_times.items(), key=lambda x: x[1])
                
                for old_key, _ in oldest:
                    old_size = self._size_tracker.get(old_key, 0)
                    self._remove_item(old_key)
                    freed += old_size
                    if freed >= to_free:
                        break
            
            # Stockage
            self._cache[full_key] = value
            self._access_times[full_key] = time.monotonic()
            self._size_tracker[full_key] = size
            self._total_memory += size
            
    async def invalidate(self, pattern="*", namespace="default"):
        """Invalide les entrées correspondant au motif dans le namespace."""
        import fnmatch
        async with self._lock:
            if pattern == "*":
                # Tout supprimer pour ce namespace
                keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{namespace}:")]
            else:
                pattern_with_ns = f"{namespace}:{pattern}"
                keys_to_remove = [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern_with_ns)]
                
            for key in keys_to_remove:
                self._remove_item(key)
                
    def get_stats(self):
        """Retourne des statistiques sur l'utilisation du cache."""
        return {
            "items": len(self._cache),
            "memory_used": self._total_memory,
            "memory_limit": self._max_memory,
            "capacity": f"{(len(self._cache) / self._max_size) * 100:.1f}%",
            "memory_percentage": f"{(self._total_memory / self._max_memory) * 100:.1f}%"
        }
# Initialisation du cache global
global_cache = GlobalCache(
    max_size=int(os.getenv('EMBEDDING_CACHE_SIZE', 2000)),
    ttl=int(os.getenv('EMBEDDING_CACHE_TTL', 3600))
)
class ConfigError(Exception):
    """Erreur de configuration personnalisée avec contexte"""
    def __init__(self, message: str, context: Optional[Dict] = None):
        super().__init__(message)
        self.context = context or {}

class EnvConfig(BaseModel):
    """Validation complète des variables d'environnement"""
    OPENAI_API_KEY: str = Field(..., min_length=20)
    QDRANT_URL: str = Field(..., pattern=r'^https?://.+')
    QDRANT_API_KEY: Optional[str] = Field(None, min_length=8)
    DATABASE_URL: str = Field(default="sqlite:///data/conversations.db")
    LOG_LEVEL: str = Field(default="INFO", pattern=r'^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$')
    ENVIRONMENT: str = Field(default="development", pattern=r'^(development|staging|production)$')
    TIMEOUT_MULTIPLIER: float = Field(default=1.0, ge=0.5, le=2.0)

    class Config:
        extra = "forbid"

@dataclass
class ClientManager:
    """Gestionnaire amélioré des clients avec contexte et métriques"""
    openai: AsyncOpenAI
    qdrant: QdrantClient
    _is_closed: bool = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Fermeture propre et sécurisée des connexions"""
        if self._is_closed:
            return

        try:
            if hasattr(self.openai, "close"):
                await self.openai.close()

            if hasattr(self.qdrant, "close"):
                await self.qdrant.close()
        finally:
            self._is_closed = True

class TimeoutManager:
    def __init__(self, config: EnvConfig):
        self.multiplier = config.TIMEOUT_MULTIPLIER
        self.timeouts = TIMEOUTS
        self._cache = {}
    def get_timeout(self, service: str, operation: str = "default") -> float:
        # Récupère le timeout défini pour le service et l'opération, avec un fallback sur "default"
        service_timeouts = self.timeouts.get(service, {})
        timeout = service_timeouts.get(operation, service_timeouts.get("default", 30))
        return timeout * self.multiplier

    @asynccontextmanager
    async def timeout_context(self, service: str, operation: str = "default"):
        timeout = self.get_timeout(service, operation)
        try:
            async with asyncio.timeout(timeout):
                yield
        except asyncio.TimeoutError:
            raise ConfigError(
                f"Timeout après {timeout}s",
                {"service": service, "operation": operation}
            )
            
class PingPongFilter(logging.Filter):
    def filter(self, record):
        return not ('PING' in record.msg or 'PONG' in record.msg)

class HTTPHeaderFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, dict) and 'headers' in record.msg:
            record.msg = self._filter_headers(record.msg)
        return True
        
    def _filter_headers(self, msg):
        if isinstance(msg, dict):
            return {k:v for k,v in msg.items() if k.lower() not in ['authorization', 'cookie']}
        return msg

class LogManager:
    """Gestionnaire de logs amélioré"""
    def __init__(self, config: EnvConfig):
        self.config = config
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        """
        Configure un système de logging avancé avec:
        - Rotation des fichiers de log
        - Formatage JSON pour les logs d'erreur
        - Filtres intelligents pour réduire le bruit
        - Gestion des performances
        """
        # Niveau de base à partir de la configuration
        base_level = getattr(logging, self.config.LOG_LEVEL, logging.INFO)
        
        # Formateur pour console (concis)
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message).1000s'
        )
        
        # Formateur détaillé pour fichiers
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(process)d - %(thread)d - %(message)s'
        )
        
        # Handler pour console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(base_level)
        
        # Handler fichier principal avec rotation (10MB, 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            'app.log', 
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(base_level)
        
        # Handler fichier pour les erreurs uniquement (JSON)
        error_handler = logging.handlers.RotatingFileHandler(
            'errors.log',
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        
        # Formateur JSON pour les erreurs
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    'timestamp': self.formatTime(record, self.datefmt),
                    'level': record.levelname,
                    'logger': record.name,
                    'message': record.getMessage(),
                    'module': record.module,
                    'line': record.lineno
                }
                if record.exc_info:
                    log_data['exception'] = self.formatException(record.exc_info)
                return json.dumps(log_data)
        
        error_handler.setFormatter(JsonFormatter())
        
        # Configuration avancée des filtres
        class VerbosityFilter(logging.Filter):
            def __init__(self, modules_verbose=None):
                super().__init__()
                self.modules_verbose = modules_verbose or []
                
            def filter(self, record):
                # Réduire verbosité pour modules non critiques
                if record.levelno < logging.WARNING:
                    # Pour les modules non listés comme "verbose"
                    return any(record.name.startswith(mod) for mod in self.modules_verbose)
                return True
        
        # Application des filtres globaux
        verbose_modules = ['ITS_HELP.chatbot', 'ITS_HELP.qdrant.jira', 'ITS_HELP.qdrant.zendesk']
        console_handler.addFilter(VerbosityFilter(verbose_modules))
        console_handler.addFilter(PingPongFilter())
        console_handler.addFilter(HTTPHeaderFilter())
        
        # Configuration détaillée par module
        logging_levels = {
            'aiosqlite': logging.ERROR,
            'slack_bolt': logging.WARNING,
            'httpcore': logging.ERROR,
            'httpx': logging.ERROR,
            'openai': logging.WARNING,
            'ITS_HELP': base_level,
            'ITS_HELP.database': logging.WARNING,
            'ITS_HELP.qdrant': logging.WARNING,
            'ITS_HELP.chatbot': logging.INFO
        }

        # Application des niveaux avec gestion des modules parents/enfants
        configured_loggers = set()
        
        for logger_name, level in logging_levels.items():
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)
            
            # Ajout des handlers si pas déjà fait
            if logger_name not in configured_loggers:
                # Éviter les doublons en vérifiant les parents
                parent_configured = any(
                    logger_name.startswith(f"{configured}.")
                    for configured in configured_loggers
                )
                
                if not parent_configured:
                    logger.handlers = []  # Réinitialiser les handlers existants
                    logger.addHandler(console_handler)
                    logger.addHandler(file_handler)
                    logger.addHandler(error_handler)
                    
                    # Éviter la propagation aux parents pour les loggers spécifiques
                    logger.propagate = False
                    configured_loggers.add(logger_name)

        # Niveau racine pour garantir capture complète
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.WARNING)
        
        # Création du logger principal de l'application
        app_logger = logging.getLogger('ITS_HELP')
        
        # Ajout d'une méthode pour logs métiers
        def business_log(self, message, **kwargs):
            extra = {'business_data': kwargs}
            self.info(message, extra=extra)
        
        app_logger.business_log = types.MethodType(business_log, app_logger)
        
        return app_logger

@asynccontextmanager 
async def get_clients(env_config: Optional[EnvConfig] = None) -> AsyncGenerator[ClientManager, None]:
    """Context manager amélioré pour la gestion des clients"""
    if env_config is None:
        env_config = EnvConfig(**{
            key: os.getenv(key) 
            for key in EnvConfig.__annotations__.keys()
            if os.getenv(key) is not None  # Vérifie que la valeur existe
        })

    timeout_manager = TimeoutManager(env_config)
    client_manager = None

    try:
        # Vérification des clés obligatoires avant création du client
        if not env_config.OPENAI_API_KEY:
            raise ConfigError("Clé API OpenAI manquante")
            
        openai_client = AsyncOpenAI(
            api_key=env_config.OPENAI_API_KEY,
            timeout=timeout_manager.get_timeout("openai")
        )

        if not env_config.QDRANT_URL:
            raise ConfigError("URL Qdrant manquante")
            
        qdrant_client = QdrantClient(
            url=env_config.QDRANT_URL,
            api_key=env_config.QDRANT_API_KEY,
            timeout=timeout_manager.get_timeout("qdrant")
        )

        client_manager = ClientManager(
            openai=openai_client,
            qdrant=qdrant_client,
            _is_closed=False
        )

        # Test des connexions
        async with timeout_manager.timeout_context("global", "init"):
            await validate_connections(client_manager)

        yield client_manager

    except Exception as e:
        if isinstance(e, ConfigError):
            raise
        raise ConfigError(
            f"Erreur initialisation clients: {str(e)}",
            {"error_type": type(e).__name__}
        )
    finally:
        if client_manager:
            await client_manager.close()

async def validate_connections(clients: ClientManager):
    """Validation complète des connexions aux services"""
    async with clients as cm:
        try:
            # Test OpenAI avec retry
            for attempt in range(3):
                try:
                    await cm.openai.models.list()
                    break
                except Exception as e:
                    if attempt == 2:
                        raise ConfigError(
                            "Échec connexion OpenAI",
                            {"error": str(e)}
                        )
                    await asyncio.sleep(1)

            # Test Qdrant avec retry
            for attempt in range(3):
                try:
                    # Correction ici - la méthode get_collections() n'est pas async
                    # Remplaçons par une méthode qui vérifie réellement la connexion
                    collection_names = cm.qdrant.get_collections()
                    # Vérifions que nous avons bien récupéré la liste
                    if collection_names is None:
                        raise ConfigError("Impossible de récupérer les collections Qdrant")
                    break
                except Exception as e:
                    if attempt == 2:
                        raise ConfigError(
                            "Échec connexion Qdrant",
                            {"error": str(e)}
                        )
                    await asyncio.sleep(1)

        except Exception as e:
            if not isinstance(e, ConfigError):
                raise ConfigError(
                    "Échec validation connexions",
                    {"error": str(e)}
                )
            raise

async def validate_initial_setup():
    try:
        logger.info("=== Début validation configuration initiale ===")
        
        # Vérification des variables d'environnement
        required_env = ['OPENAI_API_KEY', 'QDRANT_URL', 'DATABASE_URL', 'SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN']
        missing = [env for env in required_env if not os.getenv(env)]
        if missing:
            logger.error(f"Variables d'environnement manquantes: {', '.join(missing)}")
            raise ConfigError(f"Variables d'environnement manquantes: {', '.join(missing)}")
        logger.info("✓ Variables d'environnement OK")

        # Vérification du niveau de log
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        if log_level not in logging._nameToLevel:
            logger.error(f"Niveau de log invalide: {log_level}")
            raise ConfigError(f"Niveau de log invalide: {log_level}")
        logger.info("✓ Niveau de log OK")

        # Vérification de l'environnement
        env = os.getenv('ENVIRONMENT', 'development').lower()
        if env not in ['development', 'staging', 'production']:
            logger.error(f"Environnement invalide: {env}")
            raise ConfigError(f"Environnement invalide: {env}")
        logger.info("✓ Environnement OK")

        # Test de la configuration OpenAI
        logger.info("Test connexion OpenAI...")
        try:
            client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            await client.models.list()
            logger.info("✓ Connexion OpenAI OK")
        except Exception as e:
            logger.error(f"Échec connexion OpenAI: {str(e)}")
            return {
                "openai": False,
                "slack": False, 
                "qdrant": False
            }

        # Test de la configuration Qdrant
        logger.info("Test connexion Qdrant...")
        try:
            qdrant_client = QdrantClient(
                url=os.getenv('QDRANT_URL'),
                api_key=os.getenv('QDRANT_API_KEY')
            )
            # Vérifions directement la connexion
            collections = qdrant_client.get_collections()
            if collections is not None:
                logger.info("✓ Connexion Qdrant OK")
            else:
                raise Exception("Impossible de récupérer les collections")
        except Exception as e:
            logger.error(f"Échec connexion Qdrant: {str(e)}")
            return {
                "openai": True,
                "slack": False,
                "qdrant": False
            }

        # Test de la configuration Slack modifié :
        logger.info("Test connexion Slack...")
        try:
            # Création d'une configuration temporaire pour le test
            temp_config = Config()
            temp_config["SLACK_BOT_TOKEN"] = os.getenv("SLACK_BOT_TOKEN")
            temp_config["SLACK_APP_TOKEN"] = os.getenv("SLACK_APP_TOKEN") 
            temp_config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

            # Test de connexion sans démarrer le bot complet
            #from slack_bolt.async_app import AsyncApp
            #app = AsyncApp(token=os.getenv("SLACK_BOT_TOKEN"))
            
            # Test simple d'authentification
            try:
                from slack_bolt.async_app import AsyncApp
                temp_app = AsyncApp(token=os.getenv("SLACK_BOT_TOKEN"))
                auth_test = await temp_app.client.auth_test()
            except Exception as e:
                logger.error(f"Échec authentification Slack: {str(e)}")
                return {
                    "openai": True,
                    "slack": False,
                    "qdrant": True
                }
            if not auth_test["ok"]:
                raise Exception("Échec authentification Slack")
                
            logger.info(f"✓ Connexion Slack OK (Team: {auth_test['team']})")
            
            return {
                "openai": True,
                "slack": True,
                "qdrant": True
            }

        except Exception as e:
            logger.error(f"Erreur connexion Slack: {str(e)}")
            return {
                "openai": True,
                "slack": False,
                "qdrant": True
            }

    except Exception as e:
        logger.error(f"Erreur validation setup: {str(e)}")
        raise

async def init_config():
    """Initialise la configuration de manière asynchrone"""
    try:
        await validate_initial_setup()
        # Démarrage du nettoyage périodique du cache
        await global_cache.start_cleanup_task()
        async with get_clients() as clients:
            # Test des connexions
            await validate_connections(clients)
            return clients
    except Exception as e:
        logger.error(f"Erreur initialisation: {str(e)}")
        raise

# Export des instances préconfigurées
env_config = EnvConfig(**{
    key: os.getenv(key) or 
         ('sqlite+aiosqlite:///data/database.db' if key == 'DATABASE_URL' else
          1.0 if key == 'TIMEOUT_MULTIPLIER' else None)
    for key in EnvConfig.__annotations__.keys()
})

timeout_manager = TimeoutManager(env_config)
log_manager = LogManager(env_config)
logger = log_manager.logger

# Création et export de la configuration globale
config = Config()
config.config = {
    "OPENAI_API_KEY": env_config.OPENAI_API_KEY,
    "QDRANT_URL": env_config.QDRANT_URL,
    "QDRANT_API_KEY": env_config.QDRANT_API_KEY,
    "LOG_LEVEL": env_config.LOG_LEVEL,
    "ENVIRONMENT": env_config.ENVIRONMENT,
    "TIMEOUT_MULTIPLIER": env_config.TIMEOUT_MULTIPLIER,
    "DATABASE_URL": env_config.DATABASE_URL
}
config["SLACK_BOT_TOKEN"] = os.getenv("SLACK_BOT_TOKEN")
config["SLACK_APP_TOKEN"] = os.getenv("SLACK_APP_TOKEN")
