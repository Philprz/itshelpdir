"""
Module base.py - Interface abstraite pour les adaptateurs LLM

Ce module définit l'interface commune que tous les adaptateurs LLM
doivent implémenter, permettant une abstraction complète du provider sous-jacent.
"""

import abc
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass

@dataclass
class LLMMessage:
    """Représentation unifiée d'un message pour les LLM"""
    
    role: str  # "system", "user", "assistant", "function"
    content: str
    name: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None

@dataclass
class LLMResponse:
    """Représentation unifiée de la réponse d'un LLM"""
    
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str
    function_call: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[Any] = None  # Réponse brute pour debugging

@dataclass
class LLMConfig:
    """Configuration pour un appel LLM"""
    
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout: float = 60.0
    stop_sequences: Optional[List[str]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    response_format: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class LLMAdapter(abc.ABC):
    """Interface abstraite pour tous les adaptateurs LLM"""
    
    @abc.abstractmethod
    async def complete(
        self, 
        messages: List[LLMMessage], 
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        Génère une complétion basée sur un historique de messages
        
        Args:
            messages: Liste de messages représentant la conversation
            config: Configuration pour l'appel (températures, etc.)
            
        Returns:
            Réponse générée
        """
        pass
    
    @abc.abstractmethod
    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Génère un embedding pour un texte donné
        
        Args:
            text: Texte à encoder
            model: Modèle d'embedding à utiliser (optionnel)
            
        Returns:
            Vecteur d'embedding
        """
        pass
    
    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """
        Nom du fournisseur de LLM (OpenAI, Claude, etc.)
        
        Returns:
            Nom du provider
        """
        pass
    
    @property
    @abc.abstractmethod
    def available_models(self) -> List[str]:
        """
        Liste des modèles disponibles pour ce provider
        
        Returns:
            Liste des identifiants de modèles disponibles
        """
        pass
    
    @abc.abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité et l'état de santé du provider
        
        Returns:
            Dictionnaire avec statut et informations
        """
        pass
