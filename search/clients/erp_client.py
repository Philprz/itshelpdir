"""
Module erp_client - Client de recherche spécifique pour ERP
"""

import logging
from typing import List, Any

from search.core.client_base import GenericSearchClient
from search.core.result_processor import DefaultResultProcessor

class ERPResultProcessor(DefaultResultProcessor):
    """
    Processeur spécifique pour les résultats ERP.
    Personnalise l'extraction des informations des résultats ERP.
    """
    
    def extract_title(self, result: Any) -> str:
        """
        Extrait le titre d'un résultat ERP.
        
        Args:
            result: Résultat ERP
            
        Returns:
            Titre du document ERP
        """
        payload = self.extract_payload(result)
        
        # Vérifier les différents champs possibles pour le titre
        for field in ['title', 'name', 'docname', 'subject']:
            if field in payload and payload[field]:
                return payload[field]
                
        # Si aucun titre spécifique n'est trouvé, utiliser l'ID ou le type
        if 'doc_id' in payload and payload['doc_id']:
            doc_type = payload.get('doc_type', 'Document')
            return f"{doc_type} {payload['doc_id']}"
                
        return "Document ERP sans titre"
        
    def extract_url(self, result: Any) -> str:
        """
        Extrait l'URL d'un résultat ERP.
        
        Args:
            result: Résultat ERP
            
        Returns:
            URL du document ERP
        """
        payload = self.extract_payload(result)
        
        # Vérifier si l'URL est directement disponible
        if 'url' in payload and payload['url']:
            return payload['url']
            
        # Construire l'URL à partir des informations disponibles
        doc_id = payload.get('doc_id')
        doc_type = payload.get('doc_type', 'document')
        
        if doc_id:
            base_url = payload.get('base_url', 'https://erp.example.com')
            return f"{base_url}/view?id={doc_id}&type={doc_type}"
            
        return "#" # URL par défaut si aucune information n'est disponible

class ERPSearchClient(GenericSearchClient):
    """
    Client de recherche spécifique pour ERP générique.
    Implémente les méthodes spécifiques à ERP et personnalise
    le traitement des résultats de recherche.
    """
    
    def __init__(self, collection_name=None, qdrant_client=None, embedding_service=None, translation_service=None):
        """
        Initialise le client de recherche ERP.
        
        Args:
            collection_name: Nom de la collection Qdrant pour ERP
            qdrant_client: Client Qdrant à utiliser
            embedding_service: Service d'embedding à utiliser
            translation_service: Service de traduction à utiliser
        """
        # Utiliser la collection par défaut si non spécifiée
        if not collection_name:
            collection_name = "ERP"
            
        super().__init__(
            collection_name=collection_name,
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            processor=ERPResultProcessor()
        )
        
        self.logger = logging.getLogger('ITS_HELP.erp_client')
        
    def get_source_name(self) -> str:
        """
        Retourne le nom de la source.
        
        Returns:
            Nom de la source
        """
        return "ERP"
        
    def valider_resultat(self, result: Any) -> bool:
        """
        Vérifie si un résultat ERP est valide.
        
        Args:
            result: Résultat à valider
            
        Returns:
            True si le résultat est valide, False sinon
        """
        # Validation de base
        if not super().valider_resultat(result):
            return False
            
        # Validation spécifique pour les résultats ERP
        payload = getattr(result, 'payload', {})
        
        # Vérifier qu'il y a au moins un identifiant ou un titre
        if not (payload.get('doc_id') or payload.get('title') or payload.get('name')):
            return False
            
        # Vérifier le type de document si nécessaire
        if 'doc_type' in payload and not payload['doc_type']:
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
            return "Aucun document ERP trouvé."
            
        message = "📄 **Documents ERP pertinents:**\n\n"
        
        for i, result in enumerate(results[:5], 1):
            payload = getattr(result, 'payload', {})
            title = payload.get('title') or payload.get('name', 'Document sans titre')
            doc_id = payload.get('doc_id', '')
            doc_type = payload.get('doc_type', '')
            
            url = self.processor.extract_url(result)
            
            # Construction de la ligne principale
            message += f"{i}. **[{title}]({url})**"
            if doc_id:
                message += f" (ID: {doc_id})"
            message += "\n"
            
            # Informations supplémentaires
            info = []
            if doc_type:
                info.append(f"Type: {doc_type}")
            if payload.get('date'):
                info.append(f"Date: {payload['date']}")
                
            if info:
                message += f"   _({' | '.join(info)})_\n"
                
            description = payload.get('description', '') or payload.get('content', '')
            if description:
                # Tronquer la description si trop longue
                if len(description) > 150:
                    description = description[:147] + "..."
                message += f"   > {description}\n"
                
            message += "\n"
            
        if len(results) > 5:
            message += f"_...et {len(results) - 5} autres documents._"
            
        return message
