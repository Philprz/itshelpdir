"""
Module netsuite_client - Client de recherche spécifique pour NetSuite
"""

import logging
from typing import List, Any

from search.core.client_base import GenericSearchClient
from search.core.result_processor import DefaultResultProcessor

class NetsuiteResultProcessor(DefaultResultProcessor):
    """
    Processeur spécifique pour les résultats NetSuite.
    Personnalise l'extraction des informations des résultats NetSuite.
    """
    
    def extract_title(self, result: Any) -> str:
        """
        Extrait le titre d'un résultat NetSuite.
        
        Args:
            result: Résultat NetSuite
            
        Returns:
            Titre du document NetSuite
        """
        payload = self.extract_payload(result)
        
        # Vérifier si le titre est directement disponible
        if 'title' in payload and payload['title']:
            return payload['title']
            
        # Essayer avec d'autres champs possibles
        for field in ['name', 'document_name', 'subject']:
            if field in payload and payload[field]:
                return payload[field]
                
        # Si aucun titre n'est disponible, utiliser l'ID
        doc_id = payload.get('id', '')
        if doc_id:
            return f"Document NetSuite #{doc_id}"
            
        return "Document NetSuite sans titre"
    
    def extract_url(self, result: Any) -> str:
        """
        Extrait l'URL d'un résultat NetSuite.
        
        Args:
            result: Résultat NetSuite
            
        Returns:
            URL du document NetSuite
        """
        payload = self.extract_payload(result)
        
        # Vérifier si l'URL est directement disponible
        if 'url' in payload and payload['url']:
            return payload['url']
            
        # Construire l'URL à partir de l'ID
        doc_id = payload.get('id')
        doc_type = payload.get('type', 'document')
        
        if doc_id:
            base_url = payload.get('base_url', 'https://netsuite.example.com')
            return f"{base_url}/app/common/search/SearchResults.nl?id={doc_id}&type={doc_type}"
            
        return "#" # URL par défaut si aucune information n'est disponible

class NetsuiteSearchClient(GenericSearchClient):
    """
    Client de recherche spécifique pour NetSuite.
    Implémente les méthodes spécifiques à NetSuite et personnalise
    le traitement des résultats de recherche.
    """
    
    def __init__(self, collection_name=None, qdrant_client=None, embedding_service=None, translation_service=None):
        """
        Initialise le client de recherche NetSuite.
        
        Args:
            collection_name: Nom de la collection Qdrant pour NetSuite
            qdrant_client: Client Qdrant à utiliser
            embedding_service: Service d'embedding à utiliser
            translation_service: Service de traduction à utiliser
        """
        # Utiliser la collection par défaut si non spécifiée
        if not collection_name:
            collection_name = "NETSUITE"
            
        super().__init__(
            collection_name=collection_name,
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            processor=NetsuiteResultProcessor()
        )
        
        self.logger = logging.getLogger('ITS_HELP.netsuite_client')
        
    def get_source_name(self) -> str:
        """
        Retourne le nom de la source.
        
        Returns:
            Nom de la source
        """
        return "NETSUITE"
        
    def valider_resultat(self, result: Any) -> bool:
        """
        Vérifie si un résultat NetSuite est valide.
        
        Args:
            result: Résultat à valider
            
        Returns:
            True si le résultat est valide, False sinon
        """
        # Validation de base
        if not super().valider_resultat(result):
            return False
            
        # Validation spécifique pour les résultats NetSuite
        payload = getattr(result, 'payload', {})
        
        # Un résultat NetSuite valide doit avoir un ID ou une URL
        if not (payload.get('id') or payload.get('url')):
            return False
            
        # Vérifier qu'il y a au moins un titre ou un contenu
        if not (payload.get('title') or payload.get('content')):
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
            return "Aucun document NetSuite trouvé."
            
        message = "📊 **Documents NetSuite pertinents:**\n\n"
        
        for i, result in enumerate(results[:5], 1):
            payload = getattr(result, 'payload', {})
            
            # Utiliser le processeur pour extraire le titre et l'URL
            title = self.processor.extract_title(result)
            url = self.processor.extract_url(result)
            
            # Construction de la ligne principale
            message += f"{i}. **[{title}]({url})**\n"
            
            # Informations supplémentaires
            info = []
            
            # Type de document
            doc_type = payload.get('type')
            if doc_type:
                info.append(f"Type: {doc_type}")
                
            # Module
            module = payload.get('module')
            if module:
                info.append(f"Module: {module}")
                
            # Date de mise à jour
            updated = payload.get('last_updated')
            if updated:
                info.append(f"Mise à jour: {updated}")
                
            if info:
                message += f"   _({' | '.join(info)})_\n"
                
            # Extrait du contenu
            content = payload.get('content') or payload.get('excerpt', '')
            if content:
                # Tronquer le contenu si nécessaire
                if len(content) > 150:
                    content = content[:147] + "..."
                    
                message += f"   > {content}\n"
                
            message += "\n"
            
        if len(results) > 5:
            message += f"_...et {len(results) - 5} autres documents._"
            
        return message
