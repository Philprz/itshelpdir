"""
Module search - Point d'entrée principal pour la recherche
"""

# Import des classes et fonctions principales pour simplifier l'accès
from search.core.factory import SearchClientFactory, search_factory
from search.core.client_base import AbstractSearchClient, GenericSearchClient
from search.core.result_processor import AbstractResultProcessor, DefaultResultProcessor

# Import des clients spécifiques
from search.clients.jira_client import JiraSearchClient
from search.clients.zendesk_client import ZendeskSearchClient
from search.clients.confluence_client import ConfluenceSearchClient
from search.clients.netsuite_client import NetsuiteSearchClient
from search.clients.netsuite_dummies_client import NetsuiteDummiesSearchClient
from search.clients.sap_client import SapSearchClient
from search.clients.erp_client import ERPSearchClient

# Import des utilitaires
from search.utils.filter_builder import build_qdrant_filter
from search.utils.cache import SearchCache
from search.utils.embedding_service import EmbeddingService
from search.utils.translation_service import TranslationService

# Définition explicite de ce qui est exporté par le module
__all__ = [
    'SearchClientFactory', 'search_factory',
    'AbstractSearchClient', 'GenericSearchClient',
    'AbstractResultProcessor', 'DefaultResultProcessor',
    'JiraSearchClient', 'ZendeskSearchClient', 'ConfluenceSearchClient',
    'NetsuiteSearchClient', 'NetsuiteDummiesSearchClient', 'SapSearchClient', 'ERPSearchClient',
    'build_qdrant_filter', 'SearchCache', 'EmbeddingService', 'TranslationService'
]

# Version du module
__version__ = '2.0.0'
