"""
Module factory - Factory pour la création et gestion des clients de recherche
"""

import os
import logging
import time
import asyncio
from typing import Dict, Optional, Callable, Any

# Configuration du logger
logger = logging.getLogger('ITS_HELP.search.factory')

# Import des classes de base (en évitant les importations circulaires)
# Ces importations sont faites à l'utilisation pour éviter les problèmes
from search.core.client_base import AbstractSearchClient, GenericSearchClient  # noqa: E402

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

        # Collections par défaut - chargées depuis les variables d'environnement ou config.py
        self.default_collections = {}
        self._load_default_collections()
        
    def _load_default_collections(self):
        """Charge les collections par défaut depuis les variables d'environnement ou config.py"""
        # Essayer d'abord de charger depuis config.py
        try:
            # Import conditionnel pour éviter les problèmes d'importation circulaire
            import config
            if hasattr(config, 'COLLECTIONS') and isinstance(config.COLLECTIONS, dict):
                self.default_collections = config.COLLECTIONS
                self.logger.info(f"Collections chargées depuis config.py: {len(self.default_collections)} collections")
                return
        except (ImportError, AttributeError):
            self.logger.debug("Impossible de charger les collections depuis config.py")
            
        # Fallback: charger depuis les variables d'environnement
        collection_types = [
            'jira', 'zendesk', 'confluence', 'netsuite', 
            'netsuite_dummies', 'sap', 'erp'
        ]
        
        for col_type in collection_types:
            env_var = f'QDRANT_COLLECTION_{col_type.upper()}'
            collection = os.getenv(env_var, col_type.upper())
            self.default_collections[col_type] = collection
            
        self.logger.info(f"Collections chargées depuis les variables d'environnement: {len(self.default_collections)} collections")

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
        client_names = list(self.default_collections.keys())
        
        initialization_tasks = [
            self._initialize_client(client_type, self.default_collections.get(client_type, client_type))
            for client_type in client_names
        ]
        
        # Exécution parallèle des initialisations
        results = await asyncio.gather(*initialization_tasks, return_exceptions=True)
        
        # Traitement des résultats
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
        success_count = sum(1 for client in self.clients.values() if client is not None)
        self.logger.info(f"Factory initialisée: {success_count}/{len(client_names)} clients OK")
        self.initialized = True

    async def _initialize_qdrant_client(self):
        """Initialise le client Qdrant"""
        try:
            circuit = self.circuit_breakers["qdrant"]
            
            async def init_qdrant():
                from qdrant_client import QdrantClient
                
                qdrant_url = os.getenv('QDRANT_URL')
                qdrant_api_key = os.getenv('QDRANT_API_KEY')
                
                if not qdrant_url:
                    raise ValueError("QDRANT_URL n'est pas défini dans les variables d'environnement")
                    
                self.logger.info(f"Connexion à Qdrant: {qdrant_url}")
                client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
                
                # Vérifier que le client fonctionne
                collections = client.get_collections()
                self.logger.info(f"Connexion Qdrant réussie - collections disponibles: {len(collections.collections)}")
                
                return client
            
            self.qdrant_client = await with_circuit_breaker(
                circuit, 
                init_qdrant,
                fallback=lambda: self._create_fallback_qdrant_client()
            )
            
        except Exception as e:
            self.logger.error(f"Erreur initialisation QdrantClient: {str(e)}")
            self.qdrant_client = None

    async def _initialize_openai_client(self):
        """Initialise le client OpenAI"""
        try:
            circuit = self.circuit_breakers["openai"]
            
            async def init_openai():
                # Import conditionnel pour éviter les problèmes d'importation
                from openai import OpenAI
                
                api_key = os.getenv('OPENAI_API_KEY')
                
                if not api_key:
                    raise ValueError("OPENAI_API_KEY n'est pas défini dans les variables d'environnement")
                
                self.logger.info("Initialisation du client OpenAI")
                client = OpenAI(api_key=api_key)
                
                # Vérifier que le client fonctionne avec un appel simple
                client.models.list()  # Vérification que le client est bien initialisé
                self.logger.info("Client OpenAI initialisé avec succès")
                
                return client
            
            self.openai_client = await with_circuit_breaker(
                circuit, 
                init_openai,
                fallback=lambda: self._create_fallback_openai_client()
            )
            
        except Exception as e:
            self.logger.error(f"Erreur initialisation OpenAI client: {str(e)}")
            self.openai_client = None

    async def _initialize_services(self):
        """Initialise les services auxiliaires (embedding, traduction)"""
        # Import conditionnel pour éviter les problèmes d'importation
        try:
            # Initialisation du service d'embedding
            from search.utils.embedding_service import EmbeddingService
            self.embedding_service = EmbeddingService(self.openai_client)
            
            # Initialisation du service de traduction (optionnel)
            try:
                from search.utils.translation_service import TranslationService
                self.translation_service = TranslationService(self.openai_client)
            except (ImportError, Exception) as e:
                self.logger.warning(f"Service de traduction non disponible: {str(e)}")
                self.translation_service = None
                
        except Exception as e:
            self.logger.error(f"Erreur initialisation services: {str(e)}")
            self.embedding_service = None
            self.translation_service = None

    async def _initialize_client(self, client_type: str, collection_name: str):
        """
        Initialise un client de recherche spécifique.
        
        Args:
            client_type: Type de client à initialiser (ex: jira, zendesk)
            collection_name: Nom de la collection à utiliser
            
        Returns:
            Instance du client initialisé ou None en cas d'erreur
        """
        try:
            circuit = self.circuit_breakers["client_creation"]
            
            async def create_client():
                # Déterminer la classe à instancier en fonction du type
                client_class = await self._get_client_class(client_type)
                
                if not client_class:
                    raise ValueError(f"Aucune classe de client trouvée pour {client_type}")
                
                # Création du client avec les dépendances appropriées
                client = client_class(
                    collection_name=collection_name,
                    qdrant_client=self.qdrant_client,
                    embedding_service=self.embedding_service,
                    translation_service=self.translation_service
                )
                
                self.logger.info(f"Client {client_type} initialisé avec succès: {client.__class__.__name__}")
                return client
            
            return await with_circuit_breaker(
                circuit, 
                create_client,
                fallback=lambda: self._create_fallback_client(client_type, collection_name)
            )
            
        except Exception as e:
            self.logger.error(f"Erreur initialisation client {client_type}: {str(e)}")
            return None

    async def _get_client_class(self, client_type: str):
        """
        Détermine la classe de client à utiliser en fonction du type.
        
        Args:
            client_type: Type de client (ex: jira, zendesk)
            
        Returns:
            Classe de client ou None si non trouvée
        """
        # Utiliser le circuit breaker pour les importations de modules
        circuit = self.circuit_breakers["client_import"]
        
        async def import_client_class():
            # Import des classes de client en fonction du type
            # Pour éviter les problèmes d'importation, effectuer les imports ici
            
            if client_type == "jira":
                from search.clients.jira_client import JiraSearchClient
                return JiraSearchClient
                
            elif client_type == "zendesk":
                from search.clients.zendesk_client import ZendeskSearchClient
                return ZendeskSearchClient
                
            elif client_type == "confluence":
                from search.clients.confluence_client import ConfluenceSearchClient
                return ConfluenceSearchClient
                
            elif client_type == "netsuite":
                from search.clients.netsuite_client import NetsuiteSearchClient
                return NetsuiteSearchClient
                
            elif client_type == "netsuite_dummies":
                from search.clients.netsuite_dummies_client import NetsuiteDummiesSearchClient
                return NetsuiteDummiesSearchClient
                
            elif client_type == "sap":
                from search.clients.sap_client import SapSearchClient
                return SapSearchClient
                
            elif client_type == "erp":
                from search.clients.erp_client import ERPSearchClient
                return ERPSearchClient
                
            # Fallback à la classe générique
            self.logger.warning(f"Aucune classe spécifique pour {client_type}, utilisation de GenericSearchClient")
            return GenericSearchClient
        
        try:
            return await with_circuit_breaker(
                circuit, 
                import_client_class,
                fallback=lambda: GenericSearchClient
            )
        except Exception as e:
            self.logger.error(f"Erreur import client {client_type}: {str(e)}")
            return GenericSearchClient

    def _create_fallback_qdrant_client(self):
        """Crée un client Qdrant de fallback en cas d'erreur"""
        self.logger.warning("Création d'un client Qdrant de fallback (mock)")
        
        # Création d'un mock minimal pour simuler le client Qdrant
        class QdrantClientMock:
            def __init__(self):
                self.logger = logging.getLogger('ITS_HELP.qdrant_mock')
                
            def search(self, collection_name, query_vector, **kwargs):
                self.logger.warning("Recherche simulée dans " + collection_name + " (mock)")
                return []
                
            def query_points(self, collection_name, query_vector, **kwargs):
                self.logger.warning("Recherche simulée dans " + collection_name + " (mock)")
                return []
                
            def get_collections(self):
                class Collections:
                    def __init__(self):
                        self.collections = []
                return Collections()
        
        return QdrantClientMock()

    def _create_fallback_openai_client(self):
        """Crée un client OpenAI de fallback en cas d'erreur"""
        self.logger.warning("Création d'un client OpenAI de fallback (mock)")
        
        # Création d'un mock minimal pour simuler le client OpenAI
        class OpenAIClientMock:
            def __init__(self):
                self.logger = logging.getLogger('ITS_HELP.openai_mock')
                
            def embedding(self, input, model="text-embedding-ada-002"):
                self.logger.warning("Génération d'embedding simulée (mock)")
                # Retourner un vecteur factice
                return {"data": [{"embedding": [0.1] * 1536}]}
                
        return OpenAIClientMock()

    def _create_fallback_embedding_service(self):
        """Crée un service d'embedding de fallback en cas d'erreur"""
        self.logger.warning("Création d'un service d'embedding de fallback (mock)")
        
        # Création d'un mock minimal pour simuler le service d'embedding
        class EmbeddingServiceMock:
            def __init__(self):
                self.logger = logging.getLogger('ITS_HELP.embedding_mock')
                
            async def get_embedding(self, text):
                self.logger.warning("Génération d'embedding simulée pour '" + text[:20] + "...' (mock)")
                # Retourner un vecteur factice
                return [0.1] * 1536
                
        return EmbeddingServiceMock()

    def _create_fallback_translation_service(self):
        """Crée un service de traduction de fallback en cas d'erreur"""
        self.logger.warning("Création d'un service de traduction de fallback (mock)")
        
        # Création d'un mock minimal pour simuler le service de traduction
        class TranslationServiceMock:
            def __init__(self):
                self.logger = logging.getLogger('ITS_HELP.translation_mock')
                
            async def translate(self, text, source_lang="auto", target_lang="fr"):
                self.logger.warning("Traduction simulée pour '" + text[:20] + "...' (mock)")
                # Retourner le texte original
                return text
                
        return TranslationServiceMock()

    def _create_fallback_client(self, client_type: str, collection_name: str):
        """
        Crée un client de recherche de fallback en cas d'erreur.
        
        Args:
            client_type: Type de client (ex: jira, zendesk)
            collection_name: Nom de la collection
            
        Returns:
            Client de fallback
        """
        self.logger.warning("Création d'un client de fallback pour " + client_type)
        
        # Création d'un client générique de fallback
        class FallbackSearchClient(GenericSearchClient):
            def __init__(self, collection_name, client_type, factory):
                super().__init__(
                    collection_name=collection_name,
                    qdrant_client=factory._create_fallback_qdrant_client(),
                    embedding_service=factory._create_fallback_embedding_service()
                )
                self.client_type = client_type
                self.logger = logging.getLogger('ITS_HELP.fallback.' + client_type)
                
            def get_source_name(self):
                return "FALLBACK_" + self.client_type.upper()
                
            async def recherche_intelligente(self, question, **kwargs):
                self.logger.warning("Recherche fallback dans " + self.collection_name + " pour '" + question[:30] + "...'")
                return []
        
        return FallbackSearchClient(collection_name, client_type, self)

    def adapt_legacy_client(self, client: Any, client_type: str) -> AbstractSearchClient:
        """
        Adapte un client legacy à l'interface standard.
        
        Args:
            client: Client legacy à adapter
            client_type: Type de client
            
        Returns:
            Client adapté
        """
        # Cette méthode permet d'adapter des clients existants à la nouvelle interface
        # si nécessaire, en utilisant un adaptateur spécifique
        
        # Vérifier si le client est déjà compatible
        if isinstance(client, AbstractSearchClient):
            return client
            
        # Utiliser un adaptateur pour les clients legacy
        return QdrantSearchClientAdapter(
            wrapped_client=client,
            embedding_service=self.embedding_service,
            logger=logging.getLogger('ITS_HELP.adapter.' + client_type)
        )

    async def get_client(self, client_type: str) -> Optional[AbstractSearchClient]:
        """
        Récupère un client de recherche par type.
        
        Args:
            client_type: Type de client à récupérer (ex: jira, zendesk)
            
        Returns:
            Instance du client ou None si non disponible
        """
        # Si la factory n'est pas initialisée, le faire maintenant
        if not self.initialized:
            await self.initialize()
            
        # Récupérer le client s'il existe déjà
        if client_type in self.clients:
            return self.clients[client_type]
            
        # Si le client n'existe pas, essayer de l'initialiser
        try:
            collection_name = self.default_collections.get(client_type, client_type)
            client = await self._initialize_client(client_type, collection_name)
            
            if client:
                self.clients[client_type] = client
                return client
                
            # En cas d'échec, créer un client de fallback
            self.logger.warning("Impossible d'initialiser " + client_type + ", utilisation d'un fallback")
            fallback = self._create_fallback_client(client_type, collection_name)
            self.clients[client_type] = fallback
            return fallback
            
        except Exception as e:
            self.logger.error("Erreur récupération client " + client_type + ": " + str(e))
            return None

    async def get_all_clients(self) -> Dict[str, AbstractSearchClient]:
        """
        Récupère tous les clients disponibles.
        
        Returns:
            Dictionnaire {type: client}
        """
        # Si la factory n'est pas initialisée, le faire maintenant
        if not self.initialized:
            await self.initialize()
            
        return self.clients


