# search_factory.py

import os
import asyncio
import logging
from typing import Dict, Optional

from qdrant_client import QdrantClient
from openai import AsyncOpenAI

from search_base import AbstractSearchClient
# Import dynamique pour éviter les imports circulaires

from configuration import logger, global_cache
from embedding_service import EmbeddingService
from translation_service import TranslationService

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
            # Création des clients de base
            try:
                self.qdrant_client = QdrantClient(
                    url=os.getenv('QDRANT_URL'),
                    api_key=os.getenv('QDRANT_API_KEY'),
                    timeout=30  # Timeout augmenté
                )
            except Exception as e:
                self.logger.error(f"Erreur connexion Qdrant: {str(e)}")
                # Créer un client minimal même en cas d'échec pour éviter les blocages
                self.qdrant_client = object()
                self.qdrant_client.get_collections = lambda: None

            try:
                self.openai_client = AsyncOpenAI(
                    api_key=os.getenv('OPENAI_API_KEY'),
                    timeout=30.0  # Timeout explicite
                )
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

        # Obtention dynamique des types de clients
        client_types = self._get_client_types()

        # Vérification du type supporté
        if source_type not in client_types:
            self.logger.warning(f"Type de source non pris en charge: {source_type}")
            return None

        # Récupération de la collection
        collection_name = self.default_collections.get(source_type)
        if not collection_name:
            self.logger.warning(f"Pas de collection configurée pour {source_type}")
            return None

        # Création du client
        try:
            client_class = client_types[source_type]
            client = client_class(
                collection_name=collection_name,
                qdrant_client=self.qdrant_client,
                embedding_service=self.embedding_service,
                translation_service=self.translation_service
            )

            # Mise en cache
            self.clients[source_type] = client
            return client

        except Exception as e:
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
            # Créer une classe de repli
            from search_base import AbstractSearchClient

            class DummySearchClient(AbstractSearchClient):
                async def format_for_slack(self, result):
                    return {}

                def valider_resultat(self, result):
                    return False

            dummy_types = {source: DummySearchClient for source in self.default_collections.keys()}
            return dummy_types

# Instance globale
search_factory = SearchClientFactory()