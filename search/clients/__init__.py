"""
Module clients - Centralisation des clients de recherche spécifiques
"""

# Import des clients spécifiques pour qu'ils soient accessible directement depuis le package
from search.clients.jira_client import JiraSearchClient
from search.clients.zendesk_client import ZendeskSearchClient
from search.clients.confluence_client import ConfluenceSearchClient
from search.clients.netsuite_client import NetsuiteSearchClient
from search.clients.netsuite_dummies_client import NetsuiteDummiesSearchClient
from search.clients.sap_client import SapSearchClient
from search.clients.erp_client import ERPSearchClient

# Définition explicite de ce qui est exporté par le module
__all__ = [
    'JiraSearchClient',
    'ZendeskSearchClient',
    'ConfluenceSearchClient',
    'NetsuiteSearchClient',
    'NetsuiteDummiesSearchClient',
    'SapSearchClient',
    'ERPSearchClient'
]
