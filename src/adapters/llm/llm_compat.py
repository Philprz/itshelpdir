"""
Module llm_compat.py - Adaptateur de compatibilité pour les LLM

Ce module fournit une interface de compatibilité entre la nouvelle
architecture d'adaptateurs LLM et le système existant.
"""

import logging
import os
import asyncio
from typing import Dict, List, Any, Optional, Union

# Import de la nouvelle architecture
from .base import LLMMessage, LLMConfig, LLMResponse
from .factory import LLMAdapterFactory

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.llm.llm_compat")

class LLMService:
    """
    Service LLM compatible avec l'ancien système.
    Ce service est un adaptateur qui utilise la nouvelle architecture
    tout en exposant une interface compatible avec le code existant.
    """
    
    def __init__(
        self, 
        openai_client=None, 
        provider="auto",
        model=None,
        api_key=None,
        organization=None
    ):
        """
        Initialise le service LLM compatible
        
        Args:
            openai_client: Client OpenAI existant (ignoré, maintenu pour compatibilité)
            provider: Fournisseur LLM à utiliser ('openai', 'anthropic', 'auto')
            model: Modèle à utiliser par défaut
            api_key: Clé API (si différente de la variable d'environnement)
            organization: ID d'organisation (pour OpenAI)
        """
        self.provider_name = provider.lower()
        
        # Configurer le modèle par défaut en fonction du provider
        self.default_model = model
        if not self.default_model:
            if self.provider_name == "openai" or self.provider_name == "auto":
                self.default_model = os.getenv("DEFAULT_OPENAI_MODEL", "gpt-3.5-turbo")
            elif self.provider_name == "anthropic":
                self.default_model = os.getenv("DEFAULT_ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
        
        # Créer l'adaptateur LLM approprié
        try:
            adapter_args = {}
            
            if api_key:
                adapter_args["api_key"] = api_key
                
            if model:
                adapter_args["model"] = model
                
            if organization and (self.provider_name == "openai" or self.provider_name == "auto"):
                adapter_args["organization"] = organization
                
            self.llm_adapter = LLMAdapterFactory.create_adapter(
                provider=self.provider_name,
                **adapter_args
            )
            
            logger.info(f"Service LLM compatible initialisé avec provider: {self.provider_name}")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du service LLM: {str(e)}")
            self.llm_adapter = None
    
    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
        tools=None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Génère une complétion de chat en utilisant l'adaptateur LLM.
        Cette méthode est compatible avec l'ancien système.
        
        Args:
            messages: Liste de messages au format OpenAI (rôle, contenu)
            temperature: Température (0-1)
            max_tokens: Nombre maximum de tokens à générer
            model: Modèle à utiliser (si différent du défaut)
            timeout: Timeout en secondes
            tools: Définitions d'outils à fournir au LLM
            **kwargs: Arguments additionnels
            
        Returns:
            Réponse similaire au format OpenAI
        """
        if not self.llm_adapter:
            logger.error("Adaptateur LLM non initialisé, impossible de générer une complétion")
            raise RuntimeError("Adaptateur LLM non initialisé")
        
        # Convertir les messages au format standardisé
        std_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            name = msg.get("name")
            function_call = msg.get("function_call")
            
            std_messages.append(LLMMessage(
                role=role,
                content=content,
                name=name,
                function_call=function_call
            ))
        
        # Configurer l'appel
        config = LLMConfig(
            model=model or self.default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            tools=tools
        )
        
        # Ajouter d'autres paramètres de configuration s'ils sont présents
        for key in ["top_p", "frequency_penalty", "presence_penalty", "stop", "tool_choice"]:
            if key in kwargs:
                setattr(config, key.replace("stop", "stop_sequences"), kwargs[key])
                
        # Effectuer l'appel à l'adaptateur
        try:
            response = await self.llm_adapter.complete(std_messages, config)
            
            # Convertir la réponse au format ancien système (similaire à OpenAI)
            output = {
                "id": f"chatcmpl-{response.model.replace('.', '').replace('-', '')}",
                "object": "chat.completion",
                "created": int(asyncio.get_event_loop().time()),
                "model": response.model,
                "usage": response.usage,
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": response.content
                    },
                    "finish_reason": response.finish_reason,
                    "index": 0
                }]
            }
            
            # Ajouter function_call si présent
            if response.function_call:
                output["choices"][0]["message"]["function_call"] = response.function_call
                
            # Ajouter tool_calls si présent
            if response.tool_calls:
                output["choices"][0]["message"]["tool_calls"] = response.tool_calls
            
            return output
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération de complétion: {str(e)}")
            raise
    
    async def embedding(
        self, 
        text: str, 
        model: Optional[str] = None
    ) -> List[float]:
        """
        Génère un embedding pour un texte donné.
        Compatible avec l'ancien système.
        
        Args:
            text: Texte à encoder
            model: Modèle d'embedding à utiliser
            
        Returns:
            Vecteur d'embedding
        """
        if not self.llm_adapter:
            logger.error("Adaptateur LLM non initialisé, impossible de générer un embedding")
            raise RuntimeError("Adaptateur LLM non initialisé")
        
        try:
            return await self.llm_adapter.embed(text, model)
        except Exception as e:
            logger.error(f"Erreur lors de la génération d'embedding: {str(e)}")
            
            # Si le provider ne supporte pas les embeddings (ex: Anthropic)
            if "non disponible" in str(e) or "non pris en charge" in str(e):
                logger.warning(
                    f"Le provider {self.provider_name} ne supporte pas les embeddings. "
                    "Basculement vers un adaptateur OpenAI pour cette opération."
                )
                
                # Créer un adaptateur OpenAI spécifiquement pour les embeddings
                try:
                    openai_adapter = LLMAdapterFactory.create_adapter("openai")
                    return await openai_adapter.embed(text, model)
                except Exception as e2:
                    logger.error(f"Échec du basculement vers OpenAI pour embedding: {str(e2)}")
                    raise e2
            else:
                raise
    
    async def get_completion(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Méthode de compatibilité pour la génération de complétion à partir d'un prompt simple.
        
        Args:
            prompt: Texte du prompt
            temperature: Température (0-1)
            max_tokens: Nombre maximum de tokens à générer
            model: Modèle à utiliser
            **kwargs: Arguments additionnels
            
        Returns:
            Texte généré
        """
        # Convertir le prompt en format de messages
        messages = [{"role": "user", "content": prompt}]
        
        # Appeler chat_completion
        response = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            **kwargs
        )
        
        # Extraire le contenu
        return response["choices"][0]["message"]["content"]
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie l'état de santé du service LLM
        
        Returns:
            Informations sur l'état de santé
        """
        if not self.llm_adapter:
            return {
                "status": "error",
                "message": "Adaptateur LLM non initialisé"
            }
        
        try:
            return await self.llm_adapter.health_check()
        except Exception as e:
            logger.error(f"Erreur lors du contrôle de santé LLM: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
