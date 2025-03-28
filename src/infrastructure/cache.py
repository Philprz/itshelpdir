"""
Module cache.py - Cache intelligent avec optimisation de tokens et similarité sémantique

Ce module fournit une implémentation avancée du système de cache avec:
- Vérification de fraîcheur des données
- Support pour similarité sémantique
- Optimisation pour réduction de consommation de tokens
- Métriques de performance
"""

import asyncio
import logging
import time
import sys
import pickle
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from dataclasses import dataclass, field
import hashlib
import os

# Configuration du logging
logger = logging.getLogger("ITS_HELP.infrastructure.cache")

@dataclass
class CacheEntry:
    """
    Entrée de cache avec métadonnées avancées pour la gestion de fraîcheur et similarité
    """
    value: Any
    created_at: float
    last_accessed: float
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0
    access_count: int = 0
    source: str = "direct"  # direct, semantic, fallback
    
    def is_fresh(self, ttl: int = 3600, freshness_threshold: float = 0.8) -> bool:
        """
        Détermine si l'entrée est suffisamment fraîche selon sa durée de vie et son utilisation
        
        Args:
            ttl: Durée de vie en secondes
            freshness_threshold: Seuil de fraîcheur (0-1)
            
        Returns:
            True si l'entrée est considérée comme fraîche
        """
        # Calcul de l'âge et du pourcentage de vie restante
        age = time.time() - self.created_at
        
        # Si la fraîcheur basée uniquement sur le TTL est < seuil, vérifier l'activité
        if age < ttl * freshness_threshold:
            return True
            
        # Considérer également la fréquence d'utilisation pour les entrées plus anciennes
        # Les entrées fréquemment accédées restent "fraîches" plus longtemps
        recency_factor = (time.time() - self.last_accessed) / ttl
        usage_factor = min(1.0, self.access_count / 10)  # Normaliser l'utilisation (max bonus à 10 accès)
        
        # Formule composite: plus l'entrée est utilisée, plus elle reste fraîche longtemps
        effective_freshness = 1.0 - (age / ttl) + (usage_factor * 0.2) - (recency_factor * 0.1)
        
        return effective_freshness > freshness_threshold
    
    def update_access(self) -> None:
        """Met à jour le timestamp de dernier accès et incrémente le compteur"""
        self.last_accessed = time.time()
        self.access_count += 1

    def estimate_size(self) -> int:
        """
        Estime la taille mémoire de l'entrée en octets
        """
        if self.size_bytes > 0:
            return self.size_bytes
            
        try:
            # Utiliser pickle pour une estimation plus précise de la taille réelle
            serialized = pickle.dumps(self.value)
            self.size_bytes = sys.getsizeof(serialized)
            
            # Ajouter la taille des métadonnées et de l'embedding
            if self.embedding:
                self.size_bytes += sys.getsizeof(self.embedding)
            
            self.size_bytes += sys.getsizeof(self.metadata)
            
            return self.size_bytes
        except Exception as e:
            logger.warning(f"Erreur lors de l'estimation de la taille: {str(e)}")
            return sys.getsizeof(self.value)

