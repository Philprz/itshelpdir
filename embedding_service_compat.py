"""
Module de compatibilité pour embedding_service.

Ce module sert d'interface de compatibilité entre les implémentations
existantes d'embedding_service et l'application principale.
"""

import logging
from typing import List

# Import du service original s'il existe
try:
    from search.utils.embedding_service import EmbeddingService as OriginalEmbeddingService
    logger = logging.getLogger('ITS_HELP.embedding_service_compat')
    logger.info("Utilisation du service d'embedding depuis search.utils")
    EmbeddingService = OriginalEmbeddingService
except ImportError:
    # Implémentation de secours si le module original n'est pas disponible
    logger = logging.getLogger('ITS_HELP.embedding_service_compat')
    logger.warning("Module original d'embedding non trouvé, utilisation du service de compatibilité")
    
    class EmbeddingService:
        """
        Service pour la génération d'embeddings utilisant diverses APIs.
        Version de compatibilité simplifiée.
        """
        
        def __init__(self, openai_client=None, cache=None, model="text-embedding-ada-002"):
            """
            Initialise le service d'embedding.
            
            Args:
                openai_client: Client OpenAI à utiliser
                cache: Cache pour stocker les embeddings
                model: Modèle d'embedding à utiliser
            """
            self.openai_client = openai_client
            self.model = model
            self.cache = cache
            self.logger = logger
            
            # Nombre d'appels effectués
            self.call_count = 0
            self.error_count = 0
            
        async def get_embedding(self, text: str) -> List[float]:
            """
            Génère l'embedding d'un texte.
            
            Args:
                text: Texte pour lequel générer l'embedding
                
            Returns:
                Vecteur d'embedding
            """
            if not text:
                self.logger.warning("Tentative de génération d'embedding pour un texte vide")
                return [0.0] * 1536  # Embedding par défaut pour un texte vide
                
            # Normaliser le texte
            text = self._normalize_text(text)
            
            # Vérifier dans le cache si disponible
            if self.cache:
                cached_embedding = self.cache.get_embedding(text)
                if cached_embedding:
                    return cached_embedding
                    
            # Générer l'embedding avec le client configuré
            try:
                if self.openai_client:
                    return await self._get_openai_embedding(text)
                else:
                    self.logger.error("Aucun client configuré pour la génération d'embeddings")
                    return [0.0] * 1536  # Embedding par défaut
            except Exception as e:
                self.error_count += 1
                self.logger.error(f"Erreur lors de la génération d'embedding: {str(e)}")
                return [0.0] * 1536  # Embedding par défaut en cas d'erreur
                
        def _normalize_text(self, text: str) -> str:
            """Normalise un texte pour la génération d'embedding."""
            # Tronquer si trop long (OpenAI a des limites de tokens)
            max_chars = 8000
            if len(text) > max_chars:
                text = text[:max_chars]
                
            # Supprimer les caractères spéciaux problématiques
            text = text.replace('\x00', ' ')
            
            # Normaliser les espaces
            text = ' '.join(text.split())
            
            return text
            
        async def _get_openai_embedding(self, text: str) -> List[float]:
            """Génère un embedding avec OpenAI."""
            self.call_count += 1
            
            try:
                # Vérifier si c'est l'ancienne ou nouvelle API OpenAI
                if hasattr(self.openai_client, 'embeddings'):
                    # Nouvelle API
                    result = await self.openai_client.embeddings.create(
                        model=self.model,
                        input=text
                    )
                    embedding = result.data[0].embedding
                else:
                    # Ancienne API
                    result = await self.openai_client.embedding(
                        input=text,
                        model=self.model
                    )
                    embedding = result["data"][0]["embedding"]
                
                # Mettre en cache si disponible
                if self.cache and embedding:
                    self.cache.set_embedding(text, embedding)
                    
                return embedding
                
            except Exception as e:
                self.logger.error(f"Erreur API OpenAI: {str(e)}")
                raise
                
        def get_stats(self):
            """Retourne des statistiques sur l'utilisation du service."""
            return {
                "calls": self.call_count,
                "errors": self.error_count,
                "error_rate": f"{(self.error_count / self.call_count * 100) if self.call_count > 0 else 0:.2f}%",
                "model": self.model,
                "cache_enabled": self.cache is not None
            }
