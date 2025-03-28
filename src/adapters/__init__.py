"""
Module adapters - Point d'entrée principal pour les adaptateurs

Ce module unifie tous les adaptateurs (LLM, embeddings, bases vectorielles)
et facilite leur utilisation conjointe dans le système.
"""

# Import des sous-modules
from . import llm
from . import embeddings
from . import vector_stores

# Importer les factory principales pour un accès direct
from .llm.factory import LLMAdapterFactory
from .embeddings.factory import EmbeddingServiceFactory
from .vector_stores.factory import VectorStoreFactory

__all__ = [
    'llm',
    'embeddings',
    'vector_stores',
    'LLMAdapterFactory',
    'EmbeddingServiceFactory',
    'VectorStoreFactory',
]
