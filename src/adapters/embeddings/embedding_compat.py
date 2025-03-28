"""
Module embedding_compat.py - Adaptateur de compatibilité pour les services d'embedding

Ce module fournit une interface de compatibilité entre la nouvelle
architecture de services d'embedding et le système existant (embedding_service.py).
"""

import logging
import asyncio
import time
import sys
import os
from typing import Dict, List, Any, Optional, Union

# Import de la nouvelle architecture
from .factory import EmbeddingServiceFactory

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.embeddings.embedding_compat")

class EmbeddingService:
    """
    Service d'embedding compatible avec l'ancien système.
    Ce service est un adaptateur qui utilise la nouvelle architecture
    tout en exposant une interface compatible avec le code existant.
    """
    
    def __init__(
        self, 
        openai_client=None, 
        cache=None, 
        model="text-embedding-ada-002",
        provider="openai"
    ):
        """
        Initialise le service d'embedding compatible
        
        Args:
            openai_client: Client OpenAI existant (transmis à l'adaptateur si possible)
            cache: Cache existant (ignoré, utilise le nouveau cache intelligent)
            model: Modèle d'embedding à utiliser
            provider: Fournisseur d'embedding ('openai', 'auto')
        """
        self.model = model
        self.provider = provider.lower()
        self.openai_client = openai_client
        self.old_cache = cache
        
        # Statistiques de l'ancien système pour compatibilité
        self.call_count = 0
        self.error_count = 0
        
        # Initialiser le service d'embedding
        try:
            # Créer un adaptateur LLM spécifique pour le client OpenAI si fourni
            llm_adapter = None
            if openai_client:
                try:
                    from ..llm.openai_adapter import OpenAIAdapter
                    llm_adapter = OpenAIAdapter(default_model=model)
                    # Injecter le client existant
                    llm_adapter._client = openai_client
                    logger.info("Utilisation du client OpenAI existant pour le service d'embedding")
                except Exception as e:
                    logger.warning(f"Impossible d'utiliser le client OpenAI existant: {str(e)}")
            
            # Créer le service d'embedding
            self.embedding_service = EmbeddingServiceFactory.create_service(
                provider=provider,
                llm_adapter=llm_adapter,
                model=model,
                cache_embeddings=True,
                batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "20")),
                normalize_embeddings=True
            )
            
            logger.info(f"Service d'embedding compatible initialisé avec provider: {provider}")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du service d'embedding: {str(e)}")
            self.embedding_service = None
    
    async def get_embedding(self, text: str) -> List[float]:
        """
        Génère un embedding pour un texte donné.
        Compatible avec l'ancien système.
        
        Args:
            text: Texte à vectoriser
            
        Returns:
            Vecteur d'embedding
        """
        if not self.embedding_service:
            logger.error("Service d'embedding non initialisé, impossible de générer un embedding")
            self.error_count += 1
            # Retourner un vecteur nul de la bonne dimension pour éviter les erreurs en aval
            return [0.0] * (1536 if self.model == "text-embedding-ada-002" else 768)
        
        try:
            # Mettre à jour les statistiques pour compatibilité
            self.call_count += 1
            
            # Déléguer au nouveau service
            start_time = time.time()
            embedding = await self.embedding_service.get_embedding(text)
            elapsed_time = time.time() - start_time
            
            logger.debug(f"Embedding généré en {elapsed_time:.2f}s via le service compatible")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération d'embedding: {str(e)}")
            self.error_count += 1
            
            # Retourner un vecteur nul de la bonne dimension pour éviter les erreurs en aval
            return [0.0] * (1536 if self.model == "text-embedding-ada-002" else 768)
    
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Génère des embeddings en batch pour plusieurs textes.
        Méthode ajoutée pour optimisation, non présente dans l'ancien système.
        
        Args:
            texts: Liste de textes à vectoriser
            
        Returns:
            Liste de vecteurs d'embedding
        """
        if not self.embedding_service:
            logger.error("Service d'embedding non initialisé, impossible de générer des embeddings")
            self.error_count += 1
            # Retourner des vecteurs nuls de la bonne dimension pour éviter les erreurs en aval
            return [[0.0] * (1536 if self.model == "text-embedding-ada-002" else 768) for _ in texts]
        
        try:
            # Mettre à jour les statistiques pour compatibilité
            self.call_count += len(texts)
            
            # Déléguer au nouveau service
            embeddings = await self.embedding_service.get_embeddings(texts)
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération d'embeddings en batch: {str(e)}")
            self.error_count += 1
            
            # Retourner des vecteurs nuls de la bonne dimension pour éviter les erreurs en aval
            return [[0.0] * (1536 if self.model == "text-embedding-ada-002" else 768) for _ in texts]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques du service d'embedding.
        Compatible avec l'ancien système.
        
        Returns:
            Dictionnaire de statistiques
        """
        stats = {
            "calls": self.call_count,
            "errors": self.error_count,
            "error_rate": f"{(self.error_count / self.call_count * 100) if self.call_count > 0 else 0:.2f}%",
            "model": self.model,
            "provider": self.provider,
            "cache_enabled": True  # Toujours activé avec le nouveau système
        }
        
        # Ajouter les statistiques détaillées du nouveau service si disponible
        if self.embedding_service:
            try:
                # Récupérer les statistiques de manière asynchrone
                loop = asyncio.get_event_loop()
                detailed_stats = loop.run_until_complete(self.embedding_service.health_check())
                
                # Fusionner les statistiques
                stats["detailed"] = detailed_stats
                
            except Exception as e:
                logger.warning(f"Impossible de récupérer les statistiques détaillées: {str(e)}")
        
        return stats
