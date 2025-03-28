"""
Module d'infrastructure du système ITS Help

Ce module contient les composants d'infrastructure partagés:
- Cache intelligent avec recherche par similarité
- Système de persistance des interactions
- Mécanismes de métriques et performance
"""

from .cache import IntelligentCache, get_cache_instance, CacheEntry

__all__ = ['IntelligentCache', 'get_cache_instance', 'CacheEntry']
