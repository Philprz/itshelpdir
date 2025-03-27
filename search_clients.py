"""
Module de compatibilité search_clients

Ce module sert d'interface de compatibilité entre les implémentations
archivées des clients de recherche et l'application principale.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger('ITS_HELP.search_clients')

# Import des clients de recherche depuis le module archivé
try:
    from archive_scripts.search_clients import (
        GenericSearchClient, JiraSearchClient, ZendeskSearchClient, 
        ConfluenceSearchClient, NetsuiteSearchClient, 
        NetsuiteDummiesSearchClient, SapSearchClient
    )
    logger.info("Clients de recherche importés depuis archive_scripts")
except ImportError as e:
    logger.warning(f"Impossible d'importer les clients depuis archive_scripts: {str(e)}")
    # Définir des classes de base si les originales ne sont pas disponibles
    
    class AbstractSearchClient:
        """Classe de base pour tous les clients de recherche."""
        
        def __init__(self, collection_name, client, embedding_service, translation_service=None):
            self.collection_name = collection_name
            self.client = client
            self.embedding_service = embedding_service
            self.translation_service = translation_service
            self.logger = logging.getLogger(f"ITS_HELP.search.{collection_name}")
        
        async def search(self, query, *args, **kwargs):
            """Méthode de recherche générique."""
            self.logger.warning(f"Méthode search non implémentée pour {self.collection_name}")
            return []
        
        async def get_by_id(self, id, *args, **kwargs):
            """Récupère un élément par son ID."""
            self.logger.warning(f"Méthode get_by_id non implémentée pour {self.collection_name}")
            return None
            
        async def recherche_intelligente(self, question, *args, **kwargs):
            """Méthode de recherche intelligente."""
            self.logger.warning(f"Méthode recherche_intelligente non implémentée pour {self.collection_name}")
            return []
            
        def get_source_name(self):
            """Retourne le nom de la source de données."""
            return self.collection_name.upper()
    
    class DefaultResultProcessor:
        """Processeur de résultats par défaut."""
        
        def extract_payload(self, result):
            """Extrait le payload d'un résultat."""
            if hasattr(result, 'payload'):
                return result.payload
            return result
            
        def extract_score(self, result):
            """Extrait le score d'un résultat."""
            if hasattr(result, 'score'):
                return result.score
            return 0.0
            
        def normalize_date(self, date_str):
            """Normalise une date pour l'affichage."""
            if not date_str:
                return 'N/A'
            return str(date_str)
    
    # Définir des classes de clients simplifiées
    
    class GenericSearchClient(AbstractSearchClient):
        """Client de recherche générique."""
        pass
        
    class JiraSearchClient(GenericSearchClient):
        """Client pour les tickets Jira."""
        def get_source_name(self):
            return "JIRA"
            
    class ZendeskSearchClient(GenericSearchClient):
        """Client pour les tickets Zendesk."""
        def get_source_name(self):
            return "ZENDESK"
            
    class ConfluenceSearchClient(GenericSearchClient):
        """Client pour les pages Confluence."""
        def get_source_name(self):
            return "CONFLUENCE"
            
    class NetsuiteSearchClient(GenericSearchClient):
        """Client pour les documents NetSuite."""
        def get_source_name(self):
            return "NETSUITE"
            
    class NetsuiteDummiesSearchClient(GenericSearchClient):
        """Client pour les exemples NetSuite."""
        def get_source_name(self):
            return "NETSUITE_DUMMIES"
            
    class SapSearchClient(GenericSearchClient):
        """Client pour les documents SAP."""
        def get_source_name(self):
            return "SAP"


def get_search_client(client_type: str, **kwargs) -> Optional[Any]:
    """
    Fonction pour obtenir un client de recherche en fonction du type.
    
    Args:
        client_type: Type de client à créer (jira, zendesk, etc.)
        **kwargs: Arguments additionnels pour l'initialisation du client
        
    Returns:
        Instance de client de recherche ou None en cas d'erreur
    """
    logger.info(f"Demande de client de recherche de type {client_type}")
    
    # Map des types de clients vers les classes appropriées
    client_map = {
        'jira': JiraSearchClient,
        'zendesk': ZendeskSearchClient,
        'confluence': ConfluenceSearchClient,
        'netsuite': NetsuiteSearchClient,
        'netsuite_dummies': NetsuiteDummiesSearchClient,
        'sap': SapSearchClient
    }
    
    # Récupérer la classe cliente appropriée
    client_class = client_map.get(client_type.lower())
    if not client_class:
        logger.warning(f"Type de client inconnu: {client_type}, utilisation de GenericSearchClient")
        client_class = GenericSearchClient
    
    # Récupérer les arguments nécessaires
    collection_name = kwargs.get('collection_name', client_type.upper())
    client = kwargs.get('client')
    embedding_service = kwargs.get('embedding_service')
    translation_service = kwargs.get('translation_service')
    
    # Vérifier les arguments requis
    if not client:
        logger.error("Client de base manquant pour l'initialisation")
        return None
        
    if not embedding_service:
        logger.warning("Service d'embedding manquant, certaines fonctionnalités peuvent ne pas fonctionner")
    
    # Créer et retourner le client
    try:
        return client_class(collection_name, client, embedding_service, translation_service)
    except Exception as e:
        logger.error(f"Erreur lors de la création du client {client_type}: {str(e)}")
        return None
