"""
Module d'adaptateurs pour bases de données vectorielles

Ce module fournit des adaptateurs pour différentes bases de données vectorielles,
permettant une abstraction complète du système sous-jacent.
"""

from .base import VectorStoreAdapter
from .qdrant_adapter import QdrantAdapter
from .factory import VectorStoreFactory

__all__ = [
    'VectorStoreAdapter',
    'QdrantAdapter',
    'VectorStoreFactory'
]
