# À ajouter dans un fichier embedding_service.py

import asyncio
import hashlib
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

from configuration import logger, global_cache

class EmbeddingService:
    """Service centralisé de génération d'embeddings avec cache optimisé et gestion des erreurs."""
    
    def __init__(self, openai_client, cache=None):
        self.openai_client = openai_client
        self.cache = cache or global_cache  # Utilise le cache global par défaut
        self.logger = logging.getLogger('ITS_HELP.embeddings')
        self.namespace = "embeddings"
        self.model = "text-embedding-ada-002"
        self.dimension = 1536  # Dimension attendue pour ada-002
        self.max_retries = 3
        self.retry_base_delay = 1
        self.stats = {"hits": 0, "misses": 0, "errors": 0}
        self.l1_cache = {}  # Cache mémoire rapide (in-process)
        self.l1_cache_ttl = 300  # 5 minutes en secondes
        self.l1_cache_max_size = 100  # Nombre maximum d'éléments dans le cache L1
        self.l1_cache_timestamps = {}  # Timestamps pour le TTL
        
    def _get_cache_key(self, text: str) -> str:
        """Génère une clé de cache unique pour le texte."""
        text = self._normalize_text(text)
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _normalize_text(self, text: str) -> str:
        """Normalise le texte pour uniformiser les requêtes."""
        if not text:
            return ""
        # Suppression des espaces superflus et mise en minuscule
        normalized = " ".join(text.lower().split())
        # Suppression des caractères spéciaux si trop nombreux
        if sum(1 for c in normalized if not c.isalnum() and not c.isspace()) / len(normalized) > 0.3:
            normalized = "".join(c for c in normalized if c.isalnum() or c.isspace())
        return normalized.strip()
    
    def _validate_vector(self, vector: List[float]) -> bool:
        """Valide le vecteur d'embedding."""
        if not isinstance(vector, list):
            return False
        if not vector or len(vector) != self.dimension:
            return False
        if not all(isinstance(x, float) for x in vector):
            return False
        return True
    
    async def get_embedding(self, text: str, force_refresh=False) -> Optional[List[float]]:
        # Ajout d'un cache L1 pour accélérer les requêtes fréquentes
        self.l1_cache = {}  # Cache mémoire rapide (in-process)
        self.l1_cache_ttl = 300  # 5 minutes
        self.l1_cache_max_size = 100
        self.l1_cache_timestamps = {}

        # Vérification du cache L1 (plus rapide)
        cache_key = self._get_cache_key(text)
        if not force_refresh and cache_key in self.l1_cache:
            if time.monotonic() - self.l1_cache_timestamps[cache_key] < self.l1_cache_ttl:
                self.stats["hits"] += 1
                return self.l1_cache[cache_key]
        
        # Vérification du cache L2 (plus lent)
        if not force_refresh:
            cached_vector = await self.cache.get(cache_key, self.namespace)
            if cached_vector:
                # Mise à jour du cache L1
                if len(self.l1_cache) >= self.l1_cache_max_size:
                    oldest_key = min(self.l1_cache_timestamps, key=self.l1_cache_timestamps.get)
                    del self.l1_cache[oldest_key]
                    del self.l1_cache_timestamps[oldest_key]
                self.l1_cache[cache_key] = cached_vector
                self.l1_cache_timestamps[cache_key] = time.monotonic()
                self.stats["hits"] += 1
                return cached_vector
        if not text or not isinstance(text, str) or len(text.strip()) < 2:
            self.logger.warning("Texte invalide ou trop court")
            return None
            
        # Normalisation du texte
        text = text.strip()
        
        # Vérification du cache
        cache_key = self._get_cache_key(text)
        if not force_refresh:
            cached_vector = await self.cache.get(cache_key, self.namespace)
            if cached_vector:
                self.stats["hits"] += 1
                return cached_vector
        
        self.stats["misses"] += 1
        
        # Génération avec gestion des tentatives
        for attempt in range(self.max_retries):
            try:
                response = await self.openai_client.embeddings.create(
                    input=text,
                    model=self.model
                )
                
                if not response.data:
                    raise ValueError("Réponse OpenAI vide")
                    
                vector = response.data[0].embedding
                
                if not self._validate_vector(vector):
                    raise ValueError(f"Format d'embedding invalide: longueur={len(vector)}")
                    
                # Mise en cache
                await self.cache.set(cache_key, vector, self.namespace)
                
                return vector
                
            except Exception as e:
                self.logger.warning(f"Tentative {attempt+1}/{self.max_retries} échouée: {str(e)}")
                
                if attempt < self.max_retries - 1:
                    # Délai exponentiel entre les tentatives
                    retry_delay = self.retry_base_delay * (2 ** attempt)
                    await asyncio.sleep(retry_delay)
                else:
                    self.stats["errors"] += 1
                    self.logger.error(f"Échec définitif après {self.max_retries} tentatives: {str(e)}")
                    return None
    
    async def get_batch_embeddings(self, texts: List[str], force_refresh=False) -> List[Optional[List[float]]]:
        """
        Génère des embeddings pour plusieurs textes en batch.
        
        Args:
            texts: Liste de textes à transformer
            force_refresh: Force la régénération même si présent en cache
            
        Returns:
            Liste des embeddings (None pour les textes échoués)
        """
        if not texts:
            return []
            
        # Traitement optimisé des textes par lots
        batch_size = 20  # Taille de lot recommandée par OpenAI
        results = [None] * len(texts)
        
        # Optimisation : vérification du cache en premier pour tous les textes
        if not force_refresh:
            cache_keys = [self._get_cache_key(text) for text in texts]
            cache_lookups = await asyncio.gather(*[self.cache.get(key, self.namespace) for key in cache_keys])
            
            # Utilisation des valeurs en cache
            to_generate = []  # Indices des textes à générer
            generation_failures = 0  # Compteur d'échecs pour limiter les tentatives
            
            for i, (text, cached) in enumerate(zip(texts, cache_lookups)):
                if cached:
                    results[i] = cached
                    self.stats["hits"] += 1
                else:
                    to_generate.append(i)
                    self.stats["misses"] += 1
                    
            if not to_generate:
                return results  # Tous les textes sont en cache
            if generation_failures > 0:
                await asyncio.sleep(generation_failures * 0.5)  # Pause progressive
        else:
            to_generate = list(range(len(texts)))
            
        # Génération par lots pour les textes manquants
        for i in range(0, len(to_generate), batch_size):
            batch_indices = to_generate[i:i+batch_size]
            batch_texts = [texts[idx] for idx in batch_indices]
            
            try:
                # Génération en batch
                response = await self.openai_client.embeddings.create(
                    input=batch_texts,
                    model=self.model
                )
                
                # Traitement des résultats
                if response.data and len(response.data) == len(batch_texts):
                    for j, embedding_data in enumerate(response.data):
                        original_idx = batch_indices[j]
                        vector = embedding_data.embedding
                        
                        if self._validate_vector(vector):
                            results[original_idx] = vector
                            
                            # Mise en cache
                            cache_key = self._get_cache_key(texts[original_idx])
                            asyncio.create_task(self.cache.set(cache_key, vector, self.namespace))
                else:
                    self.logger.error(f"Réponse OpenAI incomplète: {len(response.data)} résultats pour {len(batch_texts)} textes")
                    
            except Exception as e:
                self.logger.error(f"Erreur génération batch: {str(e)}")
                
                # Fallback: génération individuelle pour ce batch
                for idx in batch_indices:
                    results[idx] = await self.get_embedding(texts[idx], force_refresh)
        
        return results
    
    async def get_embeddings_map(self, texts_dict: Dict[str, str], force_refresh=False) -> Dict[str, Optional[List[float]]]:
        """
        Génère des embeddings pour un dictionnaire de textes.
        
        Args:
            texts_dict: Dictionnaire {id: texte}
            force_refresh: Force la régénération
            
        Returns:
            Dictionnaire {id: embedding}
        """
        keys = list(texts_dict.keys())
        texts = [texts_dict[k] for k in keys]
        
        embeddings = await self.get_batch_embeddings(texts, force_refresh)
        
        return {k: embeddings[i] for i, k in enumerate(keys)}
    
    def cosine_similarity(self, vector1: List[float], vector2: List[float]) -> float:
        """
        Calcule la similarité cosinus entre deux vecteurs.
        
        Args:
            vector1, vector2: Vecteurs à comparer
            
        Returns:
            Score de similarité entre 0 et 1
        """
        if not vector1 or not vector2:
            return 0.0
            
        # Conversion en numpy pour optimisation
        v1 = np.array(vector1)
        v2 = np.array(vector2)
        
        # Normalisation des vecteurs
        v1_norm = np.linalg.norm(v1)
        v2_norm = np.linalg.norm(v2)
        
        if v1_norm == 0 or v2_norm == 0:
            return 0.0
            
        # Calcul de similarité
        return np.dot(v1, v2) / (v1_norm * v2_norm)
    
    async def find_similar_texts(self, query: str, candidates: List[str], threshold: float = 0.8) -> List[Tuple[int, float]]:
        """
        Trouve les textes similaires à une requête parmi une liste de candidats.
        
        Args:
            query: Texte de requête
            candidates: Liste des textes candidats
            threshold: Seuil minimal de similarité (0-1)
            
        Returns:
            Liste de tuples (indice, score) des textes similaires
        """
        # Génération de l'embedding de la requête
        query_embedding = await self.get_embedding(query)
        if not query_embedding:
            return []
            
        # Génération des embeddings des candidats
        candidate_embeddings = await self.get_batch_embeddings(candidates)
        
        # Calcul des similarités
        similarities = []
        for i, embedding in enumerate(candidate_embeddings):
            if embedding:
                similarity = self.cosine_similarity(query_embedding, embedding)
                if similarity >= threshold:
                    similarities.append((i, similarity))
                    
        # Tri par similarité décroissante
        return sorted(similarities, key=lambda x: x[1], reverse=True)
    
    def get_stats(self):
        """Retourne les statistiques d'utilisation."""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total) * 100 if total > 0 else 0
        
        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "errors": self.stats["errors"],
            "hit_rate": f"{hit_rate:.1f}%",
            "total_requests": total
        }