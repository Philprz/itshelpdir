"""
Module confluence_client - Client de recherche spécifique pour Confluence
"""

import logging
import html
import re
from typing import List, Any

from search.core.client_base import GenericSearchClient
from search.core.result_processor import DefaultResultProcessor

class ConfluenceResultProcessor(DefaultResultProcessor):
    """
    Processeur spécifique pour les résultats Confluence.
    Personnalise l'extraction des informations des résultats Confluence.
    """
    
    def extract_title(self, result: Any) -> str:
        """
        Extrait le titre d'un résultat Confluence.
        
        Args:
            result: Résultat Confluence
            
        Returns:
            Titre de la page Confluence
        """
        payload = self.extract_payload(result)
        
        # Vérifier si le titre est directement disponible
        if 'title' in payload and payload['title']:
            # Décodage HTML si nécessaire
            title = html.unescape(payload['title'])
            return title
            
        # Essayer avec d'autres champs possibles
        for field in ['name', 'page_title', 'subject']:
            if field in payload and payload[field]:
                return html.unescape(payload[field])
                
        # Si aucun titre n'est disponible, utiliser l'espace et l'ID
        space = payload.get('space', '')
        page_id = payload.get('page_id', '')
        
        if space and page_id:
            return f"Page {space} #{page_id}"
        elif page_id:
            return f"Page #{page_id}"
            
        return "Page Confluence sans titre"
    
    def extract_url(self, result: Any) -> str:
        """
        Extrait l'URL d'un résultat Confluence.
        
        Args:
            result: Résultat Confluence
            
        Returns:
            URL de la page Confluence
        """
        payload = self.extract_payload(result)
        
        # Vérifier si l'URL est directement disponible
        if 'url' in payload and payload['url']:
            return payload['url']
            
        # Construire l'URL à partir de l'ID de page
        page_id = payload.get('page_id')
        if page_id:
            base_url = payload.get('base_url', 'https://confluence.example.com')
            return f"{base_url}/pages/viewpage.action?pageId={page_id}"
            
        return "#" # URL par défaut si aucune information n'est disponible
    
    def deduplicate_results(self, results: List[Any]) -> List[Any]:
        """
        Déduplique une liste de résultats Confluence par ID de page.
        
        Args:
            results: Liste de résultats à dédupliquer
            
        Returns:
            Liste de résultats dédupliqués
        """
        if not results:
            return []
            
        # Utiliser les IDs de page comme clé de déduplication
        unique_results = {}
        
        for result in results:
            payload = self.extract_payload(result)
            
            # Vérifier si l'ID de page est disponible
            page_id = payload.get('page_id')
            if page_id:
                # Si on a déjà vu ce page_id, prendre celui avec le meilleur score
                if page_id in unique_results:
                    if hasattr(result, 'score') and hasattr(unique_results[page_id], 'score'):
                        if result.score > unique_results[page_id].score:
                            unique_results[page_id] = result
                else:
                    unique_results[page_id] = result
            else:
                # Si pas d'ID de page, utiliser l'URL comme clé
                url = payload.get('url')
                if url and url not in unique_results:
                    unique_results[url] = result
                    
        return list(unique_results.values())

