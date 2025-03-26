"""
Module netsuite_dummies_client - Client de recherche pour les documents d'exemples NetSuite
"""

import logging
from typing import Dict, Any, List

from search.core.client_base import GenericSearchClient
from search.core.result_processor import DefaultResultProcessor

class NetsuiteDummiesResultProcessor(DefaultResultProcessor):
    """
    Processeur personnalisé pour les résultats NetSuite Dummies.
    Ajoute des fonctionnalités spécifiques au traitement des résultats d'exemples NetSuite.
    """
    def extract_payload(self, result: Any) -> Dict:
        """
        Extrait la payload d'un résultat NetSuite Dummies.
        Remplace éventuellement certains champs pour les adapter au format d'exemple.
        
        Args:
            result: Résultat brut de la recherche
            
        Returns:
            Dictionnaire contenant les données de payload
        """
        payload = super().extract_payload(result)
        
        # Formatage spécifique aux exemples NetSuite si nécessaire
        if payload:
            # Marquer clairement qu'il s'agit d'un exemple
            if 'title' in payload:
                if not payload['title'].startswith('[EXEMPLE]'):
                    payload['title'] = f"[EXEMPLE] {payload['title']}"
                    
        return payload

class NetsuiteDummiesSearchClient(GenericSearchClient):
    """
    Client de recherche spécifique pour les documents d'exemples NetSuite (dummies).
    Extension du client NetSuite standard avec modifications pour les exemples.
    """
    
    def __init__(self, collection_name=None, qdrant_client=None, embedding_service=None, translation_service=None):
        """
        Initialise le client de recherche NetSuite Dummies.
        
        Args:
            collection_name: Nom de la collection Qdrant
            qdrant_client: Client Qdrant à utiliser
            embedding_service: Service d'embedding à utiliser
            translation_service: Service de traduction à utiliser
        """
        # Utiliser la collection par défaut si non spécifiée
        if not collection_name:
            collection_name = "NETSUITE_DUMMIES"
            
        super().__init__(
            collection_name=collection_name,
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            processor=NetsuiteDummiesResultProcessor()
        )
        
        self.logger = logging.getLogger('ITS_HELP.netsuite_dummies_client')
        
    def get_source_name(self) -> str:
        """
        Retourne le nom de la source.
        
        Returns:
            Nom de la source
        """
        return "NetSuite Exemples"
    
    def valider_resultat(self, result: Any) -> bool:
        """
        Vérifie si un résultat NetSuite Dummies est valide.
        
        Args:
            result: Résultat à valider
            
        Returns:
            True si le résultat est valide, False sinon
        """
        # Validation de base
        if not super().valider_resultat(result):
            return False
            
        # Vérifications spécifiques aux exemples NetSuite
        payload = getattr(result, 'payload', {})
        
        # Vérifier que le contenu existe et n'est pas vide
        if not payload.get('content'):
            return False
            
        # Autres validations spécifiques aux exemples si nécessaire
        
        return True
    
    async def format_for_message(self, results: List[Any]) -> str:
        """
        Formate les résultats pour affichage dans un message, en ajoutant une mention d'exemple.
        
        Args:
            results: Liste de résultats à formater
            
        Returns:
            Message formaté
        """
        base_message = await super().format_for_message(results)
        if not results:
            return "Aucun exemple trouvé."
            
        # Ajouter une mention d'exemple
        return "⚠️ EXEMPLES DE DOCUMENTATION:\n" + base_message
