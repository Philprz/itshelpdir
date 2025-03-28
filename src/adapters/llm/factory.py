"""
Module factory.py - Factory pour les adaptateurs LLM

Ce module fournit une factory pour créer des instances d'adaptateurs LLM
de différents fournisseurs (OpenAI, Anthropic, etc.) à partir d'une configuration.
"""

import logging
import os
from typing import Dict, List, Any, Optional, Union, Type

# Import des adaptateurs
from .base import LLMAdapter
from .openai_adapter import OpenAIAdapter
from .anthropic_adapter import AnthropicAdapter

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.llm.factory")

class LLMAdapterFactory:
    """
    Factory pour créer des instances d'adaptateurs LLM en fonction
    de la configuration et des fournisseurs disponibles.
    """
    
    # Registre des adaptateurs disponibles
    _adapters: Dict[str, Type[LLMAdapter]] = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter
    }
    
    @classmethod
    def register_adapter(cls, provider_name: str, adapter_class: Type[LLMAdapter]) -> None:
        """
        Enregistre un nouvel adaptateur dans la factory
        
        Args:
            provider_name: Nom du fournisseur (openai, anthropic, etc.)
            adapter_class: Classe d'adaptateur à enregistrer
        """
        cls._adapters[provider_name.lower()] = adapter_class
        logger.info(f"Adaptateur LLM enregistré pour le fournisseur: {provider_name}")
    
    @classmethod
    def create_adapter(
        cls, 
        provider: str = "auto",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMAdapter:
        """
        Crée un adaptateur LLM en fonction du fournisseur spécifié
        
        Args:
            provider: Nom du fournisseur (openai, anthropic, auto)
            api_key: Clé API pour le fournisseur (optionnel)
            model: Modèle à utiliser par défaut (optionnel)
            **kwargs: Arguments additionnels à passer à l'adaptateur
            
        Returns:
            Instance d'adaptateur LLM configurée
        """
        # Normaliser le nom du fournisseur
        provider = provider.lower()
        
        # Mode automatique: détecter le fournisseur en fonction des variables d'environnement
        if provider == "auto":
            if "OPENAI_API_KEY" in os.environ:
                provider = "openai"
            elif "ANTHROPIC_API_KEY" in os.environ:
                provider = "anthropic"
            else:
                # Par défaut, utiliser OpenAI
                provider = "openai"
                logger.warning(
                    "Aucun fournisseur LLM détecté automatiquement. "
                    "Utilisation d'OpenAI par défaut."
                )
        
        # Vérifier si le fournisseur est supporté
        if provider not in cls._adapters:
            supported = ", ".join(cls._adapters.keys())
            logger.error(f"Fournisseur LLM non supporté: {provider}. Options: {supported}")
            raise ValueError(f"Fournisseur LLM non supporté: {provider}. Options: {supported}")
        
        # Créer l'adaptateur avec les paramètres appropriés
        adapter_class = cls._adapters[provider]
        
        # Configurer les arguments spécifiques
        adapter_kwargs = kwargs.copy()
        
        if api_key:
            adapter_kwargs["api_key"] = api_key
            
        if model:
            adapter_kwargs["default_model"] = model
        
        # Créer et retourner l'instance
        try:
            adapter = adapter_class(**adapter_kwargs)
            logger.info(f"Adaptateur LLM créé pour le fournisseur: {provider}")
            return adapter
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'adaptateur {provider}: {str(e)}")
            raise
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """
        Liste les fournisseurs LLM disponibles
        
        Returns:
            Liste des noms de fournisseurs supportés
        """
        return list(cls._adapters.keys())