class IntelligentCache:
    """
    Cache intelligent avec support pour similarité sémantique et optimisation de tokens
    """
    
    def __init__(
        self, 
        max_entries: int = 10000,
        default_ttl: int = 3600,
        max_memory_mb: int = 100,
        cleanup_interval: int = 300,
        similarity_threshold: float = 0.85,
        freshness_threshold: float = 0.7,
        embedding_function: Optional[Callable[[str], List[float]]] = None
    ):
        """
        Initialise le cache intelligent
        
        Args:
            max_entries: Nombre maximum d'entrées dans le cache
            default_ttl: Durée de vie par défaut des entrées (secondes)
            max_memory_mb: Limite mémoire en MB
            cleanup_interval: Intervalle de nettoyage en secondes
            similarity_threshold: Seuil de similarité pour considérer deux entrées comme similaires
            freshness_threshold: Seuil pour considérer une entrée comme fraîche
            embedding_function: Fonction pour générer des embeddings (pour recherche par similarité)
        """
        self._cache: Dict[str, Dict[str, CacheEntry]] = {}  # namespace -> key -> entry
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._cleanup_interval = cleanup_interval
        self._similarity_threshold = similarity_threshold
        self._freshness_threshold = freshness_threshold
        self._embedding_function = embedding_function
        
        self._lock = asyncio.Lock()
        self._stats = {
            "total_entries": 0,
            "memory_usage_bytes": 0,
            "hits": 0,
            "misses": 0,
            "semantic_hits": 0,
            "evictions": 0,
            "expired": 0,
            "tokens_saved": 0,  # Estimation des tokens économisés
            "potential_tokens": 0,
            "semantic_searches": 0,
            "semantic_matches": 0
        }
        
        self._cleanup_task = None
        self._initialized = True
        
    async def start_cleanup_task(self) -> None:
        """
        Démarre la tâche de nettoyage périodique
        """
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info(f"Tâche de nettoyage du cache démarrée (intervalle: {self._cleanup_interval}s)")
    
    async def _periodic_cleanup(self) -> None:
        """
        Exécute le nettoyage périodique du cache
        """
        while self._initialized:
            try:
                await asyncio.sleep(self._cleanup_interval)
                async with self._lock:
                    cleaned = await self._cleanup_expired()
                    if cleaned > 0:
                        logger.debug(f"Nettoyage périodique du cache: {cleaned} entrées supprimées")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur lors du nettoyage périodique du cache: {str(e)}")
                await asyncio.sleep(60)  # Attendre un peu plus longtemps en cas d'erreur
    
    async def _cleanup_expired(self) -> int:
        """
        Supprime les entrées expirées du cache
        
        Returns:
            Nombre d'entrées supprimées
        """
        cleaned_count = 0
        
        # Parcourir tous les namespaces
        for namespace in list(self._cache.keys()):
            namespace_entries = self._cache[namespace]
            
            # Identifier les entrées à supprimer
            keys_to_remove = []
            for key, entry in namespace_entries.items():
                ttl = entry.metadata.get("ttl", self._default_ttl)
                if not entry.is_fresh(ttl, self._freshness_threshold):
                    keys_to_remove.append(key)
                    self._stats["memory_usage_bytes"] -= entry.size_bytes
                    self._stats["total_entries"] -= 1
                    cleaned_count += 1
                    self._stats["expired"] += 1
            
            # Supprimer les entrées expirées
            for key in keys_to_remove:
                del namespace_entries[key]
                
            # Supprimer le namespace s'il est vide
            if not namespace_entries:
                del self._cache[namespace]
        
        return cleaned_count

    async def _enforce_memory_limit(self) -> int:
        """
        Supprime les entrées les moins utilisées pour respecter la limite mémoire
        
        Returns:
            Nombre d'entrées supprimées
        """
        if self._stats["memory_usage_bytes"] <= self._max_memory_bytes:
            return 0
            
        evicted_count = 0
        
        # Calculer le nombre d'octets à libérer
        bytes_to_free = self._stats["memory_usage_bytes"] - (self._max_memory_bytes * 0.9)  # Libérer jusqu'à 90% de la capacité
        
        # Collecter toutes les entrées de tous les namespaces
        all_entries = []
        for namespace, entries in self._cache.items():
            for key, entry in entries.items():
                all_entries.append((namespace, key, entry))
        
        # Trier par ordre de priorité d'éviction (les moins récemment utilisées d'abord)
        all_entries.sort(key=lambda x: x[2].last_accessed)
        
        # Supprimer les entrées jusqu'à libérer assez d'espace
        bytes_freed = 0
        for namespace, key, entry in all_entries:
            if bytes_freed >= bytes_to_free:
                break
                
            bytes_freed += entry.size_bytes
            evicted_count += 1
            
            # Supprimer l'entrée
            del self._cache[namespace][key]
            
            # Supprimer le namespace s'il est vide
            if not self._cache[namespace]:
                del self._cache[namespace]
                
            # Mettre à jour les statistiques
            self._stats["memory_usage_bytes"] -= entry.size_bytes
            self._stats["total_entries"] -= 1
            self._stats["evictions"] += 1
            
        return evicted_count
        
    def _generate_key(self, value: str) -> str:
        """
        Génère une clé de cache unique pour une valeur
        
        Args:
            value: Valeur à hacher
            
        Returns:
            Clé de cache
        """
        # Normaliser la chaîne pour une meilleure cohérence
        if isinstance(value, str):
            value = value.strip().lower()
        
        # Utiliser SHA-256 pour un hachage fiable
        return hashlib.sha256(str(value).encode('utf-8')).hexdigest()
        
    async def set(
        self, 
        key: str, 
        value: Any, 
        namespace: str = "default", 
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        embedding_text: Optional[str] = None,
        should_embed: bool = False
    ) -> None:
        """
        Stocke une valeur dans le cache avec métadonnées avancées
        
        Args:
            key: Clé d'accès (sera normalisée)
            value: Valeur à stocker
            namespace: Espace de noms pour organiser le cache
            ttl: Durée de vie en secondes (None = utiliser la valeur par défaut)
            metadata: Métadonnées associées à l'entrée
            embedding_text: Texte à utiliser pour générer l'embedding (si different de key)
            should_embed: Si True, génère un embedding pour la recherche par similarité
        """
        # Normaliser la clé
        cache_key = self._generate_key(key)
        
        # Préparer les métadonnées
        entry_metadata = metadata or {}
        if ttl is not None:
            entry_metadata["ttl"] = ttl
        
        # Générer l'embedding si nécessaire
        embedding = None
        if should_embed and self._embedding_function:
            try:
                text_to_embed = embedding_text or (key if isinstance(key, str) else str(key))
                embedding = await self._embedding_function(text_to_embed)
            except Exception as e:
                logger.warning(f"Erreur lors de la génération de l'embedding: {str(e)}")
        
        # Créer l'entrée de cache
        entry = CacheEntry(
            value=value,
            created_at=time.time(),
            last_accessed=time.time(),
            embedding=embedding,
            metadata=entry_metadata,
            source="direct"
        )
        
        # Estimer la taille
        size_bytes = entry.estimate_size()
        entry.size_bytes = size_bytes
        
        async with self._lock:
            # Initialiser le namespace s'il n'existe pas
            if namespace not in self._cache:
                self._cache[namespace] = {}
            
            # Stocker l'entrée
            self._cache[namespace][cache_key] = entry
            
            # Mettre à jour les statistiques
            self._stats["memory_usage_bytes"] += size_bytes
            self._stats["total_entries"] += 1
            
            # Vérifier les limites et nettoyer si nécessaire
            if self._stats["total_entries"] > self._max_entries or self._stats["memory_usage_bytes"] > self._max_memory_bytes:
                evicted = await self._enforce_memory_limit()
                if evicted > 0:
                    logger.debug(f"Limite de mémoire dépassée, {evicted} entrées évincées")

    async def get(
        self, 
        key: str, 
        namespace: str = "default",
        return_metadata: bool = False,
        allow_semantic_match: bool = False,
        embedding_text: Optional[str] = None
    ) -> Union[Any, Tuple[Any, Dict[str, Any]], None]:
        """
        Récupère une valeur du cache avec support pour recherche par similarité
        
        Args:
            key: Clé à rechercher
            namespace: Espace de noms du cache
            return_metadata: Si True, retourne aussi les métadonnées
            allow_semantic_match: Si True, permet une correspondance par similarité sémantique
            embedding_text: Texte alternatif pour la recherche sémantique
            
        Returns:
            Valeur trouvée ou None si non trouvée
        """
        # Normaliser la clé
        cache_key = self._generate_key(key)
        
        async with self._lock:
            # Vérifier si le namespace existe
            if namespace not in self._cache:
                self._stats["misses"] += 1
                return None
                
            # Recherche directe (exacte)
            if cache_key in self._cache[namespace]:
                entry = self._cache[namespace][cache_key]
                
                # Vérifier la fraîcheur
                ttl = entry.metadata.get("ttl", self._default_ttl)
                if not entry.is_fresh(ttl, self._freshness_threshold):
                    # Entrée expirée
                    del self._cache[namespace][cache_key]
                    self._stats["memory_usage_bytes"] -= entry.size_bytes
                    self._stats["total_entries"] -= 1
                    self._stats["expired"] += 1
                    self._stats["misses"] += 1
                    return None
                
                # Mettre à jour les statistiques d'accès
                entry.update_access()
                self._stats["hits"] += 1
                
                # Estimation des tokens économisés (si la valeur est une chaîne)
                if isinstance(entry.value, str):
                    tokens_approx = len(entry.value.split()) / 0.75  # Approximation grossière
                    self._stats["tokens_saved"] += tokens_approx
                    self._stats["potential_tokens"] += tokens_approx
                
                # Retourner la valeur avec ou sans métadonnées
                if return_metadata:
                    return entry.value, entry.metadata
                return entry.value
                
            # Recherche sémantique si autorisée
            if allow_semantic_match and self._embedding_function:
                self._stats["semantic_searches"] += 1
                best_match = await self._find_semantic_match(key, namespace, embedding_text)
                if best_match:
                    entry = best_match
                    
                    # Mise à jour des statistiques
                    entry.update_access()
                    self._stats["semantic_hits"] += 1
                    self._stats["semantic_matches"] += 1
                    
                    # Estimation des tokens économisés (si la valeur est une chaîne)
                    if isinstance(entry.value, str):
                        tokens_approx = len(entry.value.split()) / 0.75
                        self._stats["tokens_saved"] += tokens_approx
                        self._stats["potential_tokens"] += tokens_approx
                    
                    # Retourner la valeur
                    if return_metadata:
                        return entry.value, entry.metadata
                    return entry.value
        
        # Aucune correspondance trouvée
        self._stats["misses"] += 1
        return None
        
    async def _find_semantic_match(
            self, 
            key: str, 
            namespace: str,
            embedding_text: Optional[str] = None
        ) -> Optional[CacheEntry]:
        """
        Recherche une entrée sémantiquement similaire
        
        Args:
            key: Clé à rechercher
            namespace: Espace de noms
            embedding_text: Texte alternatif pour la recherche
            
        Returns:
            CacheEntry la plus similaire ou None
        """
        # Vérifier si le namespace existe
        if namespace not in self._cache:
            return None
            
        try:
            # Générer l'embedding pour la requête
            text_to_embed = embedding_text or (key if isinstance(key, str) else str(key))
            query_embedding = await self._embedding_function(text_to_embed)
            
            # Cache-clé pour optimiser les recherches répétitives
            cache_key = self._generate_key(f"semantic_search:{text_to_embed}")
            if namespace in self._cache and cache_key in self._cache[namespace]:
                cached_result = self._cache[namespace][cache_key]
                if cached_result.is_fresh(ttl=60):  # Cache de recherche court (1 minute)
                    # Si le résultat référencé existe toujours et est frais
                    result_key = cached_result.value
                    if result_key in self._cache[namespace]:
                        entry = self._cache[namespace][result_key]
                        if entry.is_fresh(ttl=self._default_ttl, freshness_threshold=self._freshness_threshold):
                            return entry
            
            # Parcourir toutes les entrées du namespace avec embeddings
            candidates = []
            
            for cache_key, entry in self._cache[namespace].items():
                if entry.embedding is None:
                    continue
                    
                # Préfilter avec un calcul de similarité optimisé
                if len(entry.embedding) > 100:
                    # Pour les vecteurs longs, comparer d'abord un sous-ensemble
                    sample_similarity = self._cosine_similarity(
                        query_embedding[:100], 
                        entry.embedding[:100]
                    )
                    # Continuer seulement si la similarité partielle est prometteuse
                    if sample_similarity < self._similarity_threshold * 0.8:
                        continue
                
                # Calculer la similarité cosinus complète
                similarity = self._cosine_similarity(query_embedding, entry.embedding)
                
                # Ajuster le seuil en fonction de la fraîcheur de l'entrée
                adjusted_threshold = self._similarity_threshold
                if entry.access_count > 5:
                    # Réduire légèrement le seuil pour les entrées fréquemment utilisées
                    adjusted_threshold *= 0.95
                
                # Collecter les candidats qui dépassent le seuil adaptatif
                if similarity >= adjusted_threshold:
                    candidates.append((entry, similarity))
            
            # Trier les candidats par similarité
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            if candidates:
                best_match, best_score = candidates[0]
                
                # Mettre en cache le résultat de cette recherche pour optimiser les futures recherches
                await self.set(
                    f"semantic_search:{text_to_embed}", 
                    self._generate_key(best_match.key) if hasattr(best_match, 'key') else "unknown",
                    namespace=namespace, 
                    ttl=60,  # Courte durée pour le cache de recherche
                    metadata={"similarity_score": best_score}
                )
                
                # Enregistrer des métriques plus détaillées
                metadata = best_match.metadata or {}
                if "semantic_matches" not in metadata:
                    metadata["semantic_matches"] = []
                metadata["semantic_matches"].append({
                    "query": text_to_embed,
                    "similarity": best_score,
                    "timestamp": time.time()
                })
                # Limiter la taille de l'historique
                if len(metadata["semantic_matches"]) > 5:
                    metadata["semantic_matches"] = metadata["semantic_matches"][-5:]
                best_match.metadata = metadata
                
                return best_match
            
            return None
            
        except Exception as e:
            logger.warning(f"Erreur lors de la recherche sémantique: {str(e)}")
            return None
            
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calcule la similarité cosinus entre deux vecteurs
        
        Args:
            vec1: Premier vecteur
            vec2: Deuxième vecteur
            
        Returns:
            Similarité cosinus (0-1)
        """
        if len(vec1) != len(vec2):
            return 0.0
            
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 * magnitude2 == 0:
            return 0.0
            
        return dot_product / (magnitude1 * magnitude2)
        
    async def delete(self, key: str, namespace: str = "default") -> bool:
        """
        Supprime une entrée du cache
        
        Args:
            key: Clé à supprimer
            namespace: Espace de noms
            
        Returns:
            True si supprimée, False sinon
        """
        # Normaliser la clé
        cache_key = self._generate_key(key)
        
        async with self._lock:
            # Vérifier si le namespace existe
            if namespace not in self._cache:
                return False
                
            # Vérifier si la clé existe
            if cache_key not in self._cache[namespace]:
                return False
                
            # Récupérer l'entrée
            entry = self._cache[namespace][cache_key]
            
            # Mettre à jour les statistiques
            self._stats["memory_usage_bytes"] -= entry.size_bytes
            self._stats["total_entries"] -= 1
            
            # Supprimer l'entrée
            del self._cache[namespace][cache_key]
            
            # Supprimer le namespace s'il est vide
            if not self._cache[namespace]:
                del self._cache[namespace]
                
            return True
            
    async def clear(self, namespace: Optional[str] = None) -> int:
        """
        Vide le cache ou un namespace spécifique
        
        Args:
            namespace: Namespace à vider (None = tout le cache)
            
        Returns:
            Nombre d'entrées supprimées
        """
        count = 0
        
        async with self._lock:
            if namespace is not None:
                # Vider uniquement le namespace spécifié
                if namespace in self._cache:
                    count = len(self._cache[namespace])
                    
                    # Mettre à jour les statistiques
                    for entry in self._cache[namespace].values():
                        self._stats["memory_usage_bytes"] -= entry.size_bytes
                    
                    self._stats["total_entries"] -= count
                    
                    # Supprimer le namespace
                    del self._cache[namespace]
            else:
                # Vider tout le cache
                count = self._stats["total_entries"]
                self._cache = {}
                self._stats["memory_usage_bytes"] = 0
                self._stats["total_entries"] = 0
                
        return count
        
    async def get_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques détaillées du cache
        
        Returns:
            Dictionnaire de statistiques
        """
        stats = dict(self._stats)
        
        # Calculer le taux de hit
        hit_rate = 0
        if stats["hits"] + stats["misses"] > 0:
            hit_rate = stats["hits"] / (stats["hits"] + stats["misses"])
        
        # Calculer le taux d'économie de tokens
        token_savings_rate = 0
        if stats["potential_tokens"] > 0:
            token_savings_rate = stats["tokens_saved"] / stats["potential_tokens"]
        
        # Calculer la taille mémoire approximative
        memory_size_mb = stats["memory_usage_bytes"] / (1024 * 1024)
        
        # Calculer le taux de correspondance sémantique
        semantic_match_rate = 0
        if stats["semantic_searches"] > 0:
            semantic_match_rate = stats["semantic_matches"] / stats["semantic_searches"]
        
        # Créer et retourner les statistiques consolidées
        stats["hit_rate"] = hit_rate
        stats["token_savings_rate"] = token_savings_rate
        stats["memory_size_mb"] = memory_size_mb
        stats["semantic_match_rate"] = semantic_match_rate
        
        # Information sur les namespaces
        namespace_stats = {}
        for namespace, entries in self._cache.items():
            namespace_size = sum(entry.size_bytes for entry in entries.values())
            namespace_stats[namespace] = {
                "entries": len(entries),
                "size_mb": namespace_size / (1024 * 1024)
            }
        
        stats["namespaces"] = namespace_stats
        
        return stats

