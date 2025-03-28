"""
Module de compatibilité pour le cache intelligent

Ce module adapte la nouvelle implémentation du cache intelligent
pour maintenir la compatibilité avec le système existant.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
import os

# Import du nouveau système de cache
from .cache import get_cache_instance, IntelligentCache

# Configuration du logging
logger = logging.getLogger("ITS_HELP.infrastructure.cache_compat")

class GlobalCache:
    """
    Adaptateur de compatibilité pour maintenir l'API du GlobalCache existant
    tout en utilisant le nouveau cache intelligent en arrière-plan.
    """
    
    def __init__(self, max_size=10000, ttl=3600):
        """
        Initialise l'adaptateur de cache
        
        Args:
            max_size: Taille maximale du cache (transmise au cache intelligent)
            ttl: Durée de vie par défaut en secondes
        """
        self._max_size = max_size
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._initialized = True
        self._cleanup_task = None
        
        # Sera initialisé lors du premier appel à _get_cache()
        self._intelligent_cache = None
        
        logger.info(f"Adaptateur GlobalCache initialisé avec compatibilité vers IntelligentCache")
    
    async def _get_cache(self) -> IntelligentCache:
        """
        Récupère ou initialise le cache intelligent sous-jacent
        
        Returns:
            Instance du cache intelligent
        """
        if self._intelligent_cache is None:
            # Initialiser le cache avec les paramètres équivalents
            self._intelligent_cache = get_cache_instance(
                max_entries=self._max_size,
                default_ttl=self._ttl,
                max_memory_mb=int(os.getenv('CACHE_MAX_MEMORY_MB', 100))
            )
            
            # Démarrer la tâche de nettoyage
            await self._intelligent_cache.start_cleanup_task()
            
        return self._intelligent_cache
    
    async def start_cleanup_task(self):
        """
        Démarre la tâche de nettoyage périodique
        Méthode de compatibilité - le cache intelligent gère cela automatiquement
        """
        cache = await self._get_cache()
        await cache.start_cleanup_task()
    
    async def get(self, key: str, namespace: str = "default") -> Any:
        """
        Récupère une valeur du cache
        
        Args:
            key: Clé à rechercher
            namespace: Espace de noms
            
        Returns:
            Valeur trouvée ou None
        """
        cache = await self._get_cache()
        
        # Utiliser le nouveau cache avec recherche sémantique désactivée par défaut
        # pour conserver le comportement original
        value = await cache.get(key, namespace=namespace, allow_semantic_match=False)
        return value
    
    async def get_semantic(self, key: str, namespace: str = "default") -> Any:
        """
        Récupère une valeur du cache avec recherche sémantique activée
        
        Args:
            key: Clé à rechercher
            namespace: Espace de noms
            
        Returns:
            Valeur trouvée ou None
        """
        cache = await self._get_cache()
        
        # Utiliser le cache avec recherche sémantique activée
        value = await cache.get(key, namespace=namespace, allow_semantic_match=True)
        return value
    
    async def set(self, key: str, value: Any, namespace: str = "default") -> None:
        """
        Stocke une valeur dans le cache
        
        Args:
            key: Clé d'accès
            value: Valeur à stocker
            namespace: Espace de noms
        """
        cache = await self._get_cache()
        
        # Déterminer si nous devons générer un embedding pour cette entrée
        # Par défaut, on génère un embedding pour les chaînes plus longues
        should_embed = False
        if isinstance(value, str) and len(value) > 50:
            should_embed = True
            
        await cache.set(
            key=key, 
            value=value, 
            namespace=namespace,
            should_embed=should_embed
        )
    
    async def clear(self, namespace: Optional[str] = None) -> None:
        """
        Vide le cache ou un namespace spécifique
        
        Args:
            namespace: Namespace à vider (None = tout le cache)
        """
        cache = await self._get_cache()
        await cache.clear(namespace)
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques du cache
        
        Returns:
            Dictionnaire de statistiques
        """
        cache = await self._get_cache()
        return await cache.get_stats()
    
    def status(self) -> Dict[str, Any]:
        """
        Méthode synchrone pour obtenir un statut simplifié
        Méthode de compatibilité pour les appels synchrones
        
        Returns:
            Dictionnaire avec informations de base sur le cache
        """
        return {
            "type": "IntelligentCache",
            "max_size": self._max_size,
            "ttl": self._ttl,
            "initialized": self._initialized
        }
    
    async def get_embedding(self, text: str) -> List[float]:
        """
        Méthode de compatibilité pour l'ancien système
        Retourne None car le cache intelligent gère cela différemment
        
        Args:
            text: Texte pour lequel on voulait un embedding
            
        Returns:
            None (méthode de compatibilité)
        """
        logger.warning("get_embedding appelé sur GlobalCache - cette méthode est obsolète")
        return None
        
    async def set_embedding(self, text: str, embedding: List[float]) -> None:
        """
        Méthode de compatibilité pour l'ancien système
        Ne fait rien car le cache intelligent gère cela différemment
        
        Args:
            text: Texte
            embedding: Embedding à stocker
        """
        logger.warning("set_embedding appelé sur GlobalCache - cette méthode est obsolète")
        pass

# Créer l'instance de compatibilité globale
global_cache = GlobalCache(
    max_size=int(os.getenv('EMBEDDING_CACHE_SIZE', 2000)),
    ttl=int(os.getenv('EMBEDDING_CACHE_TTL', 3600))
)
