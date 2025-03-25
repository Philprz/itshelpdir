# search_factory.py

import os
import logging
import time
from typing import Optional, Callable
import asyncio

from configuration import logger, global_cache

class CircuitBreaker:
    """
    Implémentation du pattern Circuit Breaker pour protéger contre les erreurs répétées.
    Permet d'éviter d'appeler des services défaillants et de récupérer automatiquement.
    """
    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: int = 60):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.logger = logging.getLogger(f'ITS_HELP.circuit_breaker.{name}')
        
    def record_success(self):
        """Enregistre un succès et réinitialise le compteur d'échec"""
        self.failure_count = 0
        if self.state == "HALF-OPEN":
            self.state = "CLOSED"
            self.logger.info(f"Circuit {self.name} fermé après succès en état half-open")
            
    def record_failure(self):
        """Enregistre un échec et ouvre le circuit si le seuil est atteint"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                self.logger.warning(f"Circuit {self.name} ouvert après {self.failure_count} échecs")
                self.state = "OPEN"
            
    def can_execute(self):
        """Vérifie si une opération peut être exécutée selon l'état du circuit"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            # Vérifier si le temps de réinitialisation est écoulé
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF-OPEN"
                self.logger.info(f"Circuit {self.name} passé en half-open après {self.reset_timeout}s")
                return True
            return False
        elif self.state == "HALF-OPEN":
            return True
        return False
        
    def reset(self):
        """Réinitialise le circuit à son état fermé"""
        self.failure_count = 0
        self.state = "CLOSED"
        self.logger.info(f"Circuit {self.name} réinitialisé manuellement")
        
    def get_status(self):
        """Retourne l'état actuel du circuit pour monitoring"""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time,
            "threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout
        }

async def with_circuit_breaker(circuit: CircuitBreaker, operation: Callable, 
                               fallback: Optional[Callable] = None, *args, **kwargs):
    """
    Exécute une opération avec protection par circuit breaker.
    
    Args:
        circuit: Instance de CircuitBreaker
        operation: Fonction/coroutine à exécuter
        fallback: Fonction/coroutine de repli en cas d'échec
        args, kwargs: Arguments à passer à l'opération
    """
    if not circuit.can_execute():
        if fallback:
            return await fallback(*args, **kwargs)
        raise RuntimeError(f"Circuit {circuit.name} ouvert, opération non exécutée")
        
    try:
        result = await operation(*args, **kwargs)
        circuit.record_success()
        return result
    except Exception as e:
        circuit.record_failure()
        logger.error(f"Erreur dans circuit {circuit.name}: {str(e)}")
        if fallback:
            return await fallback(*args, **kwargs)
        raise