class ConfluenceSearchClient(GenericSearchClient):
    """
    Client de recherche spécifique pour Confluence.
    Implémente les méthodes spécifiques à Confluence et personnalise
    le traitement des résultats de recherche.
    """
    
    def __init__(self, collection_name=None, qdrant_client=None, embedding_service=None, translation_service=None):
        """
        Initialise le client de recherche Confluence.
        
        Args:
            collection_name: Nom de la collection Qdrant pour Confluence
            qdrant_client: Client Qdrant à utiliser
            embedding_service: Service d'embedding à utiliser
            translation_service: Service de traduction à utiliser
        """
        # Utiliser la collection par défaut si non spécifiée
        if not collection_name:
            collection_name = "CONFLUENCE"
            
        super().__init__(
            collection_name=collection_name,
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            processor=ConfluenceResultProcessor()
        )
        
        self.logger = logging.getLogger('ITS_HELP.confluence_client')
        
    def get_source_name(self) -> str:
        """
        Retourne le nom de la source.
        
        Returns:
            Nom de la source
        """
        return "CONFLUENCE"
        
    def valider_resultat(self, result: Any) -> bool:
        """
        Vérifie si un résultat Confluence est valide.
        
        Args:
            result: Résultat à valider
            
        Returns:
            True si le résultat est valide, False sinon
        """
        # Validation de base
        if not super().valider_resultat(result):
            return False
            
        # Validation spécifique pour les résultats Confluence
        payload = getattr(result, 'payload', {})
        
        # Un résultat Confluence valide doit avoir un page_id ou une URL
        if not (payload.get('page_id') or payload.get('url')):
            return False
            
        # Vérifier qu'il y a au moins un titre ou un contenu
        if not (payload.get('title') or payload.get('content')):
            return False
            
        return True
    
    async def recherche_intelligente(self, question: str, limit: int = 5, 
                                     score_threshold: float = 0.6, 
                                     client_name: str = None, **kwargs) -> List[Any]:
        """
        Recherche des informations pertinentes dans Confluence.
        Surcharge la méthode de base pour dédupliquer les résultats.
        
        Args:
            question: Question à rechercher
            limit: Nombre maximum de résultats
            score_threshold: Score minimum pour considérer un résultat
            client_name: Nom du client pour filtrer les résultats
            **kwargs: Arguments supplémentaires
            
        Returns:
            Liste de résultats pertinents
        """
        # Appeler la méthode de base
        results = await super().recherche_intelligente(
            question=question,
            limit=limit*2,  # On récupère plus de résultats pour avoir assez après déduplication
            score_threshold=score_threshold,
            client_name=client_name,
            **kwargs
        )
        
        # Dédupliquer les résultats avec le processeur
        dedup_results = self.processor.deduplicate_results(results)
        
        # Limiter au nombre demandé
        return dedup_results[:limit]
    
    async def format_for_message(self, results: List[Any]) -> str:
        """
        Formate les résultats pour affichage dans un message.
        
        Args:
            results: Liste de résultats à formater
            
        Returns:
            Message formaté
        """
        if not results:
            return "Aucune page Confluence trouvée."
            
        message = "📝 **Pages Confluence pertinentes:**\n\n"
        
        for i, result in enumerate(results[:5], 1):
            payload = getattr(result, 'payload', {})
            
            # Utiliser le processeur pour extraire le titre et l'URL
            title = self.processor.extract_title(result)
            url = self.processor.extract_url(result)
            
            # Construction de la ligne principale
            message += f"{i}. **[{title}]({url})**\n"
            
            # Informations supplémentaires
            info = []
            
            # Espace
            space = payload.get('space')
            if space:
                info.append(f"Espace: {space}")
                
            # Auteur
            author = payload.get('author')
            if author:
                info.append(f"Auteur: {author}")
                
            # Date de mise à jour
            updated = payload.get('last_updated') or payload.get('updated_date')
            if updated:
                info.append(f"Mise à jour: {updated}")
                
            if info:
                message += f"   _({' | '.join(info)})_\n"
                
            # Extrait du contenu
            content = payload.get('content') or payload.get('excerpt', '')
            if content:
                # Nettoyer et tronquer le contenu
                content = re.sub(r'<[^>]+>', ' ', content)  # Supprimer les balises HTML
                content = ' '.join(content.split())  # Normaliser les espaces
                content = html.unescape(content)  # Décoder les entités HTML
                
                if len(content) > 150:
                    content = content[:147] + "..."
                    
                message += f"   > {content}\n"
                
            message += "\n"
            
        if len(results) > 5:
            message += f"_...et {len(results) - 5} autres pages._"
            
        return message
