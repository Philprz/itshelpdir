# À ajouter dans un fichier embedding_service.py

import asyncio
import logging
import time
from collections import OrderedDict, Counter
import os
import pickle
from typing import List, Optional

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
        
        # Nouvelles variables pour l'amélioration du cache
        self.access_frequency = Counter()  # Compteur de fréquence d'utilisation
        self.last_cache_evaluation = time.monotonic()  # Dernière évaluation du cache
        self.cache_evaluation_interval = 3600  # Évaluer l'efficacité du cache chaque heure
        self.frequent_queries_threshold = 5  # Nombre minimal d'accès pour considérer une entrée fréquente
        self.last_cache_cleanup = time.monotonic()  # Dernier nettoyage du cache
        self.cache_cleanup_interval = 600  # Nettoyer le cache toutes les 10 minutes
        self.cache_file_path = os.getenv('EMBEDDING_CACHE_FILE', 'embedding_cache.pkl')  # Fichier de cache persistant
        
        # Charger le cache persistant au démarrage
        self._load_cache_from_disk()
        
        # Planifier l'évaluation périodique du cache
        asyncio.create_task(self._schedule_cache_maintenance())
        
    async def _schedule_cache_maintenance(self):
        """Planifie les tâches de maintenance périodiques du cache."""
        while True:
            # Attendre un intervalle avant la prochaine évaluation
            await asyncio.sleep(min(self.cache_evaluation_interval, self.cache_cleanup_interval))
            
            current_time = time.monotonic()
            
            # Évaluation périodique du cache
            if current_time - self.last_cache_evaluation >= self.cache_evaluation_interval:
                await self._evaluate_cache_efficiency()
                self.last_cache_evaluation = current_time
                
            # Nettoyage périodique du cache
            if current_time - self.last_cache_cleanup >= self.cache_cleanup_interval:
                await self._cleanup_cache()
                self.last_cache_cleanup = current_time
                
            # Sauvegarde périodique du cache
            await self._save_cache_to_disk()

    async def _evaluate_cache_efficiency(self):
        """Évalue l'efficacité du cache et ajuste les paramètres si nécessaire."""
        total_requests = self.hit_count + self.miss_count
        if total_requests == 0:
            return
            
        hit_rate = (self.hit_count / total_requests) * 100
        self.logger.info(f"Évaluation du cache: taux de succès {hit_rate:.1f}% ({self.hit_count}/{total_requests})")
        
        # Identifier les entrées fréquemment utilisées
        frequent_entries = {k: v for k, v in self.access_frequency.items() if v >= self.frequent_queries_threshold}
        self.logger.info(f"Entrées fréquentes identifiées: {len(frequent_entries)}")
        
        # Ajuster la taille du cache si nécessaire
        if hit_rate < 50 and len(self.l1_cache) >= self.l1_cache_max_size * 0.9:
            # Si le taux de succès est faible et le cache presque plein, augmenter sa taille
            old_size = self.l1_cache_max_size
            self.l1_cache_max_size = min(self.l1_cache_max_size * 2, 10000)  # Limiter à 10000 entrées max
            self.logger.info(f"Taille du cache L1 augmentée: {old_size} -> {self.l1_cache_max_size}")
        elif hit_rate > 90 and len(self.l1_cache) < self.l1_cache_max_size * 0.5:
            # Si le taux de succès est élevé et le cache peu rempli, réduire sa taille
            old_size = self.l1_cache_max_size
            self.l1_cache_max_size = max(self.l1_cache_max_size // 2, 100)  # Minimum 100 entrées
            self.logger.info(f"Taille du cache L1 réduite: {old_size} -> {self.l1_cache_max_size}")
            
        # Ajuster le TTL en fonction du taux de succès
        if hit_rate < 40:
            old_ttl = self.l1_cache_ttl
            self.l1_cache_ttl = min(self.l1_cache_ttl * 2, 3600)  # Maximum 1 heure
            self.logger.info(f"TTL du cache augmenté: {old_ttl}s -> {self.l1_cache_ttl}s")
        elif hit_rate > 85 and self.l1_cache_ttl > 300:
            old_ttl = self.l1_cache_ttl
            self.l1_cache_ttl = max(self.l1_cache_ttl // 2, 300)  # Minimum 5 minutes
            self.logger.info(f"TTL du cache réduit: {old_ttl}s -> {self.l1_cache_ttl}s")

    async def _cleanup_cache(self):
        """Nettoie le cache en supprimant les entrées expirées et peu utilisées."""
        current_time = time.monotonic()
        keys_to_remove = []
        
        # Identifier les entrées expirées
        for key, timestamp in self.l1_cache_timestamps.items():
            # Si l'entrée est fréquemment accédée, prolonger son TTL
            frequency = self.access_frequency.get(key, 0)
            ttl_multiplier = min(frequency, 10)  # Maximum 10x le TTL standard
            
            # Calculer le TTL effectif en fonction de la fréquence d'utilisation
            effective_ttl = self.l1_cache_ttl * (1 + ttl_multiplier / 10)
            
            # Vérifier si l'entrée est expirée
            if current_time - timestamp > effective_ttl:
                keys_to_remove.append(key)
                
        # Supprimer les entrées expirées
        removed_count = 0
        for key in keys_to_remove:
            if key in self.l1_cache:
                del self.l1_cache[key]
                del self.l1_cache_timestamps[key]
                removed_count += 1
                
        self.logger.info(f"Nettoyage du cache: {removed_count} entrées expirées supprimées")
        
        # Si après suppression le cache reste trop grand, supprimer les entrées les moins fréquentes
        if len(self.l1_cache) > self.l1_cache_max_size * 0.9:
            overage = len(self.l1_cache) - int(self.l1_cache_max_size * 0.8)  # Réduire à 80% pour éviter des nettoyages trop fréquents
            
            # Trier les entrées par fréquence d'utilisation (les moins utilisées d'abord)
            cache_entries = [(k, self.access_frequency.get(k, 0)) for k in self.l1_cache.keys()]
            cache_entries.sort(key=lambda x: x[1])
            
            # Supprimer les entrées les moins utilisées
            for key, _ in cache_entries[:overage]:
                if key in self.l1_cache:
                    del self.l1_cache[key]
                    if key in self.l1_cache_timestamps:
                        del self.l1_cache_timestamps[key]
                    if key in self.access_frequency:
                        del self.access_frequency[key]
                    removed_count += 1
                    
            self.logger.info(f"Nettoyage complémentaire: {overage} entrées peu utilisées supprimées")
            
        # Réduire le compteur de fréquence pour les entrées peu accédées
        for key in list(self.access_frequency.keys()):
            if key not in self.l1_cache:
                del self.access_frequency[key]
            elif self.access_frequency[key] > 0:
                # Décroissance progressive pour éviter de pénaliser trop rapidement les entrées
                self.access_frequency[key] = max(1, int(self.access_frequency[key] * 0.9))
                
        return removed_count

    async def preload_frequent_queries(self, queries: List[str]):
        """
        Précharge les embeddings pour une liste de requêtes fréquentes.
        
        Args:
            queries: Liste des requêtes fréquentes à précharger
        
        Returns:
            Dict: Informations sur le préchargement
        """
        if not queries:
            return {"status": "error", "message": "Aucune requête fournie"}
            
        self.logger.info(f"Préchargement de {len(queries)} requêtes fréquentes")
        
        # Générer les embeddings en batch
        batch_size = 20
        loaded_count = 0
        already_cached = 0
        
        for i in range(0, len(queries), batch_size):
            batch = queries[i:i+batch_size]
            
            # Vérifier quelles requêtes sont déjà en cache
            cache_keys = [self._get_cache_key(query) for query in batch]
            to_generate = []
            
            for j, (query, key) in enumerate(zip(batch, cache_keys)):
                # Vérifier d'abord le cache L1
                if key in self.l1_cache:
                    # Marquer comme fréquent pour prolonger sa durée de vie
                    self.access_frequency[key] += self.frequent_queries_threshold
                    already_cached += 1
                    continue
                    
                # Vérifier ensuite le cache L2 si disponible
                if self.l2_cache:
                    cached = await self.l2_cache.get(key, self.namespace)
                    if cached:
                        # Ajouter au cache L1 et marquer comme fréquent
                        self._update_l1_cache(key, cached)
                        self.access_frequency[key] += self.frequent_queries_threshold
                        already_cached += 1
                        continue
                        
                # Si pas en cache, ajouter à la liste pour génération
                to_generate.append((j, query))
                
            # Générer les embeddings manquants
            if to_generate:
                texts = [item[1] for item in to_generate]
                
                try:
                    response = await self.client.embeddings.create(
                        input=texts,
                        model=self.model
                    )
                    
                    if response.data and len(response.data) == len(texts):
                        for k, embedding_data in enumerate(response.data):
                            j, query = to_generate[k]
                            vector = embedding_data.embedding
                            
                            if self._validate_vector(vector):
                                key = cache_keys[j]
                                
                                # Mettre en cache avec priorité élevée
                                self._update_l1_cache(key, vector)
                                self.access_frequency[key] += self.frequent_queries_threshold * 2  # Priorité extra haute
                                
                                # Mettre aussi dans le cache L2 si disponible
                                if self.l2_cache:
                                    asyncio.create_task(self.l2_cache.set(key, vector, self.namespace))
                                    
                                loaded_count += 1
                                
                except Exception as e:
                    self.logger.error(f"Erreur lors du préchargement: {str(e)}")
                    
            # Pause pour éviter de surcharger l'API
            if i + batch_size < len(queries):
                await asyncio.sleep(0.5)
                
        self.logger.info(f"Préchargement terminé: {loaded_count} générés, {already_cached} déjà en cache")
        
        # Sauvegarder le cache mis à jour
        await self._save_cache_to_disk()
        
        return {
            "status": "success",
            "preloaded": loaded_count,
            "already_cached": already_cached,
            "total": len(queries)
        }

    async def _save_cache_to_disk(self):
        """Sauvegarde le cache L1 sur disque pour persistance."""
        if not self.cache_file_path:
            return False
            
        try:
            # Construire la structure de données à sauvegarder
            cache_data = {
                "l1_cache": dict(self.l1_cache),
                "l1_cache_timestamps": dict(self.l1_cache_timestamps),
                "access_frequency": dict(self.access_frequency),
                "stats": self.stats,
                "metadata": {
                    "dimension": self.dimension,
                    "model": self.model,
                    "saved_at": time.time(),
                    "entry_count": len(self.l1_cache)
                }
            }
            
            # Sauvegarder dans un fichier temporaire d'abord
            temp_file = f"{self.cache_file_path}.tmp"
            
            with open(temp_file, 'wb') as f:
                pickle.dump(cache_data, f)
                
            # Remplacer le fichier existant de façon atomique
            os.replace(temp_file, self.cache_file_path)
            
            self.logger.info(f"Cache sauvegardé sur disque: {len(self.l1_cache)} entrées")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde du cache: {str(e)}")
            return False

    def _load_cache_from_disk(self):
        """Charge le cache depuis le disque au démarrage."""
        if not self.cache_file_path or not os.path.exists(self.cache_file_path):
            return False
            
        try:
            with open(self.cache_file_path, 'rb') as f:
                cache_data = pickle.load(f)
                
            # Vérifier la validité des données
            if not isinstance(cache_data, dict) or "l1_cache" not in cache_data:
                self.logger.warning("Format de fichier de cache invalide")
                return False
                
            # Vérifier la compatibilité du modèle
            metadata = cache_data.get("metadata", {})
            if metadata.get("model") != self.model or metadata.get("dimension") != self.dimension:
                self.logger.warning(f"Cache incompatible: modèle={metadata.get('model')}, dimension={metadata.get('dimension')}")
                return False
                
            # Charger les données du cache
            self.l1_cache = OrderedDict(cache_data["l1_cache"])
            self.l1_cache_timestamps = dict(cache_data.get("l1_cache_timestamps", {}))
            self.access_frequency = Counter(cache_data.get("access_frequency", {}))
            
            # Mettre à jour les statistiques
            if "stats" in cache_data:
                self.stats.update(cache_data["stats"])
                
            # Limiter la taille du cache
            if len(self.l1_cache) > self.l1_cache_max_size:
                # Supprimer les entrées les moins fréquentes
                entries = [(k, self.access_frequency.get(k, 0)) for k in self.l1_cache]
                entries.sort(key=lambda x: x[1])
                
                # Garder seulement les entrées les plus fréquentes
                entries_to_keep = entries[-(self.l1_cache_max_size):]
                keep_keys = {k for k, _ in entries_to_keep}
                
                # Reconstruire le cache
                self.l1_cache = OrderedDict((k, v) for k, v in self.l1_cache.items() if k in keep_keys)
                self.l1_cache_timestamps = {k: v for k, v in self.l1_cache_timestamps.items() if k in keep_keys}
                
            self.logger.info(f"Cache chargé depuis le disque: {len(self.l1_cache)} entrées")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement du cache: {str(e)}")
            return False

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
            # Incrémenter le compteur de fréquence
            self.access_frequency[cache_key] += 1
            self.logger.debug(f"Cache L1 hit pour '{text[:30]}...'")
            return self.l1_cache[cache_key]
            
        # Vérification du cache L2 (externe)
        if self.l2_cache:
            try:
                cached_vector = await self.l2_cache.get(cache_key, self.namespace)
                if cached_vector:
                    # Mise à jour du cache L1
                    self._update_l1_cache(cache_key, cached_vector)
                    # Incrémenter le compteur de fréquence
                    self.access_frequency[cache_key] += 1
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

    def _update_l1_cache(self, cache_key: str, vector: List[float]):
        """
        Met à jour le cache L1 avec un nouvel embedding, en respectant la taille maximale.
        
        Args:
            cache_key: Clé de cache
            vector: Vecteur d'embedding à stocker
        """
        # Si le cache est presque plein, nettoyer en fonction de la fréquence d'utilisation
        if len(self.l1_cache) >= self.l1_cache_max_size:
            # Plutôt que de simplement supprimer l'élément le plus ancien,
            # on supprime l'élément le moins fréquemment utilisé
            if self.access_frequency:
                # Identifier les candidats à supprimer (les 10% moins utilisés)
                candidates = [(k, self.access_frequency.get(k, 0)) 
                             for k in self.l1_cache.keys()]
                candidates.sort(key=lambda x: x[1])
                
                # Supprimer un élément parmi les moins utilisés
                if candidates:
                    oldest_key = candidates[0][0]
                    del self.l1_cache[oldest_key]
                    if oldest_key in self.l1_cache_timestamps:
                        del self.l1_cache_timestamps[oldest_key]
            else:
                # Fallback au comportement LRU si pas de données de fréquence
                oldest_key = next(iter(self.l1_cache))
                del self.l1_cache[oldest_key]
                if oldest_key in self.l1_cache_timestamps:
                    del self.l1_cache_timestamps[oldest_key]
                
        # Ajouter le nouvel élément
        self.l1_cache[cache_key] = vector
        self.l1_cache_timestamps[cache_key] = time.monotonic()
        # Initialiser ou incrémenter le compteur de fréquence
        self.access_frequency[cache_key] = self.access_frequency.get(cache_key, 0) + 1

    def get_stats(self):
        """Retourne les statistiques d'utilisation."""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total) * 100 if total > 0 else 0
        
        # Calculer des statistiques avancées sur le cache
        frequent_entries = sum(1 for v in self.access_frequency.values() if v >= self.frequent_queries_threshold)
        avg_frequency = sum(self.access_frequency.values()) / len(self.access_frequency) if self.access_frequency else 0
        
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
            "failed_api_calls": self.failed_api_calls,
            "cache_size": len(self.l1_cache),
            "cache_max_size": self.l1_cache_max_size,
            "frequent_entries": frequent_entries,
            "average_frequency": f"{avg_frequency:.1f}",
            "cache_ttl": self.l1_cache_ttl
        }