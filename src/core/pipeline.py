"""
Module pipeline.py - Orchestration centrale du flux de traitement des requêtes

Ce module implémente le pipeline central qui orchestre tout le flux de traitement
des requêtes utilisateur, depuis l'analyse initiale jusqu'à la réponse formatée.
Il intègre des mécanismes de court-circuit pour optimiser la consommation de tokens
et améliorer les performances.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field

from src.core.query_engine import QueryEngine
from src.core.response_builder import ResponseBuilder
from src.infrastructure.cache import get_cache_instance
from src.infrastructure.metrics import MetricsCollector

# Configuration du logging
logger = logging.getLogger("ITS_HELP.core.pipeline")

@dataclass
class PipelineConfig:
    """Configuration pour le pipeline de traitement"""
    
    # Paramètres généraux
    enable_cache: bool = True
    cache_ttl: int = 3600  # Durée de vie du cache en secondes
    enable_metrics: bool = True
    log_level: str = "INFO"
    
    # Paramètres de performance
    timeout: float = 30.0  # Timeout général des opérations en secondes
    parallel_searches: bool = True  # Exécution en parallèle des recherches
    max_concurrent_searches: int = 6  # Nombre max de recherches concurrentes
    enable_circuit_breakers: bool = True  # Activer les circuit breakers
    
    # Paramètres de recherche
    search_limit: int = 10  # Nombre max de résultats par source
    similarity_threshold: float = 0.6  # Seuil minimal de similarité
    enable_semantic_search: bool = True  # Activer la recherche sémantique
    
    # Paramètres de génération de réponse
    max_context_items: int = 15  # Nombre max d'éléments de contexte à inclure
    enable_custom_instructions: bool = True  # Activer les instructions personnalisées
    
    # Collections à interroger (vide = toutes)
    enabled_collections: List[str] = field(default_factory=list)
    
    # Callbacks
    pre_processing_hook: Optional[Callable] = None
    post_processing_hook: Optional[Callable] = None


class Pipeline:
    """
    Pipeline d'orchestration central pour ITS Help
    
    Cette classe orchestre l'ensemble du flux de traitement:
    1. Réception et analyse de la requête utilisateur
    2. Court-circuit via cache intelligent si applicable
    3. Distribution et agrégation des recherches via QueryEngine
    4. Construction de la réponse via ResponseBuilder
    5. Métriques et instrumentation
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialise le pipeline avec la configuration spécifiée
        
        Args:
            config: Configuration du pipeline (PipelineConfig)
        """
        self.config = config or PipelineConfig()
        self._configure_logging()
        
        # Initialisation des composants
        self.query_engine = QueryEngine()
        self.response_builder = ResponseBuilder()
        self.cache = get_cache_instance() if self.config.enable_cache else None
        
        # Initialisation des métriques
        self.metrics = MetricsCollector() if self.config.enable_metrics else None
        
        # État interne
        self._initialized = False
        self._lock = asyncio.Lock()
        logger.info("Pipeline initialisé avec la configuration spécifiée")
    
    def _configure_logging(self):
        """Configure le niveau de logging selon la configuration"""
        logging.getLogger("ITS_HELP").setLevel(self.config.log_level)
    
    async def initialize(self):
        """Initialise les différents composants du pipeline"""
        if self._initialized:
            logger.debug("Pipeline déjà initialisé, ignoré")
            return
            
        async with self._lock:
            if self._initialized:  # Double-check avec le lock
                return
                
            logger.info("Initialisation du pipeline...")
            start_time = time.time()
            
            # Initialiser le moteur de requêtes
            await self.query_engine.initialize(
                parallel_execution=self.config.parallel_searches,
                max_concurrent=self.config.max_concurrent_searches,
                enable_circuit_breakers=self.config.enable_circuit_breakers
            )
            
            # Initialiser le générateur de réponses
            await self.response_builder.initialize(
                max_context_items=self.config.max_context_items,
                enable_custom_instructions=self.config.enable_custom_instructions
            )
            
            # Initialiser le cache si activé
            if self.cache:
                await self.cache.start_cleanup_task()
            
            # Initialiser les métriques si activées
            if self.metrics:
                await self.metrics.initialize()
            
            self._initialized = True
            
            duration = time.time() - start_time
            logger.info(f"Pipeline initialisé en {duration:.2f}s")
    
    async def process_query(self, query: str, user_id: Optional[str] = None, 
                         metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Traite une requête utilisateur de bout en bout
        
        Args:
            query: Texte de la requête
            user_id: Identifiant de l'utilisateur (pour personnalisation)
            metadata: Métadonnées additionnelles pour la requête
            
        Returns:
            Réponse formatée avec résultats et métriques
        """
        metadata = metadata or {}
        request_id = metadata.get("request_id", f"req_{int(time.time() * 1000)}")
        
        # S'assurer que le pipeline est initialisé
        if not self._initialized:
            await self.initialize()
        
        # Début du timing
        start_time = time.time()
        log_prefix = f"[{request_id}]"
        logger.info(f"{log_prefix} Traitement de la requête: {query}")
        
        # Métriques - début de requête
        if self.metrics:
            self.metrics.start_request(request_id, query, user_id)
        
        # Prétraitement via hook si configuré
        if self.config.pre_processing_hook:
            query, metadata = await self.config.pre_processing_hook(query, metadata)
        
        # Vérification du cache (court-circuit)
        cache_key = None
        if self.cache and self.config.enable_cache:
            cache_namespace = "user_queries"
            cache_key = f"query:{query}"
            
            # Tentative de récupération depuis le cache
            cached_response = await self.cache.get(cache_namespace, cache_key, 
                                                include_similar=True, 
                                                similarity_threshold=0.92)
            
            if cached_response:
                logger.info(f"{log_prefix} Réponse trouvée dans le cache")
                
                # Mise à jour des métriques
                if self.metrics:
                    self.metrics.record_cache_hit(request_id)
                    self.metrics.end_request(request_id)
                
                # Ajout des métadonnées de cache
                cached_response["metadata"]["source"] = "cache"
                cached_response["metadata"]["processing_time"] = time.time() - start_time
                
                return cached_response
        
        # Exécution de la recherche via QueryEngine
        logger.info(f"{log_prefix} Exécution de la recherche")
        query_result = await self.query_engine.execute_query(
            query=query,
            collections=self.config.enabled_collections if self.config.enabled_collections else None,
            limit_per_collection=self.config.search_limit,
            similarity_threshold=self.config.similarity_threshold,
            enable_semantic=self.config.enable_semantic_search,
            timeout=self.config.timeout,
            metadata=metadata
        )
        
        # Métriques - recherche terminée
        if self.metrics:
            self.metrics.record_search_completed(
                request_id, 
                total_results=query_result.total_results,
                sources=query_result.sources
            )
        
        # Construction de la réponse
        logger.info(f"{log_prefix} Construction de la réponse")
        response = await self.response_builder.build_response(
            query=query,
            query_result=query_result,
            user_id=user_id,
            metadata=metadata
        )
        
        # Mise en cache de la réponse
        if self.cache and self.config.enable_cache and cache_key:
            await self.cache.set(
                namespace="user_queries",
                key=cache_key,
                value=response,
                ttl=self.config.cache_ttl,
                text_for_embedding=query  # Pour permettre la recherche par similarité
            )
        
        # Durée totale
        duration = time.time() - start_time
        logger.info(f"{log_prefix} Requête traitée en {duration:.2f}s")
        
        # Métriques - fin de requête
        if self.metrics:
            self.metrics.record_response_size(request_id, len(str(response)))
            self.metrics.end_request(request_id, duration)
        
        # Post-traitement via hook si configuré
        if self.config.post_processing_hook:
            response = await self.config.post_processing_hook(response, metadata)
        
        # Ajout des métadonnées de performance
        response["metadata"]["processing_time"] = duration
        response["metadata"]["source"] = "direct"
        
        return response
    
    async def shutdown(self):
        """Arrête proprement le pipeline et ses ressources"""
        logger.info("Arrêt du pipeline...")
        
        # Arrêt des composants
        if hasattr(self.query_engine, 'shutdown'):
            await self.query_engine.shutdown()
            
        if hasattr(self.response_builder, 'shutdown'):
            await self.response_builder.shutdown()
            
        # Arrêt du cache si activé
        if self.cache and hasattr(self.cache, 'shutdown'):
            await self.cache.shutdown()
            
        # Arrêt des métriques si activées
        if self.metrics and hasattr(self.metrics, 'shutdown'):
            await self.metrics.shutdown()
            
        logger.info("Pipeline arrêté avec succès")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Renvoie l'état actuel du pipeline et de ses composants
        
        Returns:
            Dictionnaire avec les informations d'état
        """
        status = {
            "initialized": self._initialized,
            "config": {k: v for k, v in vars(self.config).items() 
                      if not callable(v) and not k.startswith('_')},
            "components": {
                "query_engine": self.query_engine.get_status() if hasattr(self.query_engine, 'get_status') else "N/A",
                "response_builder": self.response_builder.get_status() if hasattr(self.response_builder, 'get_status') else "N/A",
                "cache": self.cache.get_status() if self.cache and hasattr(self.cache, 'get_status') else "N/A",
                "metrics": self.metrics.get_status() if self.metrics and hasattr(self.metrics, 'get_status') else "N/A"
            }
        }
        
        return status
