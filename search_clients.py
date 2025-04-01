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
        NetsuiteDummiesSearchClient, SapSearchClient, ERPSearchClient
    )
    logger.info("Clients de recherche importés depuis archive_scripts")
except ImportError as e:
    # Le module archive_scripts est optionnel, log en INFO et non WARNING
    logger.info(f"Utilisation des clients de recherche internes: {str(e)}")
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
            
        def __getstate__(self):
            """Définit l'état de l'objet pour la sérialisation."""
            state = {}
            try:
                # Attributs sûrs uniquement
                state["collection_name"] = self.collection_name
                state["has_client"] = hasattr(self, "client") and self.client is not None
                state["has_embedding_service"] = hasattr(self, "embedding_service") and self.embedding_service is not None
                state["has_translation_service"] = hasattr(self, "translation_service") and self.translation_service is not None
            except Exception:
                state = {"collection_name": getattr(self, "collection_name", "unknown")}
            return state

        def to_json(self):
            """Méthode pour convertir en structure JSON-compatible."""
            try:
                return {
                    "collection_name": self.collection_name,
                    "type": self.__class__.__name__
                }
            except Exception:
                return {"type": "search_client"}
    
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
            
        async def recherche_intelligente(self, question, client_name=None, date_debut=None, date_fin=None, limit=10):
            """
            Méthode asynchrone pour effectuer une recherche intelligente dans JIRA.
            
            Args:
                question: Question ou texte de recherche
                client_name: Nom du client (optionnel)
                date_debut: Date de début pour filtrage (optionnel)
                date_fin: Date de fin pour filtrage (optionnel)
                limit: Nombre maximum de résultats à retourner
                
            Returns:
                Liste des résultats de recherche
            """
            try:
                # CORRECTION: Ne pas utiliser super().recherche_intelligente dans to_thread
                # car c'est déjà une coroutine et cela cause l'erreur "never awaited"
                
                # Implémentation de recherche intelligente spécifique à JIRA
                self.logger.info(f"Recherche JIRA pour '{question}'")
                
                # Si client_name est fourni, noter simplement sa présence
                if client_name:
                    self.logger.debug(f"Recherche filtrée pour client: {client_name}")
                
                # Simuler une recherche simple
                # Dans une vraie implémentation, cette partie ferait appel à l'API JIRA
                # et construirait une requête JQL appropriée
                
                # Retourner une liste vide pour le moment
                # Dans la vraie implémentation, transformer les résultats en structure attendue
                return []
            except Exception as e:
                logger.error(f"Erreur lors de la recherche JIRA: {str(e)}")
                return []
            
        async def format_for_slack(self, result):
            """Format le résultat pour affichage dans Slack."""
            try:
                # Si result a un attribut payload, l'utiliser directement
                if hasattr(result, 'payload'):
                    payload = result.payload
                # Sinon, considérer que result est lui-même le payload
                else:
                    payload = result
                
                # Extraire les informations pertinentes
                title = payload.get('summary', '')
                key = payload.get('key', 'N/A')
                status = payload.get('status', 'En cours')
                client = payload.get('client', 'N/A')
                assignee = payload.get('assignee', 'Non assigné')
                created = payload.get('created', 'N/A')
                updated = payload.get('updated', 'N/A')
                description = payload.get('description', '')
                url = payload.get('url', '')
                
                # Limiter la longueur de la description
                if description and len(description) > 500:
                    description = description[:497] + "..."
                
                # Construire le bloc formaté
                return {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*JIRA* - {key}\n"
                            f"*Client:* {client}\n"
                            f"*Titre:* {title}\n"
                            f"*Status:* {status} - *Assigné à:* {assignee}\n"
                            f"*Créé le:* {created} - *Maj:* {updated}\n"
                            f"*Description:* {description}\n"
                            f"*URL:* {url}"
                        )
                    }
                }
            except Exception as e:
                logger.error(f"Erreur lors du formatage JIRA: {str(e)}")
                return None
            
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
            
    class ERPSearchClient(GenericSearchClient):
        """Client pour les documents ERP génériques."""
        def get_source_name(self):
            return "ERP"


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
        'sap': SapSearchClient,
        'erp': ERPSearchClient  # Modification du client pour le type 'erp'
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
