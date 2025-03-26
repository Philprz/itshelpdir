"""
Module sap_client - Client de recherche spécifique pour SAP
"""

import logging
from typing import List, Any

from search.core.client_base import GenericSearchClient
from search.core.result_processor import DefaultResultProcessor

class SapResultProcessor(DefaultResultProcessor):
    """
    Processeur spécifique pour les résultats SAP.
    Personnalise l'extraction des informations des résultats SAP.
    """
    
    def extract_title(self, result: Any) -> str:
        """
        Extrait le titre d'un résultat SAP.
        
        Args:
            result: Résultat SAP
            
        Returns:
            Titre du document SAP
        """
        payload = self.extract_payload(result)
        
        # Vérifier les différents champs possibles pour le titre
        if 'transaction_id' in payload and 'transaction_name' in payload:
            trans_id = payload['transaction_id']
            trans_name = payload['transaction_name']
            return f"Transaction {trans_id} - {trans_name}"
            
        # Si c'est un rapport, utiliser son ID et nom
        if 'report_id' in payload and payload['report_id']:
            report_name = payload.get('report_name', 'Rapport')
            return f"Rapport {payload['report_id']} - {report_name}"
            
        # Si c'est une documentation, utiliser son titre
        if 'title' in payload and payload['title']:
            return payload['title']
                
        # Par défaut, utiliser le champ name ou subject
        for field in ['name', 'subject', 'description']:
            if field in payload and payload[field]:
                return payload[field]
                
        return "Document SAP sans titre"
        
    def extract_url(self, result: Any) -> str:
        """
        Extrait l'URL d'un résultat SAP.
        
        Args:
            result: Résultat SAP
            
        Returns:
            URL du document SAP
        """
        payload = self.extract_payload(result)
        
        # Vérifier si l'URL est directement disponible
        if 'url' in payload and payload['url']:
            return payload['url']
            
        # Construire l'URL à partir des informations disponibles
        base_url = payload.get('base_url', 'https://sap.example.com')
        
        # Pour les transactions
        if 'transaction_id' in payload and payload['transaction_id']:
            return f"{base_url}/transaction?id={payload['transaction_id']}"
            
        # Pour les rapports
        if 'report_id' in payload and payload['report_id']:
            return f"{base_url}/report?id={payload['report_id']}"
            
        # Pour les autres documents
        doc_id = payload.get('doc_id') or payload.get('id')
        if doc_id:
            return f"{base_url}/document?id={doc_id}"
            
        return "#" # URL par défaut si aucune information n'est disponible

class SapSearchClient(GenericSearchClient):
    """
    Client de recherche spécifique pour SAP.
    Implémente les méthodes spécifiques à SAP et personnalise
    le traitement des résultats de recherche.
    """
    
    def __init__(self, collection_name=None, qdrant_client=None, embedding_service=None, translation_service=None):
        """
        Initialise le client de recherche SAP.
        
        Args:
            collection_name: Nom de la collection Qdrant pour SAP
            qdrant_client: Client Qdrant à utiliser
            embedding_service: Service d'embedding à utiliser
            translation_service: Service de traduction à utiliser
        """
        # Utiliser la collection par défaut si non spécifiée
        if not collection_name:
            collection_name = "SAP"
            
        super().__init__(
            collection_name=collection_name,
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            processor=SapResultProcessor()
        )
        
        self.logger = logging.getLogger('ITS_HELP.sap_client')
        
    def get_source_name(self) -> str:
        """
        Retourne le nom de la source.
        
        Returns:
            Nom de la source
        """
        return "SAP"
        
    def valider_resultat(self, result: Any) -> bool:
        """
        Vérifie si un résultat SAP est valide.
        
        Args:
            result: Résultat à valider
            
        Returns:
            True si le résultat est valide, False sinon
        """
        # Validation de base
        if not super().valider_resultat(result):
            return False
            
        # Validation spécifique pour les résultats SAP
        payload = getattr(result, 'payload', {})
        
        # Vérifier qu'il y a au moins un identifiant ou un titre
        has_transaction = 'transaction_id' in payload and payload['transaction_id']
        has_report = 'report_id' in payload and payload['report_id']
        has_title = 'title' in payload and payload['title']
        has_name = 'name' in payload and payload['name']
        
        if not (has_transaction or has_report or has_title or has_name):
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
            return "Aucun document SAP trouvé."
            
        message = "🖥️ **Documents SAP pertinents:**\n\n"
        
        for i, result in enumerate(results[:5], 1):
            payload = getattr(result, 'payload', {})
            
            # Utiliser le processeur pour extraire le titre et l'URL
            title = self.processor.extract_title(result)
            url = self.processor.extract_url(result)
            
            # Construction de la ligne principale
            message += f"{i}. **[{title}]({url})**\n"
            
            # Informations supplémentaires
            info = []
            
            # Transaction / Rapport
            if 'transaction_id' in payload and payload['transaction_id']:
                info.append(f"Transaction: {payload['transaction_id']}")
            elif 'report_id' in payload and payload['report_id']:
                info.append(f"Rapport: {payload['report_id']}")
                
            # Module
            if 'module' in payload and payload['module']:
                info.append(f"Module: {payload['module']}")
                
            # Date
            if 'date' in payload and payload['date']:
                info.append(f"Date: {payload['date']}")
                
            if info:
                message += f"   _({' | '.join(info)})_\n"
                
            # Description ou contenu
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
