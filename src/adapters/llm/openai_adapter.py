"""
Module openai_adapter.py - Adaptateur LLM pour OpenAI

Ce module implémente l'interface LLMAdapter pour les modèles OpenAI,
en gérant les spécificités de l'API OpenAI et les mécanismes de retry.
"""

import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Union
import os

# Import de l'interface abstraite
from .base import LLMAdapter, LLMMessage, LLMResponse, LLMConfig

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.llm.openai")

class OpenAIAdapter(LLMAdapter):
    """
    Adaptateur pour les modèles OpenAI avec gestion des erreurs et métriques
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        organization: Optional[str] = None,
        default_model: str = "gpt-3.5-turbo",
        timeout_multiplier: float = 1.0,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialise l'adaptateur OpenAI
        
        Args:
            api_key: Clé API OpenAI (par défaut: variable d'environnement OPENAI_API_KEY)
            organization: ID d'organisation OpenAI (optionnel)
            default_model: Modèle par défaut à utiliser
            timeout_multiplier: Multiplicateur pour les timeouts (pour les environnements lents)
            max_retries: Nombre maximum de tentatives en cas d'erreur
            retry_delay: Délai initial entre les tentatives (avec backoff exponentiel)
        """
        # Récupérer la clé API depuis les variables d'environnement si non spécifiée
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.organization = organization or os.getenv("OPENAI_ORGANIZATION_ID")
        
        if not self.api_key:
            logger.warning("Aucune clé API OpenAI fournie")
        
        # Configuration
        self.default_model = default_model
        self.timeout_multiplier = timeout_multiplier
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Client OpenAI (initialisé lors de la première utilisation)
        self._client = None
        
        # Métriques
        self._call_count = 0
        self._error_count = 0
        self._total_tokens = 0
        self._retry_count = 0
        
        # Cache des modèles disponibles
        self._available_models_cache = None
        self._models_cache_time = 0
        self._MODELS_CACHE_TTL = 3600  # 1 heure
        
        logger.info(f"Adaptateur OpenAI initialisé avec le modèle par défaut: {default_model}")
    
    def _get_client(self):
        """
        Récupère ou initialise le client OpenAI
        
        Returns:
            Client OpenAI initialisé
        """
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                
                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    organization=self.organization
                )
                
                logger.debug("Client OpenAI initialisé avec succès")
            except ImportError:
                logger.error("Module OpenAI non disponible. Installez-le avec: pip install openai")
                raise
        
        return self._client
    
    @property
    def provider_name(self) -> str:
        """
        Nom du fournisseur de LLM
        
        Returns:
            'openai'
        """
        return "openai"
    
    @property
    def available_models(self) -> List[str]:
        """
        Liste des modèles disponibles
        
        Returns:
            Liste des identifiants de modèles OpenAI
        """
        # Liste statique des modèles courants pour éviter des appels API inutiles
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4-1106-preview",
            "gpt-4-vision-preview", 
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large"
        ]
    
    async def _fetch_available_models(self) -> List[str]:
        """
        Récupère la liste des modèles disponibles depuis l'API OpenAI
        
        Returns:
            Liste des identifiants de modèles disponibles
        """
        current_time = time.time()
        
        # Utiliser le cache si disponible et non expiré
        if (self._available_models_cache is not None and 
            current_time - self._models_cache_time < self._MODELS_CACHE_TTL):
            return self._available_models_cache
        
        # Sinon, récupérer depuis l'API
        try:
            client = self._get_client()
            models = await client.models.list()
            
            # Extraire les IDs
            model_ids = [model.id for model in models.data]
            
            # Mettre en cache
            self._available_models_cache = model_ids
            self._models_cache_time = current_time
            
            return model_ids
        except Exception as e:
            logger.warning(f"Impossible de récupérer les modèles disponibles: {str(e)}")
            # En cas d'erreur, utiliser la liste statique
            return self.available_models
    
    async def complete(
        self, 
        messages: List[LLMMessage], 
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        Génère une complétion basée sur un historique de messages avec OpenAI
        
        Args:
            messages: Liste de messages représentant la conversation
            config: Configuration pour l'appel
            
        Returns:
            Réponse générée
        """
        # Utiliser la configuration par défaut si non spécifiée
        if config is None:
            config = LLMConfig(model=self.default_model)
        
        # Convertir les messages au format OpenAI
        openai_messages = []
        for msg in messages:
            openai_msg = {
                "role": msg.role,
                "content": msg.content
            }
            
            # Ajouter le nom si présent (pour les messages de fonction)
            if msg.name:
                openai_msg["name"] = msg.name
                
            # Ajouter l'appel de fonction si présent
            if msg.function_call:
                openai_msg["function_call"] = msg.function_call
                
            openai_messages.append(openai_msg)
            
        # Préparer les paramètres pour l'appel API
        params = {
            "model": config.model,
            "messages": openai_messages,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "frequency_penalty": config.frequency_penalty,
            "presence_penalty": config.presence_penalty
        }
        
        # Ajouter les paramètres optionnels s'ils sont spécifiés
        if config.max_tokens:
            params["max_tokens"] = config.max_tokens
            
        if config.stop_sequences:
            params["stop"] = config.stop_sequences
            
        if config.tools:
            params["tools"] = config.tools
            
        if config.tool_choice:
            params["tool_choice"] = config.tool_choice
            
        if config.response_format:
            params["response_format"] = config.response_format
            
        if config.seed:
            params["seed"] = config.seed
        
        # Tentatives avec backoff exponentiel
        retry_count = 0
        last_error = None
        
        while retry_count <= self.max_retries:
            try:
                # Incrémenter le compteur d'appels
                self._call_count += 1
                
                # Calculer le timeout effectif
                effective_timeout = config.timeout * self.timeout_multiplier
                
                # Effectuer l'appel API avec timeout
                client = self._get_client()
                
                # Utiliser un contexte asyncio.timeout pour le timeout
                async with asyncio.timeout(effective_timeout):
                    start_time = time.time()
                    response = await client.chat.completions.create(**params)
                    elapsed_time = time.time() - start_time
                
                # Analyser la réponse
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
                
                # Mettre à jour les métriques
                self._total_tokens += response.usage.total_tokens
                
                # Extraire le contenu de la réponse
                response_message = response.choices[0].message
                content = response_message.content or ""
                
                # Extraire l'appel de fonction ou d'outil si présent
                function_call = None
                tool_calls = None
                
                if hasattr(response_message, 'function_call') and response_message.function_call:
                    function_call = {
                        "name": response_message.function_call.name,
                        "arguments": response_message.function_call.arguments
                    }
                
                if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
                    tool_calls = []
                    for tool_call in response_message.tool_calls:
                        tool_calls.append({
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        })
                
                # Créer la réponse standardisée
                result = LLMResponse(
                    content=content,
                    model=response.model,
                    usage=usage,
                    finish_reason=response.choices[0].finish_reason,
                    function_call=function_call,
                    tool_calls=tool_calls,
                    raw_response=response
                )
                
                # Journaliser le succès
                logger.debug(
                    f"Complétion OpenAI réussie: {usage['total_tokens']} tokens, "
                    f"{elapsed_time:.2f}s, modèle: {response.model}"
                )
                
                return result
                
            except asyncio.TimeoutError:
                retry_count += 1
                self._retry_count += 1
                delay = self.retry_delay * (2 ** retry_count)  # Backoff exponentiel
                
                logger.warning(
                    f"Timeout lors de l'appel OpenAI (tentative {retry_count}/{self.max_retries}). "
                    f"Nouvelle tentative dans {delay:.2f}s..."
                )
                
                last_error = "Timeout"
                await asyncio.sleep(delay)
                
            except Exception as e:
                self._error_count += 1
                retry_count += 1
                
                # Déterminer si l'erreur est récupérable
                is_recoverable = False
                
                # Analyser le type d'erreur
                error_str = str(e)
                
                # Erreurs liées au taux de requêtes (récupérables)
                if any(x in error_str.lower() for x in [
                    "rate limit", "rate_limit", "too many requests", "timeout"
                ]):
                    is_recoverable = True
                    delay = self.retry_delay * (2 ** retry_count)  # Backoff exponentiel
                    logger.warning(
                        f"Erreur de rate limit OpenAI (tentative {retry_count}/{self.max_retries}). "
                        f"Nouvelle tentative dans {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                # Erreurs de service (récupérables)
                elif any(x in error_str.lower() for x in [
                    "server error", "internal error", "500", "502", "503", "504"
                ]):
                    is_recoverable = True
                    delay = self.retry_delay * (2 ** retry_count)  # Backoff exponentiel
                    logger.warning(
                        f"Erreur serveur OpenAI (tentative {retry_count}/{self.max_retries}). "
                        f"Nouvelle tentative dans {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    # Erreurs non récupérables
                    logger.error(f"Erreur OpenAI non récupérable: {str(e)}")
                    
                # Si l'erreur n'est pas récupérable ou nombre max de tentatives atteint
                if not is_recoverable or retry_count > self.max_retries:
                    raise
                    
                last_error = str(e)
        
        # Si toutes les tentatives ont échoué
        if last_error:
            logger.error(f"Échec de l'appel OpenAI après {self.max_retries} tentatives: {last_error}")
            raise Exception(f"Échec de l'appel OpenAI: {last_error}")
        
        # Ne devrait jamais atteindre ce point
        return None
    
    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Génère un embedding pour un texte donné en utilisant l'API OpenAI
        
        Args:
            text: Texte à encoder
            model: Modèle d'embedding à utiliser (défaut: text-embedding-ada-002)
            
        Returns:
            Vecteur d'embedding
        """
        # Utiliser le modèle par défaut si non spécifié
        embedding_model = model or "text-embedding-ada-002"
        
        # Tentatives avec backoff exponentiel
        retry_count = 0
        last_error = None
        
        while retry_count <= self.max_retries:
            try:
                # Incrémenter le compteur d'appels
                self._call_count += 1
                
                # Normaliser le texte
                if text:
                    # Tronquer si trop long (limite API OpenAI)
                    max_chars = 8000
                    if len(text) > max_chars:
                        text = text[:max_chars]
                    
                    # Supprimer les caractères problématiques
                    text = text.replace('\x00', ' ')
                    
                    # Normaliser les espaces
                    text = ' '.join(text.split())
                else:
                    text = " "  # Texte vide -> espace unique
                
                # Effectuer l'appel API
                client = self._get_client()
                
                start_time = time.time()
                response = await client.embeddings.create(
                    model=embedding_model,
                    input=text
                )
                elapsed_time = time.time() - start_time
                
                # Extraire l'embedding
                embedding = response.data[0].embedding
                
                # Journaliser le succès
                logger.debug(
                    f"Embedding OpenAI réussi: {len(text)} caractères, "
                    f"{elapsed_time:.2f}s, modèle: {embedding_model}"
                )
                
                return embedding
                
            except Exception as e:
                self._error_count += 1
                retry_count += 1
                
                # Déterminer si l'erreur est récupérable
                is_recoverable = False
                
                # Analyser le type d'erreur
                error_str = str(e)
                
                # Erreurs liées au taux de requêtes (récupérables)
                if any(x in error_str.lower() for x in [
                    "rate limit", "rate_limit", "too many requests", "timeout"
                ]):
                    is_recoverable = True
                    delay = self.retry_delay * (2 ** retry_count)  # Backoff exponentiel
                    logger.warning(
                        f"Erreur de rate limit OpenAI (tentative {retry_count}/{self.max_retries}). "
                        f"Nouvelle tentative dans {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                # Erreurs de service (récupérables)
                elif any(x in error_str.lower() for x in [
                    "server error", "internal error", "500", "502", "503", "504"
                ]):
                    is_recoverable = True
                    delay = self.retry_delay * (2 ** retry_count)  # Backoff exponentiel
                    logger.warning(
                        f"Erreur serveur OpenAI (tentative {retry_count}/{self.max_retries}). "
                        f"Nouvelle tentative dans {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    # Erreurs non récupérables
                    logger.error(f"Erreur OpenAI non récupérable: {str(e)}")
                    
                # Si l'erreur n'est pas récupérable ou nombre max de tentatives atteint
                if not is_recoverable or retry_count > self.max_retries:
                    raise
                    
                last_error = str(e)
        
        # Si toutes les tentatives ont échoué
        if last_error:
            logger.error(f"Échec de l'embedding OpenAI après {self.max_retries} tentatives: {last_error}")
            raise Exception(f"Échec de l'embedding OpenAI: {last_error}")
        
        # Ne devrait jamais atteindre ce point
        return None
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité et l'état de santé du provider OpenAI
        
        Returns:
            Dictionnaire avec statut et informations
        """
        try:
            # Test simple avec un embedding (plus léger qu'une complétion)
            start_time = time.time()
            embedding = await self.embed("Test de santé OpenAI")
            elapsed_time = time.time() - start_time
            
            # Vérifier si l'embedding a été généré correctement
            is_healthy = embedding is not None and len(embedding) > 0
            
            return {
                "provider": self.provider_name,
                "status": "healthy" if is_healthy else "degraded",
                "latency_ms": int(elapsed_time * 1000),
                "api_key_configured": bool(self.api_key),
                "metrics": {
                    "calls": self._call_count,
                    "errors": self._error_count,
                    "error_rate": f"{(self._error_count / self._call_count * 100) if self._call_count > 0 else 0:.2f}%",
                    "retries": self._retry_count,
                    "total_tokens": self._total_tokens
                }
            }
        except Exception as e:
            logger.error(f"Échec du contrôle de santé OpenAI: {str(e)}")
            
            return {
                "provider": self.provider_name,
                "status": "unhealthy",
                "error": str(e),
                "api_key_configured": bool(self.api_key),
                "metrics": {
                    "calls": self._call_count,
                    "errors": self._error_count,
                    "error_rate": f"{(self._error_count / self._call_count * 100) if self._call_count > 0 else 0:.2f}%",
                    "retries": self._retry_count,
                    "total_tokens": self._total_tokens
                }
            }
