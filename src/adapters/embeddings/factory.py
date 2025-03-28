"""
Module factory.py - Factory pour les services d'embedding

Ce module fournit une factory pour créer des instances de services d'embedding
de différents fournisseurs à partir d'une configuration.
"""

import logging
import os
from typing import Dict, List, Any, Optional, Union, Type

# Import des adaptateurs
from .base import EmbeddingService
from .openai_embedding import OpenAIEmbeddingService

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.embeddings.factory")

class EmbeddingServiceFactory:
    """
    Factory pour créer des instances de services d'embedding en fonction
    de la configuration et des fournisseurs disponibles.
    """
    
    # Registre des services disponibles
    _services: Dict[str, Type[EmbeddingService]] = {
        "openai": OpenAIEmbeddingService
    }
    
    @classmethod
    def register_service(cls, provider_name: str, service_class: Type[EmbeddingService]) -> None:
        """
        Enregistre un nouveau service d'embedding dans la factory
        
        Args:
            provider_name: Nom du fournisseur (openai, etc.)
            service_class: Classe de service à enregistrer
        """
        cls._services[provider_name.lower()] = service_class
        logger.info(f"Service d'embedding enregistré pour le fournisseur: {provider_name}")
    
    @classmethod
    def create_service(
        cls, 
        provider: str = "auto",
        llm_adapter=None,
        model: Optional[str] = None,
        cache_embeddings: bool = True,
        batch_size: int = 20,
        normalize_embeddings: bool = True,
        **kwargs
    ) -> EmbeddingService:
        """
        Crée un service d'embedding en fonction du fournisseur spécifié
        
        Args:
            provider: Nom du fournisseur (openai, auto)
            llm_adapter: Adaptateur LLM à utiliser (optionnel)
            model: Modèle à utiliser par défaut (optionnel)
            cache_embeddings: Activer le cache des embeddings
            batch_size: Taille maximale des batchs pour les requêtes multiples
            normalize_embeddings: Normaliser les vecteurs d'embedding
            **kwargs: Arguments additionnels à passer au service
            
        Returns:
            Instance de service d'embedding configurée
        """
        # Normaliser le nom du fournisseur
        provider = provider.lower()
        
        # Mode automatique: détecter le fournisseur en fonction des variables d'environnement
        if provider == "auto":
            if "OPENAI_API_KEY" in os.environ:
                provider = "openai"
            else:
                # Par défaut, utiliser OpenAI
                provider = "openai"
                logger.warning(
                    "Aucun fournisseur d'embedding détecté automatiquement. "
                    "Utilisation d'OpenAI par défaut."
                )
        
        # Vérifier si le fournisseur est supporté
        if provider not in cls._services:
            supported = ", ".join(cls._services.keys())
            logger.error(f"Fournisseur d'embedding non supporté: {provider}. Options: {supported}")
            raise ValueError(f"Fournisseur d'embedding non supporté: {provider}. Options: {supported}")
        
        # Créer le service avec les paramètres appropriés
        service_class = cls._services[provider]
        
        # Configurer les arguments spécifiques
        service_kwargs = kwargs.copy()
        
        if llm_adapter:
            service_kwargs["llm_adapter"] = llm_adapter
            
        if model:
            service_kwargs["model"] = model
            
        service_kwargs["cache_embeddings"] = cache_embeddings
        service_kwargs["batch_size"] = batch_size
        service_kwargs["normalize_embeddings"] = normalize_embeddings
        
        # Créer et retourner l'instance
        try:
            service = service_class(**service_kwargs)
            logger.info(f"Service d'embedding créé pour le fournisseur: {provider}")
            return service
        except Exception as e:
            logger.error(f"Erreur lors de la création du service d'embedding {provider}: {str(e)}")
            raise
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """
        Liste les fournisseurs d'embedding disponibles
        
        Returns:
            Liste des noms de fournisseurs supportés
        """
        return list(cls._services.keys())