# Fonction pour créer un singleton de cache
_global_cache = None

def get_cache_instance(
    embedding_function: Optional[Callable] = None,
    max_entries: int = 10000,
    default_ttl: int = 3600,
    max_memory_mb: int = 100
) -> IntelligentCache:
    """
    Récupère l'instance singleton du cache intelligent
    
    Args:
        embedding_function: Fonction pour générer des embeddings
        max_entries: Nombre maximum d'entrées
        default_ttl: Durée de vie par défaut
        max_memory_mb: Limite mémoire en MB
        
    Returns:
        Instance du cache intelligent
    """
    global _global_cache
    
    if _global_cache is None:
        # Lire les configurations depuis les variables d'environnement
        max_entries = int(os.getenv('CACHE_MAX_ENTRIES', max_entries))
        default_ttl = int(os.getenv('CACHE_DEFAULT_TTL', default_ttl))
        max_memory_mb = int(os.getenv('CACHE_MAX_MEMORY_MB', max_memory_mb))
        similarity_threshold = float(os.getenv('CACHE_SIMILARITY_THRESHOLD', 0.85))
        freshness_threshold = float(os.getenv('CACHE_FRESHNESS_THRESHOLD', 0.7))
        
        # Créer l'instance
        _global_cache = IntelligentCache(
            max_entries=max_entries,
            default_ttl=default_ttl,
            max_memory_mb=max_memory_mb,
            similarity_threshold=similarity_threshold,
            freshness_threshold=freshness_threshold,
            embedding_function=embedding_function
        )
        
        # Log de création
        logger.info(f"Cache intelligent initialisé: {max_entries} entrées, {max_memory_mb}MB max, TTL {default_ttl}s")
    
    return _global_cache
