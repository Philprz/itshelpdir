"""
Module d'adaptateurs LLM pour ITS Help

Ce module fournit des adaptateurs pour différents fournisseurs de modèles de langage,
permettant une abstraction complète du provider sous-jacent.
"""

from .base import LLMAdapter, LLMMessage, LLMResponse, LLMConfig
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter
from .factory import LLMAdapterFactory

__all__ = [
    'LLMAdapter', 'LLMMessage', 'LLMResponse', 'LLMConfig',
    'OpenAIAdapter', 'AnthropicAdapter', 'LLMAdapterFactory'
]
