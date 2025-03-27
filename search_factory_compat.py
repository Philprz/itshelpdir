"""
Module de compatibilité pour search_factory.py

Ce module sert d'interface de compatibilité entre les implémentations
existantes de search_factory et l'application principale.
"""

import os
import logging
import asyncio
from typing import Any

# Configuration du logger
logger = logging.getLogger("ITS_HELP.search_factory_compat")

# Importer la configuration à partir des variables d'environnement
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
QDRANT_URL = os.getenv('QDRANT_URL')
QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')

# Collections par défaut
COLLECTIONS = {
    'jira': os.getenv('QDRANT_COLLECTION_JIRA', 'JIRA'),
    'zendesk': os.getenv('QDRANT_COLLECTION_ZENDESK', 'ZENDESK'),
    'confluence': os.getenv('QDRANT_COLLECTION_CONFLUENCE', 'CONFLUENCE'),
    'netsuite': os.getenv('QDRANT_COLLECTION_NETSUITE', 'NETSUITE'),
    'netsuite_dummies': os.getenv('QDRANT_COLLECTION_NETSUITE_DUMMIES', 'NETSUITE_DUMMIES'),
    'sap': os.getenv('QDRANT_COLLECTION_SAP', 'SAP'),
    'erp': os.getenv('QDRANT_COLLECTION_ERP', 'ERP')
}

class SearchClientFactory:
    """
    Factory pour la création et la gestion des clients de recherche.
    Version de compatibilité simplifiée pour assurer le fonctionnement de l'application.
    """

    def __init__(self):
        self.clients = {}
        self.initialized = False
        self.logger = logger
    
    async def initialize(self):
        """Initialise tous les clients de recherche nécessaires"""
        if self.initialized:
            self.logger.info("Factory déjà initialisée - ignoré")
            return

        self.logger.info("Initialisation des clients de recherche...")
        
        try:
            # Tenter d'initialiser les clients
            await self._initialize_clients()
            self.initialized = True
            self.logger.info("Factory initialisée avec succès")
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation de la factory: {str(e)}")
            # Créer des clients de fallback pour permettre un fonctionnement dégradé
            self._initialize_fallback_clients()
    
    async def _initialize_clients(self):
        """Initialisation des clients de recherche pour chaque source de données"""
        # Créer les clients de manière asynchrone
        tasks = []
        for client_type in COLLECTIONS.keys():
            tasks.append(self._initialize_client(client_type))
        
        # Exécuter toutes les tâches d'initialisation en parallèle
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Traiter les résultats
        for client_type, result in zip(COLLECTIONS.keys(), results):
            if isinstance(result, Exception):
                self.logger.error(f"Erreur initialisation {client_type}: {str(result)}")
                # Créer un client de fallback en cas d'erreur
                self.clients[client_type] = self._create_fallback_client(client_type)
            else:
                self.clients[client_type] = result
    
    async def _initialize_client(self, client_type: str) -> Any:
        """Initialisation d'un client de recherche spécifique"""
        try:
            # Vérifier les variables d'environnement nécessaires
            if not OPENAI_API_KEY or not QDRANT_URL:
                self.logger.warning(f"Variables d'environnement manquantes pour {client_type}")
                return self._create_fallback_client(client_type)
            
            # Déterminer la collection à utiliser
            collection_name = COLLECTIONS.get(client_type, client_type)
            
            # Import dynamique pour éviter les problèmes d'importation circulaire
            try:
                from qdrant_search_clients import QdrantSearchClientFactory
                
                factory = QdrantSearchClientFactory(
                    qdrant_url=QDRANT_URL,
                    qdrant_api_key=QDRANT_API_KEY,
                    openai_api_key=OPENAI_API_KEY
                )
                
                client = factory.create_search_client(collection_name=collection_name)
                
                if client:
                    self.logger.info(f"Client {client_type} initialisé avec succès")
                    return client
            except ImportError as e:
                self.logger.warning(f"Impossible d'importer QdrantSearchClientFactory: {str(e)}")
                
                # Tentative alternative avec search_clients
                try:
                    from search_clients import get_search_client
                    client = get_search_client(client_type)
                    if client:
                        self.logger.info(f"Client {client_type} initialisé avec succès via search_clients")
                        return client
                except ImportError:
                    self.logger.warning("Impossible d'importer search_clients")
            
            # Si on arrive ici, aucune méthode n'a fonctionné
            return self._create_fallback_client(client_type)
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du client {client_type}: {str(e)}")
            return self._create_fallback_client(client_type)
    
    def _initialize_fallback_clients(self):
        """Initialise des clients de fallback pour toutes les sources"""
        for client_type in COLLECTIONS.keys():
            self.clients[client_type] = self._create_fallback_client(client_type)
        self.logger.warning("Clients de fallback initialisés")
    
    def _create_fallback_client(self, client_type: str) -> Any:
        """Crée un client de fallback qui retourne des résultats vides"""
        class FallbackSearchClient:
            def __init__(self, client_type):
                self.client_type = client_type
                self.logger = logging.getLogger(f"ITS_HELP.fallback_client.{client_type}")
            
            async def search(self, query, *args, **kwargs):
                self.logger.warning(f"Utilisation du client fallback pour {self.client_type}")
                return []
            
            async def get_by_id(self, id, *args, **kwargs):
                self.logger.warning(f"Utilisation du client fallback pour {self.client_type}")
                return None
        
        return FallbackSearchClient(client_type)
    
    def get_client(self, client_type: str) -> Any:
        """Récupère un client de recherche par son type"""
        if not self.initialized:
            self.logger.warning(f"Factory non initialisée, retourne un client fallback pour {client_type}")
            return self._create_fallback_client(client_type)
        
        if client_type not in self.clients:
            self.logger.warning(f"Client {client_type} non trouvé, retourne un client fallback")
            return self._create_fallback_client(client_type)
        
        return self.clients.get(client_type)


# Instance globale pour l'application
search_factory = SearchClientFactory()