class QdrantSearchClientAdapter(AbstractSearchClient):
    """Adaptateur pour les clients Qdrant legacy"""
    
    def __init__(self, wrapped_client, embedding_service, logger):
        """
        Initialise l'adaptateur avec le client à adapter.
        
        Args:
            wrapped_client: Client à adapter
            embedding_service: Service d'embedding
            logger: Logger à utiliser
        """
        self.wrapped_client = wrapped_client
        self.embedding_service = embedding_service
        self.logger = logger
        
        # Déterminer si le client est compatible avec l'interface standard
        self.has_recherche_intelligente = hasattr(wrapped_client, 'recherche_intelligente')
        self.has_recherche_similaire = hasattr(wrapped_client, 'recherche_similaire')
        self.has_recherche_filtree = hasattr(wrapped_client, 'recherche_avec_filtres')
        
    def get_source_name(self) -> str:
        """Délègue l'appel au client sous-jacent"""
        if hasattr(self.wrapped_client, 'get_source_name'):
            return self.wrapped_client.get_source_name()
        return "ADAPTED_CLIENT"
        
    def valider_resultat(self, result: Any) -> bool:
        """Délègue l'appel au client sous-jacent ou implémente un comportement par défaut"""
        if hasattr(self.wrapped_client, 'valider_resultat'):
            return self.wrapped_client.valider_resultat(result)
        
        # Implémentation par défaut
        if not result:
            return False
            
        # Vérifier les attributs de base
        return hasattr(result, 'score') and hasattr(result, 'payload')
        
    async def recherche_intelligente(self, question: str, **kwargs):
        """
        Délègue l'appel au client sous-jacent ou adapte l'appel si nécessaire.
        
        Args:
            question: Question à rechercher
            **kwargs: Arguments additionnels
            
        Returns:
            Résultats de la recherche
        """
        try:
            # Si le client a déjà la méthode recherche_intelligente, l'utiliser directement
            if self.has_recherche_intelligente:
                return await self.wrapped_client.recherche_intelligente(question=question, **kwargs)
                
            # Sinon, adapter l'appel aux méthodes disponibles
            
            # Générer l'embedding pour la question
            vector = await self.embedding_service.get_embedding(question)
            
            # Adapter les arguments pour les filtres
            client_name = kwargs.get('client_name')
            limit = kwargs.get('limit', 10)
            
            filtres = {
                'client_name': client_name,
                'date_debut': kwargs.get('date_debut'),
                'date_fin': kwargs.get('date_fin')
            }
            
            # Appeler la méthode appropriée
            if self.has_recherche_filtree:
                return await self.wrapped_client.recherche_avec_filtres(
                    query_vector=vector,
                    filtres=filtres,
                    limit=limit
                )
            elif self.has_recherche_similaire:
                return await self.wrapped_client.recherche_similaire(
                    query_vector=vector,
                    limit=limit
                )
            else:
                self.logger.error("Client incompatible: aucune méthode de recherche disponible")
                return []
                
        except Exception as e:
            self.logger.error("Erreur dans l'adaptateur: " + str(e))
            return []
            
    async def format_for_slack(self, result: Any):
        """Délègue l'appel au client sous-jacent"""
        if hasattr(self.wrapped_client, 'format_for_slack'):
            return await self.wrapped_client.format_for_slack(result)
        
        # Implémentation par défaut
        return None


# Instance globale de la factory
search_factory = SearchClientFactory()
