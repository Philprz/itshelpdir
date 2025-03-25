# À ajouter dans un fichier embedding_service.py

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple
import numpy as np

class EmbeddingService:
    """Service centralisé de génération d'embeddings avec cache optimisé et gestion des erreurs."""
    
    def __init__(self, openai_client=None, model="text-embedding-ada-002", 
                  l1_cache_max_size=1000, l2_cache=None, use_cache=True):
        """
        Initialise le service d'embedding.
        
        Args:
            openai_client: Client OpenAI pré-initialisé (optional)
            model: Modèle d'embedding à utiliser
            l1_cache_max_size: Taille maximale du cache L1 (en mémoire)
            l2_cache: Cache L2 (externe) pour persistance
            use_cache: Activer/désactiver le cache globalement
        """
        self.client = openai_client
        self.model = model
        
        # Configuration du logging
        self.logger = logging.getLogger("EmbeddingService")
        
        # Configuration du cache à deux niveaux
        self.use_cache = use_cache
        self.l1_cache = OrderedDict()  # Cache rapide en mémoire
        self.l1_cache_max_size = l1_cache_max_size
        self.l2_cache = l2_cache  # Cache externe (par exemple Redis)
        
        # Statistiques du cache
        self.hit_count = 0
        self.miss_count = 0
        self.l1_hit_count = 0
        self.l2_hit_count = 0
        
        # Métriques de performance
        self.total_api_calls = 0
        self.total_api_time = 0
        self.failed_api_calls = 0
        
        # Verrous pour éviter les requêtes dupliquées parallèles
        self._locks = {}
        
        # Circuit breaker pour limiter les appels en cas d'erreur répétée
        self.circuit_open = False
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        self.circuit_reset_time = None
        self.circuit_timeout = 60  # secondes
        
        self.namespace = "embeddings"
        self.dimension = 1536  # Dimension attendue pour ada-002
        self.max_retries = 3
        self.retry_base_delay = 1
        self.stats = {"hits": 0, "misses": 0, "errors": 0}
        self.l1_cache_ttl = 300  # 5 minutes en secondes
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
    
    async def _check_circuit_breaker(self):
        """
        Vérifie si le circuit breaker est ouvert et tente de le réinitialiser si le délai est écoulé.
        
        Returns:
            bool: True si le circuit est fermé (opérationnel), False si ouvert (en erreur)
        """
        if not self.circuit_open:
            return True
            
        # Vérifier si le délai de réinitialisation est écoulé
        if self.circuit_reset_time and time.monotonic() >= self.circuit_reset_time:
            self.logger.info("Tentative de réinitialisation du circuit breaker")
            self.circuit_open = False
            self.consecutive_failures = 0
            self.circuit_reset_time = None
            return True
            
        return False
        
    async def reset_circuit_breaker(self, force=False):
        """
        Réinitialise manuellement le circuit breaker.
        
        Args:
            force: Si True, réinitialise même si le délai n'est pas écoulé
            
        Returns:
            bool: True si réinitialisé avec succès
        """
        if not self.circuit_open:
            return True
            
        if force or (self.circuit_reset_time and time.monotonic() >= self.circuit_reset_time):
            self.logger.info("Réinitialisation manuelle du circuit breaker")
            self.circuit_open = False
            self.consecutive_failures = 0
            self.circuit_reset_time = None
            return True
            
        return False
        
    async def clear_cache(self, level="all"):
        """
        Vide le cache d'embeddings.
        
        Args:
            level: Niveau de cache à vider ("l1", "l2" ou "all")
            
        Returns:
            Dict: Statistiques sur l'opération
        """
        cleared = {
            "l1": 0,
            "l2": 0
        }
        
        if level in ["l1", "all"]:
            cleared["l1"] = len(self.l1_cache)
            self.l1_cache.clear()
            self.l1_cache_timestamps.clear()
            self.logger.info(f"Cache L1 vidé: {cleared['l1']} entrées supprimées")
            
        if level in ["l2", "all"] and self.l2_cache:
            try:
                # Supprimer uniquement les clés dans le namespace embeddings
                count = await self.l2_cache.clear(namespace=self.namespace)
                cleared["l2"] = count
                self.logger.info(f"Cache L2 vidé: {count} entrées supprimées")
            except Exception as e:
                self.logger.error(f"Erreur lors du vidage du cache L2: {str(e)}")
                
        # Réinitialisation des statistiques
        if level == "all":
            self.hit_count = 0
            self.miss_count = 0
            self.l1_hit_count = 0
            self.l2_hit_count = 0
            
        return cleared
        
    async def get_embedding(self, text: str, force_refresh=False) -> Optional[List[float]]:
        """
        Obtient l'embedding d'un texte avec gestion du cache et des erreurs.
        
        Args:
            text: Texte à encoder
            force_refresh: Si True, ignore le cache et force une nouvelle génération
            
        Returns:
            Liste de nombres flottants représentant l'embedding, ou None en cas d'erreur
        """
        # Validation de base
        if not text or not isinstance(text, str) or len(text.strip()) < 2:
            self.logger.warning("Texte invalide ou trop court")
            return None
            
        # Vérification du circuit breaker
        if not await self._check_circuit_breaker():
            self.logger.warning("Circuit breaker ouvert, requête rejetée")
            return None
        
        start_time = time.monotonic()
        
        # Génération de la clé de cache
        cache_key = self._get_cache_key(text)
        
        # Si cache désactivé ou force_refresh, on passe directement à la génération
        if not self.use_cache or force_refresh:
            return await self._generate_embedding(text, cache_key)
            
        # Vérification du cache L1 (mémoire)
        if cache_key in self.l1_cache:
            self.hit_count += 1
            self.l1_hit_count += 1
            self.l1_cache_timestamps[cache_key] = time.monotonic()
            self.logger.debug(f"Cache L1 hit pour '{text[:30]}...'")
            return self.l1_cache[cache_key]
            
        # Vérification du cache L2 (externe)
        if self.l2_cache:
            try:
                cached_vector = await self.l2_cache.get(cache_key, self.namespace)
                if cached_vector:
                    # Mise à jour du cache L1
                    self._update_l1_cache(cache_key, cached_vector)
                    self.hit_count += 1
                    self.l2_hit_count += 1
                    self.logger.debug(f"Cache L2 hit pour '{text[:30]}...'")
                    return cached_vector
            except Exception as e:
                self.logger.warning(f"Erreur lors de l'accès au cache L2: {str(e)}")
                
        # Cache miss, génération de l'embedding
        self.miss_count += 1
        result = await self._generate_embedding(text, cache_key)
        
        # Mesure du temps de traitement
        processing_time = time.monotonic() - start_time
        if processing_time > 1.0:  # Seuil arbitraire pour les requêtes lentes
            self.logger.warning(f"Génération d'embedding lente: {processing_time:.2f}s pour '{text[:30]}...'")
            
        return result
        
    async def _generate_embedding(self, text: str, cache_key: str) -> Optional[List[float]]:
        """
        Génère un embedding via l'API OpenAI avec gestion des erreurs et mise en cache.
        
        Args:
            text: Texte à encoder
            cache_key: Clé de cache pré-calculée
            
        Returns:
            Liste de nombres flottants représentant l'embedding, ou None en cas d'erreur
        """
        if not self.client:
            self.logger.error("Client OpenAI non initialisé")
            return None
            
        # Vérifier si une requête identique est déjà en cours (éviter les doublons)
        lock = self._locks.get(cache_key)
        if lock and lock.locked():
            self.logger.debug(f"Requête identique déjà en cours, attente du résultat: '{text[:30]}...'")
            await lock.acquire()
            lock.release()
            # Vérifier si le résultat est maintenant dans le cache
            if cache_key in self.l1_cache:
                return self.l1_cache[cache_key]
                
        # Créer un verrou pour cette requête
        if cache_key not in self._locks:
            self._locks[cache_key] = asyncio.Lock()
            
        # Acquérir le verrou
        async with self._locks[cache_key]:
            # Génération avec gestion des tentatives
            start_time = time.monotonic()
            
            for attempt in range(self.max_retries):
                try:
                    self.total_api_calls += 1
                    
                    # Appel API
                    response = await self.client.embeddings.create(
                        input=text,
                        model=self.model
                    )
                    
                    # Mesure du temps d'API
                    api_time = time.monotonic() - start_time
                    self.total_api_time += api_time
                    
                    # Réinitialisation du compteur d'échecs consécutifs
                    if self.consecutive_failures > 0:
                        self.consecutive_failures = 0
                        
                    # Traitement de la réponse
                    if response and response.data and len(response.data) > 0:
                        vector = response.data[0].embedding
                        
                        # Vérification de la taille
                        if len(vector) != self.dimension:
                            self.logger.warning(f"Dimension d'embedding inattendue: {len(vector)} au lieu de {self.dimension}")
                            
                        # Mise en cache
                        self._update_l1_cache(cache_key, vector)
                        if self.l2_cache and self.use_cache:
                            asyncio.create_task(self.l2_cache.set(cache_key, vector, self.namespace))
                            
                        return vector
                    else:
                        raise ValueError("Réponse OpenAI vide ou mal formée")
                        
                except Exception as e:
                    self.failed_api_calls += 1
                    delay = self.retry_base_delay * (2 ** attempt)  # Backoff exponentiel
                    
                    if attempt < self.max_retries - 1:
                        self.logger.warning(f"Échec de génération d'embedding (tentative {attempt+1}/{self.max_retries}): {str(e)}")
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(f"Échec définitif après {self.max_retries} tentatives: {str(e)}")
                        self.consecutive_failures += 1
                        
                        # Activation du circuit breaker si trop d'échecs consécutifs
                        if self.consecutive_failures >= self.max_consecutive_failures:
                            self.circuit_open = True
                            self.circuit_reset_time = time.monotonic() + self.circuit_timeout
                            self.logger.error(f"Circuit breaker activé pour {self.circuit_timeout}s après {self.consecutive_failures} échecs consécutifs")
                            
                        return None
                        
    def _update_l1_cache(self, cache_key: str, vector: List[float]):
        """
        Met à jour le cache L1 avec un nouvel embedding, en respectant la taille maximale.
        
        Args:
            cache_key: Clé de cache
            vector: Vecteur d'embedding à stocker
        """
        # Si le cache est plein, supprimer l'élément le plus ancien
        if len(self.l1_cache) >= self.l1_cache_max_size:
            oldest_key = next(iter(self.l1_cache))
            del self.l1_cache[oldest_key]
            if oldest_key in self.l1_cache_timestamps:
                del self.l1_cache_timestamps[oldest_key]
                
        # Ajouter le nouvel élément
        self.l1_cache[cache_key] = vector
        self.l1_cache_timestamps[cache_key] = time.monotonic()
        
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
            cache_lookups = await asyncio.gather(*[self.l2_cache.get(key, self.namespace) for key in cache_keys])
            
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
                response = await self.client.embeddings.create(
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
                            asyncio.create_task(self.l2_cache.set(cache_key, vector, self.namespace))
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
            "total_requests": total,
            "l1_hit_count": self.l1_hit_count,
            "l2_hit_count": self.l2_hit_count,
            "total_api_calls": self.total_api_calls,
            "total_api_time": self.total_api_time,
            "failed_api_calls": self.failed_api_calls
        }