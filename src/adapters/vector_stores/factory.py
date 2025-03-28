"""
Module factory.py - Factory pour les adaptateurs de bases vectorielles

Ce module fournit une factory pour créer des instances d'adaptateurs
de bases de données vectorielles selon le provider choisi.
"""

import logging
import os
from typing import Dict, List, Any, Optional, Union

# Import des adaptateurs
from .base import VectorStoreAdapter
from .qdrant_adapter import QdrantAdapter

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.vector_stores.factory")

class VectorStoreFactory:
    """
    Factory pour la création d'adaptateurs de bases vectorielles
    """
    
    @classmethod
    def create_adapter(
        cls, 
        provider: str = "auto",
        **kwargs
    ) -> VectorStoreAdapter:
        """
        Crée un adaptateur pour une base vectorielle
        
        Args:
            provider: Fournisseur de base vectorielle ('qdrant', 'auto', etc.)
            **kwargs: Paramètres spécifiques à l'adaptateur
            
        Returns:
            Adaptateur créé
            
        Raises:
            ValueError: Si le provider n'est pas pris en charge
        """
        # Normaliser le nom du provider
        provider = provider.lower()
        
        # Si 'auto', déterminer automatiquement le provider
        if provider == "auto":
            provider = cls._detect_provider()
        
        # Créer l'adaptateur selon le provider
        if provider == "qdrant":
            logger.info("Création d'un adaptateur Qdrant")
            return QdrantAdapter(**kwargs)
        # Ajouter d'autres adaptateurs ici (Pinecone, Weaviate, etc.)
        else:
            error_msg = f"Provider non pris en charge: {provider}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    @classmethod
    def _detect_provider(cls) -> str:
        """
        Détecte automatiquement le provider à utiliser en fonction
        des variables d'environnement et de la configuration
        
        Returns:
            Nom du provider détecté
        """
        # Vérifier les variables d'environnement pour Qdrant
        if os.getenv("QDRANT_URL") or os.getenv("QDRANT_HOST"):
            return "qdrant"
        
        # Ajouter d'autres détections ici selon les besoins
        
        # Par défaut, utiliser Qdrant
        logger.info("Aucun provider détecté automatiquement, utilisation de Qdrant par défaut")
        return "qdrant"
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """
        Liste les fournisseurs de bases vectorielles disponibles
        
        Returns:
            Liste des noms de providers
        """
        # Liste des providers pris en charge
        return ["qdrant"]
