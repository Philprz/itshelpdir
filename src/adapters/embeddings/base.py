"""
Module base.py - Interface abstraite pour les services d'embedding

Ce module définit l'interface commune que tous les services d'embedding
doivent implémenter, permettant une abstraction complète du provider sous-jacent.
"""

import abc
from typing import Dict, List, Any, Optional, Union, Callable

class EmbeddingService(abc.ABC):
    """Interface abstraite pour tous les services d'embedding"""
    
    @abc.abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """
        Génère un embedding vectoriel pour un texte
        
        Args:
            text: Texte à vectoriser
            
        Returns:
            Vecteur d'embedding
        """
        pass
    
    @abc.abstractmethod
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Génère des embeddings en batch pour plusieurs textes
        
        Args:
            texts: Liste de textes à vectoriser
            
        Returns:
            Liste de vecteurs d'embedding
        """
        pass
    
    @abc.abstractmethod
    async def similarity(self, text1: str, text2: str) -> float:
        """
        Calcule la similarité cosinus entre deux textes
        
        Args:
            text1: Premier texte
            text2: Second texte
            
        Returns:
            Score de similarité (0-1)
        """
        pass
    
    @abc.abstractmethod
    async def rank_by_similarity(self, query: str, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Classe une liste de textes par similarité avec une requête
        
        Args:
            query: Texte de requête
            texts: Liste de textes à classer
            
        Returns:
            Liste de dictionnaires {texte, score, index} triés par score décroissant
        """
        pass
    
    @property
    @abc.abstractmethod
    def dimensions(self) -> int:
        """
        Nombre de dimensions des embeddings générés
        
        Returns:
            Nombre de dimensions
        """
        pass
    
    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """
        Nom du fournisseur d'embedding
        
        Returns:
            Nom du provider
        """
        pass
    
    @abc.abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité et l'état de santé du service
        
        Returns:
            Dictionnaire avec statut et informations
        """
        pass
