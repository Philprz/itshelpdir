"""
Module core - Composants principaux du système de recherche
"""

# Importer les classes et fonctions principales
from search.core.client_base import AbstractSearchClient, GenericSearchClient
from search.core.factory import SearchClientFactory, search_factory
from search.core.result_processor import AbstractResultProcessor, DefaultResultProcessor

# Définir explicitement ce qui est exposé
__all__ = [
    'AbstractSearchClient',
    'GenericSearchClient',
    'SearchClientFactory',
    'search_factory',
    'AbstractResultProcessor',
    'DefaultResultProcessor'
]
