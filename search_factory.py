# À ajouter dans un fichier search_factory.py

import os
import asyncio
import logging
from typing import Dict, Optional

from qdrant_client import QdrantClient
from openai import AsyncOpenAI

from search_base import AbstractSearchClient
from search_clients import (
    JiraSearchClient, 
    ZendeskSearchClient, 
    ConfluenceSearchClient, 
    NetsuiteSearchClient,
    NetsuiteDummiesSearchClient,
    SapSearchClient
)
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
        
        # Mapping des types de recherche vers les classes
        self.client_types = {
            'jira': JiraSearchClient,
            'zendesk': ZendeskSearchClient,
            'confluence': ConfluenceSearchClient,
            'netsuite': NetsuiteSearchClient,
            'netsuite_dummies': NetsuiteDummiesSearchClient,
            'sap': SapSearchClient
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
    
    async def get_client(self, source_type: str) -> Optional[AbstractSearchClient]:
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
            
        # Vérification du type supporté
        if source_type not in self.client_types:
            self.logger.warning(f"Type de source non pris en charge: {source_type}")
            return None
            
        # Récupération de la collection
        collection_name = self.default_collections.get(source_type)
        if not collection_name:
            self.logger.warning(f"Pas de collection configurée pour {source_type}")
            return None
            
        # Création du client
        try:
            client_class = self.client_types[source_type]
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
    
    async def get_clients(self, source_types: list) -> Dict[str, AbstractSearchClient]:
        # S'assurer que le factory est initialisé
        if not self.initialized:
            await self.initialize()
            
        # Solution: utiliser directement les coroutines sans create_task
        tasks = [self.get_client(source_type) for source_type in source_types]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        clients = {}
        for source_type, result in zip(source_types, results):
            if isinstance(result, Exception):
                self.logger.error(f"Erreur récupération client {source_type}: {str(result)}")
            elif result:
                clients[source_type] = result
                
        return clients
    
    async def search_all(self, question: str, client_name=None, date_debut=None, date_fin=None, limit_per_source=3):
        """
        Effectue une recherche sur toutes les sources disponibles.
        
        Args:
            question: Question à rechercher
            client_name: Information sur le client (optionnel)
            date_debut: Date de début pour filtrage (optionnel)
            date_fin: Date de fin pour filtrage (optionnel)
            limit_per_source: Nombre maximum de résultats par source
            
        Returns:
            Dictionnaire des résultats par source
        """
        # Initialisation si nécessaire
        if not self.initialized:
            await self.initialize()
            
        # Récupération de tous les clients
        clients = await self.get_clients(self.default_collections.keys())
        
        # Exécution des recherches en parallèle
        async def search_source(source_type, client):
            try:
                results = await client.recherche_intelligente(
                    question=question,
                    client_name=client_name,
                    date_debut=date_debut,
                    date_fin=date_fin
                )
                return source_type, results[:limit_per_source]
            except Exception as e:
                self.logger.error(f"Erreur recherche {source_type}: {str(e)}")
                return source_type, []
                
        tasks = [search_source(source_type, client) for source_type, client in clients.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Traitement des résultats
        all_results = {}
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Erreur recherche: {str(result)}")
                continue
                
            source_type, source_results = result
            all_results[source_type] = source_results
            
        return all_results
    
    def get_legacy_client(self, source_type: str):
        """
        Fonction de compatibilité pour obtenir un client legacy.
        À utiliser pendant la transition vers la nouvelle architecture.
        """
        if source_type.lower() == 'jira':
            from qdrant_jira import QdrantJiraSearch
            return QdrantJiraSearch(collection_name=self.default_collections['jira'])
        elif source_type.lower() == 'zendesk':
            from qdrant_zendesk import QdrantZendeskSearch
            return QdrantZendeskSearch(collection_name=self.default_collections['zendesk'])
# Instance globale
search_factory = SearchClientFactory()