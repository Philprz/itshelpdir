"""
Module openai_embedding.py - Service d'embedding utilisant OpenAI

Ce module implémente l'interface EmbeddingService pour OpenAI,
avec optimisation du batching et du caching.
"""

import logging
import asyncio
import time
import numpy as np
from typing import Dict, List, Any, Optional, Union, Callable, Tuple

# Import des interfaces nécessaires
from .base import EmbeddingService

# Import du cache intelligent
from ...infrastructure.cache import get_cache_instance

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.embeddings.openai")

class OpenAIEmbeddingService(EmbeddingService):
    """
    Service d'embedding utilisant les modèles OpenAI avec optimisation
    """
    
    def __init__(
        self, 
        llm_adapter=None,
        model: str = "text-embedding-ada-002",
        batch_size: int = 20,
        cache_embeddings: bool = True,
        normalize_embeddings: bool = True
    ):
        """
        Initialise le service d'embedding OpenAI
        
        Args:
            llm_adapter: Adaptateur LLM OpenAI déjà configuré (optionnel)
            model: Modèle d'embedding à utiliser
            batch_size: Taille maximale des batchs pour les requêtes multiples
            cache_embeddings: Activer le cache des embeddings
            normalize_embeddings: Normaliser les vecteurs d'embedding
        """
        self.model = model
        self.batch_size = batch_size
        self.cache_embeddings = cache_embeddings
        self.normalize_embeddings = normalize_embeddings
        
        # Utiliser l'adaptateur LLM fourni ou en créer un nouveau
        self.llm_adapter = llm_adapter
        
        if not self.llm_adapter:
            try:
                # Import de l'adaptateur OpenAI
                from ..llm.factory import LLMAdapterFactory
                self.llm_adapter = LLMAdapterFactory.create_adapter("openai")
                logger.debug("Adaptateur LLM OpenAI créé automatiquement")
            except Exception as e:
                logger.error(f"Impossible de créer l'adaptateur LLM OpenAI: {str(e)}")
                self.llm_adapter = None
        
        # Initialiser le cache si activé
        self.cache = get_cache_instance() if cache_embeddings else None
        
        # Métriques
        self._call_count = 0
        self._cached_hits = 0
        self._token_count = 0
        self._batch_count = 0
        
        # Modèles et dimensions
        self._dimensions_map = {
            "text-embedding-ada-002": 1536,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072
        }
        
        logger.info(f"Service d'embedding OpenAI initialisé avec modèle: {model}")
    
    @property
    def dimensions(self) -> int:
        """
        Nombre de dimensions des embeddings générés
        
        Returns:
            Nombre de dimensions
        """
        return self._dimensions_map.get(self.model, 1536)
    
    @property
    def provider_name(self) -> str:
        """
        Nom du fournisseur d'embedding
        
        Returns:
            'openai'
        """
        return "openai"
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalise un texte pour la génération d'embedding
        
        Args:
            text: Texte à normaliser
            
        Returns:
            Texte normalisé
        """
        if not text:
            return " "  # Éviter les textes vides
            
        # Tronquer si trop long (limite API OpenAI)
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars]
        
        # Supprimer les caractères problématiques
        text = text.replace('\x00', ' ')
        
        # Normaliser les espaces
        text = ' '.join(text.split())
        
        return text
    
    def _normalize_vector(self, vector: List[float]) -> List[float]:
        """
        Normalise un vecteur (norme L2 = 1) si nécessaire
        
        Args:
            vector: Vecteur à normaliser
            
        Returns:
            Vecteur normalisé
        """
        if not self.normalize_embeddings:
            return vector
            
        # Convertir en numpy pour efficacité
        np_vector = np.array(vector)
        norm = np.linalg.norm(np_vector)
        
        # Éviter division par zéro
        if norm > 0:
            np_vector = np_vector / norm
            return np_vector.tolist()
        return vector
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calcule la similarité cosinus entre deux vecteurs
        
        Args:
            vec1: Premier vecteur
            vec2: Deuxième vecteur
            
        Returns:
            Similarité cosinus (0-1)
        """
        # Convertir en numpy pour performance
        np_vec1 = np.array(vec1)
        np_vec2 = np.array(vec2)
        
        # Normaliser les vecteurs si pas déjà fait
        if not self.normalize_embeddings:
            norm1 = np.linalg.norm(np_vec1)
            norm2 = np.linalg.norm(np_vec2)
            
            if norm1 > 0:
                np_vec1 = np_vec1 / norm1
            if norm2 > 0:
                np_vec2 = np_vec2 / norm2
        
        # Calculer la similarité
        similarity = np.dot(np_vec1, np_vec2)
        
        # Limiter aux bornes [0,1]
        return float(max(0.0, min(1.0, similarity)))
    
    async def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """
        Récupère un embedding depuis le cache si disponible
        
        Args:
            text: Texte normalisé
            
        Returns:
            Vecteur d'embedding ou None si non trouvé
        """
        if not self.cache or not self.cache_embeddings:
            return None
            
        # Générer une clé de cache basée sur le modèle et le texte
        cache_key = f"{self.model}:{text}"
        
        # Chercher dans le cache
        cached_embedding = await self.cache.get(
            key=cache_key,
            namespace="embeddings"
        )
        
        if cached_embedding:
            self._cached_hits += 1
            logger.debug(f"Embedding trouvé dans le cache pour: {text[:50]}...")
        
        return cached_embedding
    
    async def _store_embedding_in_cache(self, text: str, embedding: List[float]) -> None:
        """
        Stocke un embedding dans le cache
        
        Args:
            text: Texte normalisé
            embedding: Vecteur d'embedding
        """
        if not self.cache or not self.cache_embeddings:
            return
            
        # Générer une clé de cache basée sur le modèle et le texte
        cache_key = f"{self.model}:{text}"
        
        # Stocker dans le cache
        await self.cache.set(
            key=cache_key,
            value=embedding,
            namespace="embeddings"
        )
        
        logger.debug(f"Embedding stocké dans le cache pour: {text[:50]}...")
    
    async def get_embedding(self, text: str) -> List[float]:
        """
        Génère un embedding vectoriel pour un texte
        
        Args:
            text: Texte à vectoriser
            
        Returns:
            Vecteur d'embedding
        """
        # Normaliser le texte
        normalized_text = self._normalize_text(text)
        
        # Vérifier dans le cache
        cached_embedding = await self._get_cached_embedding(normalized_text)
        if cached_embedding:
            return self._normalize_vector(cached_embedding)
        
        # Si pas dans le cache, générer avec l'adaptateur LLM
        if not self.llm_adapter:
            logger.error("Adaptateur LLM non disponible, impossible de générer l'embedding")
            raise RuntimeError("Adaptateur LLM non disponible")
        
        try:
            self._call_count += 1
            
            # Approximation des tokens (1 token ~= 4 caractères en anglais)
            self._token_count += len(normalized_text) // 4
            
            # Générer l'embedding
            start_time = time.time()
            embedding = await self.llm_adapter.embed(normalized_text, self.model)
            elapsed_time = time.time() - start_time
            
            logger.debug(
                f"Embedding généré en {elapsed_time:.2f}s pour texte de "
                f"{len(normalized_text)} caractères"
            )
            
            # Normaliser si nécessaire
            normalized_embedding = self._normalize_vector(embedding)
            
            # Stocker dans le cache
            await self._store_embedding_in_cache(normalized_text, normalized_embedding)
            
            return normalized_embedding
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération d'embedding: {str(e)}")
            raise
    
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Génère des embeddings en batch pour plusieurs textes
        
        Args:
            texts: Liste de textes à vectoriser
            
        Returns:
            Liste de vecteurs d'embedding
        """
        if not texts:
            return []
            
        # Résultats
        embeddings = []
        
        # Normaliser tous les textes
        normalized_texts = [self._normalize_text(text) for text in texts]
        
        # Traiter par batchs pour optimiser les appels API
        for i in range(0, len(normalized_texts), self.batch_size):
            batch = normalized_texts[i:i+self.batch_size]
            batch_results = []
            
            # Construire une liste des textes pour lesquels nous devons générer des embeddings
            to_generate = []
            cache_indices = []
            
            # Vérifier le cache pour chaque texte du batch
            for j, text in enumerate(batch):
                cached_embedding = await self._get_cached_embedding(text)
                if cached_embedding:
                    batch_results.append(self._normalize_vector(cached_embedding))
                else:
                    # Marquer pour génération
                    to_generate.append(text)
                    cache_indices.append(j)
            
            # Générer les embeddings manquants
            if to_generate:
                self._batch_count += 1
                self._call_count += 1
                
                # Approximation des tokens
                batch_tokens = sum(len(text) // 4 for text in to_generate)
                self._token_count += batch_tokens
                
                try:
                    # Générer des embeddings en batch si l'adaptateur le supporte
                    # Sinon, générer séquentiellement
                    generated_embeddings = []
                    
                    if hasattr(self.llm_adapter, 'embed_batch'):
                        # Si l'adaptateur supporte le batching natif
                        generated_embeddings = await self.llm_adapter.embed_batch(to_generate, self.model)
                    else:
                        # Fallback: génération séquentielle
                        logger.debug("Adaptateur sans support natif pour batching, génération séquentielle")
                        for text in to_generate:
                            emb = await self.llm_adapter.embed(text, self.model)
                            generated_embeddings.append(emb)
                    
                    # Normaliser et stocker dans le cache
                    for k, (text, embedding) in enumerate(zip(to_generate, generated_embeddings)):
                        normalized_embedding = self._normalize_vector(embedding)
                        await self._store_embedding_in_cache(text, normalized_embedding)
                        
                        # Insérer à la bonne position dans batch_results
                        j = cache_indices[k]
                        
                        # Étendre batch_results si nécessaire
                        while len(batch_results) <= j:
                            batch_results.append(None)
                            
                        batch_results[j] = normalized_embedding
                    
                except Exception as e:
                    logger.error(f"Erreur lors de la génération d'embeddings en batch: {str(e)}")
                    raise
            
            # Ajouter les résultats du batch
            embeddings.extend(batch_results)
        
        return embeddings
    
    async def similarity(self, text1: str, text2: str) -> float:
        """
        Calcule la similarité cosinus entre deux textes
        
        Args:
            text1: Premier texte
            text2: Second texte
            
        Returns:
            Score de similarité (0-1)
        """
        # Générer les embeddings pour les deux textes
        emb1 = await self.get_embedding(text1)
        emb2 = await self.get_embedding(text2)
        
        # Calculer la similarité
        return self._cosine_similarity(emb1, emb2)
    
    async def rank_by_similarity(self, query: str, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Classe une liste de textes par similarité avec une requête
        
        Args:
            query: Texte de requête
            texts: Liste de textes à classer
            
        Returns:
            Liste de dictionnaires {texte, score, index} triés par score décroissant
        """
        if not texts:
            return []
            
        # Générer l'embedding de la requête
        query_embedding = await self.get_embedding(query)
        
        # Générer les embeddings des textes en batch
        texts_embeddings = await self.get_embeddings(texts)
        
        # Calculer les scores de similarité
        similarities = []
        for i, embedding in enumerate(texts_embeddings):
            score = self._cosine_similarity(query_embedding, embedding)
            similarities.append({
                "text": texts[i],
                "score": score,
                "index": i
            })
        
        # Trier par score décroissant
        similarities.sort(key=lambda x: x["score"], reverse=True)
        
        return similarities
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité et l'état de santé du service
        
        Returns:
            Dictionnaire avec statut et informations
        """
        try:
            # Effectuer un test simple d'embedding
            start_time = time.time()
            embedding = await self.get_embedding("Test de santé du service d'embedding")
            elapsed_time = time.time() - start_time
            
            is_healthy = embedding is not None and len(embedding) == self.dimensions
            
            # Récupérer les statistiques du cache
            cache_stats = None
            if self.cache:
                cache_stats = await self.cache.get_stats()
            
            return {
                "provider": self.provider_name,
                "model": self.model,
                "dimensions": self.dimensions,
                "status": "healthy" if is_healthy else "degraded",
                "latency_ms": int(elapsed_time * 1000),
                "cache_enabled": self.cache_embeddings,
                "metrics": {
                    "calls": self._call_count,
                    "batches": self._batch_count,
                    "cached_hits": self._cached_hits,
                    "tokens_estimated": self._token_count,
                    "cache_stats": cache_stats
                }
            }
        except Exception as e:
            logger.error(f"Échec du contrôle de santé du service d'embedding: {str(e)}")
            
            return {
                "provider": self.provider_name,
                "model": self.model,
                "status": "unhealthy",
                "error": str(e),
                "cache_enabled": self.cache_embeddings
            }