class SearchClientFactory:
    """
    Factory pour la création et la gestion des clients de recherche.
    Centralise la gestion des dépendances et des instances.
    """

    def __init__(self):
        self.clients = {}
        self.qdrant_client = None
        self.openai_client = None
        self.embedding_service = None
        self.translation_service = None
        self.initialized = False
        self.logger = logging.getLogger('ITS_HELP.search.factory')
        
        # Circuit breakers pour les différents services
        self.circuit_breakers = {
            "qdrant": CircuitBreaker("qdrant", failure_threshold=3, reset_timeout=30),
            "openai": CircuitBreaker("openai", failure_threshold=3, reset_timeout=60),
            "client_creation": CircuitBreaker("client_creation", failure_threshold=5, reset_timeout=120),
            "client_import": CircuitBreaker("client_import", failure_threshold=2, reset_timeout=300)
        }

        # Collections par défaut
        self.default_collections = {
            'jira': os.getenv('QDRANT_COLLECTION_JIRA', 'JIRA'),
            'zendesk': os.getenv('QDRANT_COLLECTION_ZENDESK', 'ZENDESK'),
            'confluence': os.getenv('QDRANT_COLLECTION_CONFLUENCE', 'CONFLUENCE'),
            'netsuite': os.getenv('QDRANT_COLLECTION_NETSUITE', 'NETSUITE'),
            'netsuite_dummies': os.getenv('QDRANT_COLLECTION_NETSUITE_DUMMIES', 'NETSUITE_DUMMIES'),
            'sap': os.getenv('QDRANT_COLLECTION_SAP', 'SAP'),
            'erp': os.getenv('QDRANT_COLLECTION_ERP', 'ERP')
        }

    async def initialize(self):
        """Initialise tous les clients et services nécessaires avec gestion des erreurs"""
        if self.initialized:
            self.logger.info("Factory déjà initialisée - ignoré")
            return
            
        self.logger.info("Initialisation des clients et services...")
        
        # Initialisation des composants de base avec gestion des erreurs
        await self._initialize_qdrant_client()
        await self._initialize_openai_client()
        await self._initialize_services()
        
        # Garde-fou: si les composants de base ne sont pas initialisés correctement,
        # utiliser des composants de fallback pour permettre un fonctionnement dégradé
        if not self.qdrant_client:
            self.logger.warning("QdrantClient non initialisé - création d'un fallback")
            self.qdrant_client = self._create_fallback_qdrant_client()
            
        if not self.openai_client:
            self.logger.warning("OpenAI client non initialisé - création d'un fallback")
            self.openai_client = self._create_fallback_openai_client()
            
        if not self.embedding_service:
            self.logger.warning("EmbeddingService non initialisé - création d'un fallback")
            self.embedding_service = self._create_fallback_embedding_service()
            
        if not self.translation_service:
            self.logger.warning("TranslationService non initialisé - création d'un fallback")
            self.translation_service = self._create_fallback_translation_service()
        
        # Création des clients de recherche spécialisés en utilisant les nouvelles méthodes
        # avec fallback automatique en cas d'erreur
        results = await asyncio.gather(
            self._initialize_client("jira", "jira"),
            self._initialize_client("zendesk", "zendesk"),
            self._initialize_client("erp", "erp"),
            self._initialize_client("netsuite", "netsuite"),
            self._initialize_client("netsuite_dummies", "netsuite_dummies"),
            self._initialize_client("sap", "sap"),
            self._initialize_client("confluence", "confluence"),
            return_exceptions=True
        )
        
        # Traitement des résultats
        client_names = ["jira", "zendesk", "erp", "netsuite", "netsuite_dummies", "sap", "confluence"]
        for i, result in enumerate(results):
            client_name = client_names[i] if i < len(client_names) else f"client_{i}"
            
            if isinstance(result, Exception):
                self.logger.error(f"Erreur initialisation {client_name}: {str(result)}")
                # Créer un client de fallback en cas d'erreur
                try:
                    self.clients[client_name] = self._create_fallback_client(client_name, client_name)
                except Exception as e:
                    self.logger.error(f"Erreur critique sur fallback {client_name}: {str(e)}")
            else:
                if result:
                    self.clients[client_name] = result
                else:
                    # Créer un client de fallback si le résultat est None
                    self.clients[client_name] = self._create_fallback_client(client_name, client_name)
        
        # Mise à jour du statut d'initialisation
        success_count = sum(1 for client in self.clients.values() if not isinstance(client, Exception))
        self.logger.info(f"Factory initialisée: {success_count}/{len(client_names)} clients OK")
        
        self.initialized = True
        return

    async def get_client(self, source_type: str):
        """
        Récupère ou crée un client de recherche pour le type demandé.

        Args:
            source_type: Type de source de données ('jira', 'zendesk', etc.)

        Returns:
            Client de recherche correspondant ou None si non pris en charge
        """
        # Vérification de l'initialisation
        if not self.initialized:
            await self.initialize()

        # Normalisation du type
        source_type = source_type.lower()

        # Vérification du cache
        if source_type in self.clients:
            return self.clients[source_type]

        # Circuit breaker pour la création de client
        if not self.circuit_breakers["client_creation"].can_execute():
            self.logger.warning(f"Circuit client_creation ouvert, impossible de créer client {source_type}")
            return None

        # Obtention dynamique des types de clients
        async def get_client_types():
            # Circuit breaker pour l'import de client
            if not self.circuit_breakers["client_import"].can_execute():
                return self._get_fallback_client_types()
                
            try:
                from search_clients import (
                    JiraSearchClient,
                    ZendeskSearchClient,
                    ConfluenceSearchClient,
                    NetsuiteSearchClient,
                    NetsuiteDummiesSearchClient,
                    SapSearchClient,
                    ERPSearchClient
                )

                # Création des mappings vers les classes
                client_types = {
                    'jira': JiraSearchClient,
                    'zendesk': ZendeskSearchClient,
                    'confluence': ConfluenceSearchClient,
                    'netsuite': NetsuiteSearchClient,
                    'netsuite_dummies': NetsuiteDummiesSearchClient,
                    'sap': SapSearchClient,
                    'erp': ERPSearchClient
                }
                self.circuit_breakers["client_import"].record_success()
                return client_types
            except Exception as e:
                self.circuit_breakers["client_import"].record_failure()
                self.logger.error(f"Erreur import classes clients: {str(e)}")
                return self._get_fallback_client_types()
        
        client_types = await get_client_types()

        # Vérification du type supporté
        if source_type not in client_types:
            self.logger.warning(f"Type de source non pris en charge: {source_type}")
            return None

        # Récupération de la collection
        collection_name = self.default_collections.get(source_type)
        if not collection_name:
            self.logger.warning(f"Pas de collection configurée pour {source_type}")
            return None

        # Création du client avec circuit breaker
        try:
            client_class = client_types[source_type]
            client = client_class(
                collection_name=collection_name,
                qdrant_client=self.qdrant_client,
                embedding_service=self.embedding_service,
                translation_service=self.translation_service
            )

            # Test minimal du client
            # Ce serait bien d'avoir une méthode health() sur chaque client
            
            # Mise en cache
            self.clients[source_type] = client
            self.circuit_breakers["client_creation"].record_success()
            return client

        except Exception as e:
            self.circuit_breakers["client_creation"].record_failure()
            self.logger.error(f"Erreur création client {source_type}: {str(e)}")
            return None

    async def _initialize_qdrant_client(self):
        """Initialise le client Qdrant avec gestion d'erreurs robuste."""
        try:
            # Vérifier si le circuit qdrant est fermé
            if self.circuit_breakers["qdrant"].can_execute():
                try:
                    # Configuration complète du client
                    from qdrant_client import QdrantClient
                    qdrant_url = os.getenv('QDRANT_URL')
                    qdrant_api_key = os.getenv('QDRANT_API_KEY')
                    
                    if not qdrant_url:
                        raise ValueError("Variable d'environnement QDRANT_URL non définie")
                    
                    self.logger.info(f"Connexion à Qdrant: {qdrant_url}")
                    self.qdrant_client = QdrantClient(
                        url=qdrant_url,
                        api_key=qdrant_api_key,
                        timeout=30  # Timeout augmenté
                    )
                    
                    # Test de connexion
                    collections = self.qdrant_client.get_collections()
                    self.logger.info(f"Connexion Qdrant réussie. Collections disponibles: {len(collections.collections) if hasattr(collections, 'collections') else 'inconnu'}")
                    self.circuit_breakers["qdrant"].record_success()
                    
                except Exception as e:
                    self.circuit_breakers["qdrant"].record_failure()
                    self.logger.error(f"Erreur connexion Qdrant: {str(e)}")
                    raise
            else:
                self.logger.warning("Circuit Qdrant ouvert, utilisation du client minimal")
                
        except Exception as e:
            self.logger.error(f"Erreur d'initialisation Qdrant, création d'un client minimal: {str(e)}")
            
        # Créer un client minimal en cas d'échec (toujours, pour garantir un fallback)
        if not self.qdrant_client:
            self.logger.warning("Utilisation d'un client Qdrant minimal (fallback)")
            # Création d'un objet qui implémente les méthodes minimales requises
            from types import SimpleNamespace
            self.qdrant_client = SimpleNamespace()
            self.qdrant_client.get_collections = lambda: SimpleNamespace(collections=[])
            self.qdrant_client.search = lambda **kwargs: []
            
    async def _initialize_openai_client(self):
        """Initialise le client OpenAI avec gestion d'erreurs robuste."""
        try:
            # Vérifier si le circuit openai est fermé
            if self.circuit_breakers["openai"].can_execute():
                try:
                    # Configuration complète du client
                    from openai import AsyncOpenAI
                    openai_api_key = os.getenv('OPENAI_API_KEY')
                    
                    if not openai_api_key:
                        raise ValueError("Variable d'environnement OPENAI_API_KEY non définie")
                    
                    self.logger.info("Initialisation du client OpenAI")
                    self.openai_client = AsyncOpenAI(
                        api_key=openai_api_key,
                        timeout=30.0  # Timeout explicite
                    )
                    
                    # Un test simple serait idéal ici, mais nous le ferons lors de la première utilisation
                    self.circuit_breakers["openai"].record_success()
                    
                except Exception as e:
                    self.circuit_breakers["openai"].record_failure()
                    self.logger.error(f"Erreur initialisation OpenAI client: {str(e)}")
                    raise
            else:
                self.logger.warning("Circuit OpenAI ouvert, utilisation du client minimal")
                
        except Exception as e:
            self.logger.error(f"Erreur d'initialisation OpenAI, création d'un client minimal: {str(e)}")
            
        # Créer un client minimal en cas d'échec (toujours, pour garantir un fallback)
        if not self.openai_client:
            self.logger.warning("Utilisation d'un client OpenAI minimal (fallback)")
            # Création d'un client avec une clé factice
            self.openai_client = AsyncOpenAI(api_key="dummy-key-for-fallback-initialization")
            
    async def _initialize_services(self):
        """Initialise les services d'embedding et de traduction."""
        try:
            # Import des classes en local pour éviter les problèmes d'import circulaire
            from embedding_service import EmbeddingService
            from translation_service import TranslationService
                
            if not self.embedding_service:
                self.embedding_service = EmbeddingService(
                    openai_client=self.openai_client,
                    model='text-embedding-ada-002',
                    l2_cache=global_cache
                )
                
            if not self.translation_service:
                self.translation_service = TranslationService(
                    openai_client=self.openai_client,
                    cache=global_cache
                )
                
        except Exception as e:
            self.logger.error(f"Erreur initialisation des services: {str(e)}")
            # Création de services minimaux en cas d'échec
            if not self.embedding_service:
                self.embedding_service = self._create_fallback_embedding_service()
            if not self.translation_service:
                self.translation_service = self._create_fallback_translation_service()
    
    async def _initialize_client(self, client_type: str, collection_name: str, fallback_enabled: bool = True):
        """
        Initialise un client de recherche spécifique avec gestion des erreurs.
        
        Args:
            client_type: Type de client à initialiser (jira, zendesk, etc.)
            collection_name: Nom de la collection à utiliser
            fallback_enabled: Si True, un client de fallback sera créé en cas d'erreur
            
        Returns:
            Le client initialisé ou None en cas d'échec
        """
        # Vérifications de base
        if not self.qdrant_client or not self.embedding_service:
            self.logger.error(f"Impossible d'initialiser le client {client_type}: dépendances manquantes")
            return None
            
        try:
            client_types = await self._get_client_types_safe()
            
            # Obtenir la classe du client
            client_class = client_types.get(client_type)
            if not client_class:
                self.logger.error(f"Type de client inconnu: {client_type}")
                return None
                
            # Créer l'instance avec les paramètres appropriés
            client = client_class(
                collection_name=collection_name,
                qdrant_client=self.qdrant_client,
                embedding_service=self.embedding_service,
                translation_service=self.translation_service
            )
            
            self.logger.info(f"Client {client_type} initialisé avec succès (collection: {collection_name})")
            return client
            
        except ImportError as e:
            self.logger.error(f"Erreur d'importation pour le client {client_type}: {str(e)}")
            self.circuit_breakers["client_import"].record_failure()
            if fallback_enabled:
                return self._create_fallback_client(client_type, collection_name)
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du client {client_type}: {str(e)}")
            self.circuit_breakers["client_creation"].record_failure()
            if fallback_enabled:
                return self._create_fallback_client(client_type, collection_name)
            return None
    
    def _create_fallback_client(self, client_type: str, collection_name: str):
        """
        Crée un client de fallback en cas d'échec d'initialisation du client principal.
        Utilise une implémentation simplifiée qui enregistre les erreurs mais ne bloque pas l'exécution.
        
        Args:
            client_type: Type de client pour lequel créer un fallback
            collection_name: Nom de la collection
            
        Returns:
            Un client de fallback minimal
        """
        # Import local pour éviter les cycles d'importation
        from search_base import AbstractSearchClient
        
        class FallbackSearchClient(AbstractSearchClient):
            def __init__(self, client_type, original_error, logger):
                self.client_type = client_type
                self.original_error = original_error
                self.logger = logger
                self.error_logged = False
                
            def get_source_name(self) -> str:
                return f"FALLBACK_{self.client_type.upper()}"
                
            async def recherche_intelligente(self, *args, **kwargs):
                if not self.error_logged:
                    self.logger.warning(f"Utilisation du client de fallback pour {self.client_type}")
                    self.error_logged = True
                return []
                
            def valider_resultat(self, result):
                return False
                
            async def format_for_slack(self, result):
                return None
        
        error_msg = f"Client {client_type} non disponible - utilisation du fallback"
        self.logger.warning(error_msg)
        
        fallback = FallbackSearchClient(client_type, error_msg, self.logger)
        self.logger.info(f"Client de fallback créé pour {client_type}")
        return fallback
    
    def _get_client_types(self):
        """Import dynamique des types de clients pour éviter les imports circulaires"""
        from search_clients import (
            JiraSearchClient,
            ZendeskSearchClient,
            ConfluenceSearchClient,
            NetsuiteSearchClient,
            NetsuiteDummiesSearchClient,
            SapSearchClient,
            ERPSearchClient
        )

        # Création des mappings vers les classes
        return {
            'jira': JiraSearchClient,
            'zendesk': ZendeskSearchClient,
            'confluence': ConfluenceSearchClient,
            'netsuite': NetsuiteSearchClient,
            'netsuite_dummies': NetsuiteDummiesSearchClient,
            'sap': SapSearchClient,
            'erp': ERPSearchClient
        }
    
    async def _get_client_types_safe(self):
        try:
            return self._get_client_types()
        except Exception as e:
            self.logger.error(f"Erreur import classes clients: {str(e)}")
            return self._get_fallback_client_types()
    
    def _get_fallback_client_types(self):
        """Crée des types de clients de repli en cas d'erreur d'import"""
        from search_base import AbstractSearchClient

        class DummySearchClient(AbstractSearchClient):
            async def format_for_slack(self, result):
                return {}

            def valider_resultat(self, result):
                return False
                
            async def search(self, *args, **kwargs):
                return []

        dummy_types = {source: DummySearchClient for source in self.default_collections.keys()}
        return dummy_types
    
    def get_circuit_breaker_status(self):
        """Retourne l'état de tous les circuit breakers pour monitoring"""
        return {name: cb.get_status() for name, cb in self.circuit_breakers.items()}
    
    def reset_circuit_breakers(self):
        """Réinitialise tous les circuit breakers"""
        for cb in self.circuit_breakers.values():
            cb.reset()
        return {"status": "reset", "count": len(self.circuit_breakers)}

    def _create_fallback_qdrant_client(self):
        """
        Crée un client Qdrant de fallback qui implémente l'interface minimale requise.
        Ce client simule les réponses sans effectuer de vraies requêtes pour permettre
        un fonctionnement dégradé de l'application.
        
        Returns:
            Un objet qui implémente l'interface minimale de QdrantClient
        """
        class FallbackQdrantClient:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                
            async def search(self, collection_name, **kwargs):
                if not self.error_logged:
                    self.logger.warning(f"Utilisation du client Qdrant de fallback pour {collection_name}")
                    self.error_logged = True
                return []
                
            def get_collections(self):
                return []
                
            def get_collection(self, collection_name):
                return {"status": "fallback"}
                
            async def create_payload_index(self, *args, **kwargs):
                return None
                
            async def upload_collection(self, *args, **kwargs):
                return None
                
            async def upload_points(self, *args, **kwargs):
                return None
                
            async def scroll(self, *args, **kwargs):
                return ([], None)
                
            def close(self):
                pass
                
        self.logger.info("Création d'un client Qdrant de fallback")
        return FallbackQdrantClient(self.logger)
        
    def _create_fallback_openai_client(self):
        """
        Crée un client OpenAI de fallback qui implémente l'interface minimale requise.
        Ce client simule les réponses sans effectuer de vraies requêtes API pour permettre
        un fonctionnement dégradé de l'application.
        
        Returns:
            Un objet qui implémente l'interface minimale d'AsyncOpenAI
        """
        class FallbackEmbeddingsClient:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                
            async def create(self, *args, **kwargs):
                if not self.error_logged:
                    self.logger.warning("Utilisation du client Embeddings de fallback")
                    self.error_logged = True
                return {"data": [{"embedding": [0.0] * 384}], "model": "fallback-model"}
                
        class FallbackChatClient:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                
            async def create(self, *args, **kwargs):
                if not self.error_logged:
                    self.logger.warning("Utilisation du client Chat de fallback")
                    self.error_logged = True
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "Je ne peux pas répondre pour le moment car le service est indisponible."
                            },
                            "finish_reason": "fallback"
                        }
                    ],
                    "model": "fallback-model"
                }
        
        class FallbackOpenAIClient:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                self.embeddings = FallbackEmbeddingsClient(logger)
                self.chat = FallbackChatClient(logger)
                
        self.logger.info("Création d'un client OpenAI de fallback")
        return FallbackOpenAIClient(self.logger)
        
    def _create_fallback_embedding_service(self):
        """
        Crée un service d'embedding de fallback qui implémente l'interface minimale requise.
        
        Returns:
            Un objet qui implémente l'interface minimale d'EmbeddingService
        """
        class FallbackEmbeddingService:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                self.metrics = {
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "api_calls": 0,
                    "errors": 0,
                    "total_requests": 0
                }
                self.circuit_breaker = CircuitBreaker("embedding_fallback")
                
            async def get_embedding(self, text, force_refresh=False):
                if not self.error_logged:
                    self.logger.warning("Utilisation du service Embedding de fallback")
                    self.error_logged = True
                
                self.metrics["total_requests"] += 1
                self.metrics["cache_hits"] += 1  # Simuler un hit de cache
                
                return [0.0] * 384  # Vecteur d'embedding nul de dimension 384
                
            def _get_cache_key(self, text):
                return hash(text)
            
            def get_metrics(self):
                """Retourne les métriques du service."""
                return self.metrics
            
            def reset_metrics(self):
                """Réinitialise les métriques."""
                self.metrics = {
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "api_calls": 0,
                    "errors": 0,
                    "total_requests": 0
                }
                
            async def warm_cache(self, texts):
                """Simule un préchauffage du cache."""
                self.logger.info(f"Simulation de préchauffage du cache pour {len(texts)} textes")
                return len(texts)
                
        self.logger.info("Création d'un service Embedding de fallback")
        return FallbackEmbeddingService(self.logger)
        
    def _create_fallback_translation_service(self):
        """
        Crée un service de traduction de fallback qui implémente l'interface minimale requise.
        
        Returns:
            Un objet qui implémente l'interface minimale de TranslationService
        """
        class FallbackTranslationService:
            def __init__(self, logger):
                self.logger = logger
                self.error_logged = False
                
            async def detect_language(self, text):
                return "fr"
                
            async def translate(self, text, target_lang="en"):
                if not self.error_logged:
                    self.logger.warning("Utilisation du service Translation de fallback")
                    self.error_logged = True
                return text  # On retourne le texte tel quel
                
        self.logger.info("Création d'un service Translation de fallback")
        return FallbackTranslationService(self.logger)
    
# Instance globale
search_factory = SearchClientFactory()