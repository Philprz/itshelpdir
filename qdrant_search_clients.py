"""
Module qdrant_search_clients - Factory pour les clients de recherche Qdrant

Ce module définit la factory pour créer des clients de recherche
spécialisés utilisant Qdrant comme base de données vectorielle.
"""

import os
import logging
from typing import Dict, Any, Optional

# Import sécurisé pour éviter les erreurs d'importation circulaire
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

logger = logging.getLogger('ITS_HELP.qdrant_search_clients')

class QdrantSearchClientFactory:
    """
    Factory pour la création des clients de recherche Qdrant.
    """
    
    def __init__(self, qdrant_url: str, openai_api_key: str, qdrant_api_key: str = None):
        """
        Initialise la factory avec les paramètres de connexion.
        
        Args:
            qdrant_url: URL du serveur Qdrant
            openai_api_key: Clé API OpenAI
            qdrant_api_key: Clé API Qdrant (optionnelle)
        """
        self.qdrant_url = qdrant_url
        self.openai_api_key = openai_api_key
        self.qdrant_api_key = qdrant_api_key
        self.logger = logger
        
        # Vérifier si les dépendances sont disponibles
        if not QDRANT_AVAILABLE:
            self.logger.error("Impossible d'importer qdrant_client. Assurez-vous que la bibliothèque est installée.")
        
        # Initialiser le client Qdrant
        try:
            self.qdrant_client = self._init_qdrant_client()
            self.logger.info(f"Client Qdrant initialisé avec succès sur {qdrant_url}")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du client Qdrant: {str(e)}")
            self.qdrant_client = None
        
        # Initialiser les services d'embedding et de traduction
        try:
            from embedding_service_compat import EmbeddingService
            from translation_service_compat import TranslationService
            from configuration import global_cache
            
            # Client OpenAI
            try:
                from openai import AsyncOpenAI
                openai_client = AsyncOpenAI(api_key=openai_api_key)
                self.logger.info("Client OpenAI initialisé avec succès")
            except Exception as e:
                self.logger.error(f"Erreur lors de l'initialisation du client OpenAI: {str(e)}")
                openai_client = None
                
            # Services
            self.embedding_service = EmbeddingService(openai_client, global_cache)
            self.translation_service = TranslationService(None, global_cache)
            if openai_client:
                self.translation_service.set_async_client(openai_client)
            self.logger.info("Services d'embedding et de traduction initialisés")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation des services: {str(e)}")
            self.embedding_service = None
            self.translation_service = None
    
    def _init_qdrant_client(self):
        """
        Initialise le client Qdrant en fonction des paramètres.
        
        Returns:
            Client Qdrant initialisé
        """
        if not QDRANT_AVAILABLE:
            return None
            
        if not self.qdrant_url:
            self.logger.error("URL Qdrant non spécifiée")
            return None
            
        # Déterminer si l'URL est locale ou distante
        is_local = self.qdrant_url.startswith("http://localhost") or self.qdrant_url.startswith("http://127.0.0.1")
        
        # Créer le client adapté
        try:
            if is_local:
                # Client local
                return QdrantClient(url=self.qdrant_url)
            else:
                # Client distant avec authentification si nécessaire
                if self.qdrant_api_key:
                    return QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
                else:
                    return QdrantClient(url=self.qdrant_url)
        except Exception as e:
            self.logger.error(f"Erreur création client Qdrant: {str(e)}")
            return None
    
    def create_search_client(self, collection_name: str, client_type: str = None) -> Any:
        """
        Crée un client de recherche pour une collection spécifique.
        
        Args:
            collection_name: Nom de la collection Qdrant
            client_type: Type de client (jira, zendesk, etc.) si différent de la collection
            
        Returns:
            Client de recherche initialisé ou None en cas d'erreur
        """
        if not self.qdrant_client:
            self.logger.error("Client Qdrant non initialisé")
            return None
            
        if not collection_name:
            self.logger.error("Nom de collection non spécifié")
            return None
            
        # Déterminer le type de client à créer en fonction du nom de collection
        if not client_type:
            client_type = collection_name.lower()
        
        # Import dynamique pour éviter les problèmes d'importation circulaire
        try:
            # Tenter d'importer search_clients
            try:
                from search_clients import (
                    JiraSearchClient, ZendeskSearchClient, ConfluenceSearchClient,
                    NetsuiteSearchClient, NetsuiteDummiesSearchClient, SapSearchClient
                )
                
                # Créer le client approprié
                if client_type.lower() == 'jira':
                    return JiraSearchClient(
                        collection_name, self.qdrant_client,
                        self.embedding_service, self.translation_service
                    )
                elif client_type.lower() == 'zendesk':
                    return ZendeskSearchClient(
                        collection_name, self.qdrant_client,
                        self.embedding_service, self.translation_service
                    )
                elif client_type.lower() == 'confluence':
                    return ConfluenceSearchClient(
                        collection_name, self.qdrant_client,
                        self.embedding_service, self.translation_service
                    )
                elif client_type.lower() == 'netsuite':
                    return NetsuiteSearchClient(
                        collection_name, self.qdrant_client,
                        self.embedding_service, self.translation_service
                    )
                elif client_type.lower() == 'netsuite_dummies':
                    return NetsuiteDummiesSearchClient(
                        collection_name, self.qdrant_client,
                        self.embedding_service, self.translation_service
                    )
                elif client_type.lower() == 'sap':
                    return SapSearchClient(
                        collection_name, self.qdrant_client,
                        self.embedding_service, self.translation_service
                    )
                else:
                    self.logger.warning(f"Type de client inconnu: {client_type}, utilisation de GenericSearchClient")
                    from search_clients import GenericSearchClient
                    return GenericSearchClient(
                        collection_name, self.qdrant_client,
                        self.embedding_service, self.translation_service
                    )
            except ImportError as e:
                self.logger.warning(f"Impossible d'importer les clients depuis search_clients: {str(e)}")
                # Créer un client générique de fallback si les clients spécifiques ne sont pas disponibles
                return self._create_fallback_client(collection_name, client_type)
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la création du client de recherche: {str(e)}")
            return None
    
    def _create_fallback_client(self, collection_name: str, client_type: str) -> Any:
        """
        Crée un client de recherche minimal en cas d'échec de création du client spécifique.
        
        Args:
            collection_name: Nom de la collection
            client_type: Type de client
            
        Returns:
            Client de secours
        """
        class FallbackSearchClient:
            def __init__(self, collection_name, client_type):
                self.collection_name = collection_name
                self.client_type = client_type
                self.logger = logging.getLogger(f"ITS_HELP.fallback_client.{client_type}")
            
            async def search(self, query, *args, **kwargs):
                self.logger.warning(f"Utilisation du client fallback pour {self.client_type}")
                return []
            
            async def get_by_id(self, id, *args, **kwargs):
                self.logger.warning(f"Utilisation du client fallback pour {self.client_type}")
                return None
                
            async def recherche_intelligente(self, question, *args, **kwargs):
                self.logger.warning(f"Utilisation du client fallback pour {self.client_type}")
                return []
                
            def get_source_name(self):
                """Retourne le nom de la source de données."""
                return self.client_type.upper()
        
        return FallbackSearchClient(collection_name, client_type)
