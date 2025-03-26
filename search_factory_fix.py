
# Correctif pour search_factory.py

# Ajoutez ce code au début du fichier
from typing import Dict, Any, List, Optional
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Importer la configuration
try:
    from config import OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY, COLLECTIONS
except ImportError:
    # Utiliser les variables d'environnement
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    QDRANT_URL = os.getenv('QDRANT_URL')
    QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')
    COLLECTIONS = {
        "jira": "jira",
        "zendesk": "zendesk",
        "confluence": "confluence",
        "netsuite": "netsuite",
        "netsuite_dummies": "netsuite_dummies",
        "sap": "sap"
    }

# Remplacez la méthode _initialize_client par celle-ci
async def _initialize_client(self, client_type: str, collection_name: str = None, fallback_enabled: bool = True) -> Optional[Any]:
    '''Initialisation sécurisée d'un client de recherche'''
    try:
        # Vérifier les variables d'environnement
        if not OPENAI_API_KEY or not QDRANT_URL:
            logger.error(f"Variables d'environnement manquantes pour {client_type}")
            return None
            
        # Déterminer la collection à utiliser
        actual_collection = collection_name or COLLECTIONS.get(client_type, client_type)
        
        # Créer le client en fonction du type
        if client_type in ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]:
            # Importer dynamiquement pour éviter les problèmes d'importation circulaire
            from qdrant_search_clients import QdrantSearchClientFactory
            
            factory = QdrantSearchClientFactory(
                qdrant_url=QDRANT_URL,
                qdrant_api_key=QDRANT_API_KEY,
                openai_api_key=OPENAI_API_KEY
            )
            
            client = factory.create_search_client(collection_name=actual_collection)
            
            if client:
                logger.info(f"Client {client_type} initialisé avec succès")
                # Mettre en cache
                self._clients_cache[client_type] = client
                return client
        
        logger.error(f"Échec de l'initialisation du client {client_type}")
        return None
            
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du client {client_type}: {str(e)}")
        return None
