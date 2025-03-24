# search_factory.py

import os
import logging
import time
from typing import Optional, Callable

from qdrant_client import QdrantClient
from openai import AsyncOpenAI

from configuration import logger, global_cache
from embedding_service import EmbeddingService
from translation_service import TranslationService

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
            'sap': os.getenv('QDRANT_COLLECTION_SAP', 'SAP')
        }

    async def initialize(self):
        """Initialisation des services et clients de base."""
        if self.initialized:
            return

        try:
            # Création des clients de base avec circuit breaker
            try:
                # Vérifier si le circuit qdrant est fermé
                if self.circuit_breakers["qdrant"].can_execute():
                    try:
                        self.qdrant_client = QdrantClient(
                            url=os.getenv('QDRANT_URL'),
                            api_key=os.getenv('QDRANT_API_KEY'),
                            timeout=30  # Timeout augmenté
                        )
                        # Test de connexion
                        self.qdrant_client.get_collections()
                        self.circuit_breakers["qdrant"].record_success()
                    except Exception as e:
                        self.circuit_breakers["qdrant"].record_failure()
                        self.logger.error(f"Erreur connexion Qdrant: {str(e)}")
                        raise
                else:
                    self.logger.warning("Circuit Qdrant ouvert, utilisation du client minimal")
                    
                # Créer un client minimal en cas d'échec
                if not self.qdrant_client:
                    self.qdrant_client = object()
                    self.qdrant_client.get_collections = lambda: None
            except Exception as e:
                self.logger.error(f"Erreur connexion Qdrant: {str(e)}")
                # Créer un client minimal même en cas d'échec pour éviter les blocages
                self.qdrant_client = object()
                self.qdrant_client.get_collections = lambda: None

            try:
                # Vérifier si le circuit openai est fermé
                if self.circuit_breakers["openai"].can_execute():
                    try:
                        self.openai_client = AsyncOpenAI(
                            api_key=os.getenv('OPENAI_API_KEY'),
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
                    
                # Créer un client minimal en cas d'échec
                if not self.openai_client:
                    self.openai_client = AsyncOpenAI(api_key="dummy-key-for-initialization")
            except Exception as e:
                self.logger.error(f"Erreur initialisation OpenAI client: {str(e)}")
                # Créer un client minimal en cas d'échec
                self.openai_client = AsyncOpenAI(api_key="dummy-key-for-initialization")

            # Création des services avec gestion d'erreurs
            try:
                self.embedding_service = EmbeddingService(
                    openai_client=self.openai_client,
                    cache=global_cache
                )
            except Exception as e:
                self.logger.error(f"Erreur initialisation EmbeddingService: {str(e)}")
                # Créer un service minimal
                self.embedding_service = object()
                self.embedding_service.get_embedding = lambda text, **kwargs: []

            try:
                self.translation_service = TranslationService(
                    openai_client=None,  # Client synchrone non nécessaire
                    cache=global_cache
                )
                self.translation_service.set_async_client(self.openai_client)
            except Exception as e:
                self.logger.error(f"Erreur initialisation TranslationService: {str(e)}")
                # Créer un service minimal
                self.translation_service = object()
                self.translation_service.translate = lambda text, **kwargs: text

            # Marquer comme initialisé même en cas d'erreurs partielles
            self.initialized = True
            self.logger.info("SearchClientFactory initialisé avec mode dégradé si nécessaire")

        except Exception as e:
            self.logger.error(f"Erreur initialisation SearchClientFactory: {str(e)}")
            # Rendre les attributs disponibles même en cas d'erreur
            if not hasattr(self, 'qdrant_client'):
                self.qdrant_client = None
            if not hasattr(self, 'openai_client'):
                self.openai_client = None
            if not hasattr(self, 'embedding_service'):
                self.embedding_service = None
            if not hasattr(self, 'translation_service'):
                self.translation_service = None
            # Marquer comme initialisé pour éviter les blocages
            self.initialized = True

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
                client_types = self._get_client_types()
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

    def _get_client_types(self):
        """Import dynamique des types de clients pour éviter les imports circulaires"""
        try:
            from search_clients import (
                JiraSearchClient,
                ZendeskSearchClient,
                ConfluenceSearchClient,
                NetsuiteSearchClient,
                NetsuiteDummiesSearchClient,
                SapSearchClient
            )

            # Création des mappings vers les classes
            return {
                'jira': JiraSearchClient,
                'zendesk': ZendeskSearchClient,
                'confluence': ConfluenceSearchClient,
                'netsuite': NetsuiteSearchClient,
                'netsuite_dummies': NetsuiteDummiesSearchClient,
                'sap': SapSearchClient
            }
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

# Instance globale
search_factory = SearchClientFactory()