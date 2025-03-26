"""
Module zendesk_client - Client de recherche spécifique pour Zendesk
"""

import logging
import re
from typing import Dict, Any, List

from search.core.client_base import GenericSearchClient
from search.core.result_processor import DefaultResultProcessor

class ZendeskResultProcessor(DefaultResultProcessor):
    """
    Processeur spécifique pour les résultats Zendesk.
    Personnalise l'extraction des informations des résultats Zendesk.
    """
    
    def extract_title(self, result: Any) -> str:
        """
        Extrait le titre d'un résultat Zendesk.
        
        Args:
            result: Résultat Zendesk
            
        Returns:
            Titre du ticket Zendesk (généralement "Ticket #ID: subject")
        """
        payload = self.extract_payload(result)
        
        # Vérifier si l'ID du ticket est disponible
        ticket_id = payload.get('ticket_id')
        if not ticket_id:
            # Essayer d'extraire l'ID du ticket de l'URL
            url = payload.get('url', '')
            if url:
                match = re.search(r'/tickets/(\d+)', url)
                if match:
                    ticket_id = match.group(1)
        
        # Vérifier si le sujet est disponible
        subject = payload.get('subject') or payload.get('title', '')
        
        # Construire le titre
        if ticket_id and subject:
            return f"Ticket #{ticket_id}: {subject}"
        elif ticket_id:
            return f"Ticket #{ticket_id}"
        elif subject:
            return subject
        else:
            return "Ticket Zendesk sans titre"
    
    def extract_url(self, result: Any) -> str:
        """
        Extrait l'URL d'un résultat Zendesk.
        
        Args:
            result: Résultat Zendesk
            
        Returns:
            URL du ticket Zendesk
        """
        payload = self.extract_payload(result)
        
        # Vérifier si l'URL est directement disponible
        if 'url' in payload and payload['url']:
            return payload['url']
        
        # Construire l'URL à partir de l'ID du ticket
        ticket_id = payload.get('ticket_id')
        if ticket_id:
            subdomain = payload.get('subdomain', 'support')
            return f"https://{subdomain}.zendesk.com/agent/tickets/{ticket_id}"
            
        return "#" # URL par défaut si aucune information n'est disponible
    
    def deduplicate_results(self, results: List[Any]) -> List[Any]:
        """
        Déduplique une liste de résultats Zendesk par ID de ticket.
        
        Args:
            results: Liste de résultats à dédupliquer
            
        Returns:
            Liste de résultats dédupliqués
        """
        if not results:
            return []
            
        # Utiliser un dictionnaire pour dédupliquer par ticket_id
        unique_results = {}
        content_hashes = set()
        
        for result in results:
            payload = self.extract_payload(result)
            
            # Vérifier si le ticket_id est disponible
            ticket_id = payload.get('ticket_id')
            if ticket_id:
                # Si on a déjà vu ce ticket_id, prendre celui avec le meilleur score
                if ticket_id in unique_results:
                    if hasattr(result, 'score') and hasattr(unique_results[ticket_id], 'score'):
                        if result.score > unique_results[ticket_id].score:
                            unique_results[ticket_id] = result
                else:
                    unique_results[ticket_id] = result
            else:
                # Utiliser un hash du contenu pour dédupliquer
                content_hash = self._compute_content_hash(payload)
                if content_hash not in content_hashes:
                    content_hashes.add(content_hash)
                    # Utiliser l'index du résultat comme clé
                    unique_results[len(unique_results)] = result
                    
        return list(unique_results.values())
                
    def _compute_content_hash(self, payload: Dict) -> str:
        """
        Calcule un hash du contenu pour déduplication.
        
        Args:
            payload: Dictionnaire de payload
            
        Returns:
            Hash du contenu
        """
        # Extraire les champs pertinents pour le hash
        hash_elements = []
        
        if 'subject' in payload:
            hash_elements.append(payload['subject'])
            
        if 'content' in payload:
            # Tronquer le contenu pour ne pas avoir des hash trop longs
            content = payload['content']
            if len(content) > 100:
                content = content[:100]
            hash_elements.append(content)
            
        # Construire une chaîne à hasher
        hash_str = "|".join(hash_elements)
        
        # Retourner un hash simple
        if not hash_str:
            return "empty"
            
        return str(hash(hash_str))

class ZendeskSearchClient(GenericSearchClient):
    """
    Client de recherche spécifique pour Zendesk.
    Implémente les méthodes spécifiques à Zendesk et personnalise
    le traitement des résultats de recherche.
    """
    
    def __init__(self, collection_name=None, qdrant_client=None, embedding_service=None, translation_service=None):
        """
        Initialise le client de recherche Zendesk.
        
        Args:
            collection_name: Nom de la collection Qdrant pour Zendesk
            qdrant_client: Client Qdrant à utiliser
            embedding_service: Service d'embedding à utiliser
            translation_service: Service de traduction à utiliser
        """
        # Utiliser la collection par défaut si non spécifiée
        if not collection_name:
            collection_name = "ZENDESK"
            
        super().__init__(
            collection_name=collection_name,
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            processor=ZendeskResultProcessor()
        )
        
        self.logger = logging.getLogger('ITS_HELP.zendesk_client')
        
    def get_source_name(self) -> str:
        """
        Retourne le nom de la source.
        
        Returns:
            Nom de la source
        """
        return "ZENDESK"
        
    def valider_resultat(self, result: Any) -> bool:
        """
        Vérifie si un résultat Zendesk est valide.
        
        Args:
            result: Résultat à valider
            
        Returns:
            True si le résultat est valide, False sinon
        """
        # Validation de base
        if not super().valider_resultat(result):
            return False
            
        # Validation spécifique pour les résultats Zendesk
        payload = getattr(result, 'payload', {})
        
        # Un ticket Zendesk valide doit avoir un ticket_id ou une URL valide
        if 'ticket_id' not in payload and not ('url' in payload and '/tickets/' in payload['url']):
            return False
            
        # Un ticket doit avoir un sujet ou un contenu
        if not (payload.get('subject') or payload.get('content')):
            return False
            
        return True
    
    async def recherche_intelligente(self, question: str, limit: int = 5, 
                                    score_threshold: float = 0.6, 
                                    client_name: str = None, **kwargs) -> List[Any]:
        """
        Recherche des informations pertinentes dans Zendesk.
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
            return "Aucun ticket Zendesk trouvé."
            
        message = "🎯 **Tickets Zendesk pertinents:**\n\n"
        
        for i, result in enumerate(results[:5], 1):
            payload = getattr(result, 'payload', {})
            
            # Utiliser le processeur pour extraire le titre et l'URL
            title = self.processor.extract_title(result)
            url = self.processor.extract_url(result)
            
            # Construction de la ligne principale
            message += f"{i}. **[{title}]({url})**\n"
            
            # Informations supplémentaires
            info = []
            
            # Status
            status = payload.get('status')
            if status:
                info.append(f"Status: {status}")
                
            # Priorité
            priority = payload.get('priority')
            if priority:
                info.append(f"Priorité: {priority}")
                
            # Date
            created_at = payload.get('created_at')
            if created_at:
                info.append(f"Créé le: {created_at}")
                
            if info:
                message += f"   _({' | '.join(info)})_\n"
                
            # Contenu
            content = payload.get('content') or payload.get('description', '')
            if content:
                # Tronquer le contenu si trop long
                if len(content) > 150:
                    content = content[:147] + "..."
                message += f"   > {content}\n"
                
            message += "\n"
            
        if len(results) > 5:
            message += f"_...et {len(results) - 5} autres tickets._"
            
        return message
