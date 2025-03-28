"""
Module d'adaptateurs d'embedding pour ITS Help

Ce module fournit des services d'embedding pour différents fournisseurs,
permettant une abstraction complète du provider sous-jacent.
"""

from .base import EmbeddingService
from .openai_embedding import OpenAIEmbeddingService
from .factory import EmbeddingServiceFactory

__all__ = [
    'EmbeddingService',
    'OpenAIEmbeddingService',
    'EmbeddingServiceFactory'
]
