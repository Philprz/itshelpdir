"""
Module jira_client - Client de recherche spécifique pour Jira
"""

import logging
from typing import List, Any

from search.core.client_base import GenericSearchClient
from search.core.result_processor import DefaultResultProcessor

class JiraResultProcessor(DefaultResultProcessor):
    """
    Processeur spécifique pour les résultats Jira.
    Personnalise l'extraction des informations des résultats Jira.
    """
    
    def extract_title(self, result: Any) -> str:
        """
        Extrait le titre d'un résultat Jira.
        
        Args:
            result: Résultat Jira
            
        Returns:
            Titre du ticket Jira
        """
        payload = self.extract_payload(result)
        
        # Format standard pour les tickets Jira: [KEY-123] Titre du ticket
        key = payload.get('key', '')
        title = payload.get('title') or payload.get('summary', '')
        
        if key and title:
            return f"[{key}] {title}"
        elif key:
            return f"[{key}]" 
        else:
            return title or "Ticket sans titre"
            
    def extract_url(self, result: Any) -> str:
        """
        Extrait l'URL d'un résultat Jira.
        
        Args:
            result: Résultat Jira
            
        Returns:
            URL du ticket Jira
        """
        payload = self.extract_payload(result)
        
        # Vérifier si l'URL est directement disponible
        if 'url' in payload and payload['url']:
            return payload['url']
            
        # Construire l'URL à partir du key et de la base_url
        key = payload.get('key')
        if key:
            base_url = payload.get('base_url', 'https://jira.example.com')
            return f"{base_url}/browse/{key}"
            
        return super().extract_url(result)

class JiraSearchClient(GenericSearchClient):
    """
    Client de recherche spécifique pour Jira.
    Implémente les méthodes spécifiques à Jira et personnalise
    le traitement des résultats de recherche.
    """
    
    def __init__(self, collection_name: str = None, qdrant_client=None, embedding_service=None, translation_service=None):
        """
        Initialise le client de recherche Jira.
        
        Args:
            collection_name: Nom de la collection Qdrant pour Jira
            qdrant_client: Client Qdrant à utiliser
            embedding_service: Service d'embedding à utiliser
            translation_service: Service de traduction à utiliser
        """
        # Utiliser la collection par défaut si non spécifiée
        if not collection_name:
            collection_name = "JIRA"
            
        super().__init__(
            collection_name=collection_name,
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            processor=JiraResultProcessor()
        )
        
        self.logger = logging.getLogger('ITS_HELP.jira_client')
        
    def get_source_name(self) -> str:
        """
        Retourne le nom de la source.
        
        Returns:
            Nom de la source
        """
        return "JIRA"
        
    def valider_resultat(self, result: Any) -> bool:
        """
        Vérifie si un résultat Jira est valide.
        
        Args:
            result: Résultat à valider
            
        Returns:
            True si le résultat est valide, False sinon
        """
        # Validation de base
        if not super().valider_resultat(result):
            return False
            
        # Validation spécifique pour les résultats Jira
        payload = getattr(result, 'payload', {})
        
        # Un ticket Jira valide doit avoir un key
        if not payload.get('key'):
            return False
            
        # Vérifier qu'il y a un titre ou un résumé
        if not (payload.get('title') or payload.get('summary')):
            return False
            
        return True
    
    async def format_for_message(self, results: List[Any]) -> str:
        """
        Formate les résultats pour affichage dans un message.
        
        Args:
            results: Liste de résultats à formater
            
        Returns:
            Message formaté
        """
        if not results:
            return "Aucun ticket Jira trouvé."
            
        message = "🎫 **Tickets Jira pertinents:**\n\n"
        
        for i, result in enumerate(results[:5], 1):
            payload = getattr(result, 'payload', {})
            key = payload.get('key', '')
            title = payload.get('title') or payload.get('summary', 'Sans titre')
            status = payload.get('status', '')
            priority = payload.get('priority', '')
            
            url = self.processor.extract_url(result)
            
            message += f"{i}. **[{key}]({url})** - {title}\n"
            
            if status or priority:
                status_info = []
                if status:
                    status_info.append(f"Status: {status}")
                if priority:
                    status_info.append(f"Priorité: {priority}")
                
                message += f"   _({' | '.join(status_info)})_\n"
                
            description = payload.get('description', '')
            if description:
                # Tronquer la description si trop longue
                if len(description) > 150:
                    description = description[:147] + "..."
                message += f"   > {description}\n"
                
            message += "\n"
            
        if len(results) > 5:
            message += f"_...et {len(results) - 5} autres tickets._"
            
        return message
