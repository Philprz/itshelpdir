"""
Module anthropic_adapter.py - Adaptateur LLM pour Anthropic Claude

Ce module implémente l'interface LLMAdapter pour les modèles Anthropic Claude,
en gérant les spécificités de l'API Claude et les mécanismes de retry.
"""

import logging
import asyncio
import time
import json
from typing import Dict, List, Any, Optional, Union
import os

# Import de l'interface abstraite
from .base import LLMAdapter, LLMMessage, LLMResponse, LLMConfig

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.llm.anthropic")

class AnthropicAdapter(LLMAdapter):
    """
    Adaptateur pour les modèles Anthropic Claude avec gestion des erreurs et métriques
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        default_model: str = "claude-3-sonnet-20240229",
        timeout_multiplier: float = 1.0,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialise l'adaptateur Anthropic Claude
        
        Args:
            api_key: Clé API Anthropic (par défaut: variable d'environnement ANTHROPIC_API_KEY)
            default_model: Modèle par défaut à utiliser
            timeout_multiplier: Multiplicateur pour les timeouts (pour les environnements lents)
            max_retries: Nombre maximum de tentatives en cas d'erreur
            retry_delay: Délai initial entre les tentatives (avec backoff exponentiel)
        """
        # Récupérer la clé API depuis les variables d'environnement si non spécifiée
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        
        if not self.api_key:
            logger.warning("Aucune clé API Anthropic fournie")
        
        # Configuration
        self.default_model = default_model
        self.timeout_multiplier = timeout_multiplier
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Client Anthropic (initialisé lors de la première utilisation)
        self._client = None
        
        # Métriques
        self._call_count = 0
        self._error_count = 0
        self._total_tokens = 0
        self._retry_count = 0
        
        logger.info(f"Adaptateur Anthropic initialisé avec le modèle par défaut: {default_model}")
    
    def _get_client(self):
        """
        Récupère ou initialise le client Anthropic
        
        Returns:
            Client Anthropic initialisé
        """
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                
                self._client = AsyncAnthropic(
                    api_key=self.api_key
                )
                
                logger.debug("Client Anthropic initialisé avec succès")
            except ImportError:
                logger.error("Module Anthropic non disponible. Installez-le avec: pip install anthropic")
                raise
        
        return self._client
    
    @property
    def provider_name(self) -> str:
        """
        Nom du fournisseur de LLM
        
        Returns:
            'anthropic'
        """
        return "anthropic"
    
    @property
    def available_models(self) -> List[str]:
        """
        Liste des modèles disponibles
        
        Returns:
            Liste des identifiants de modèles Anthropic Claude
        """
        # Liste statique des modèles disponibles
        return [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2"
        ]
    
    async def _convert_to_anthropic_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """
        Convertit les messages au format Anthropic
        
        Args:
            messages: Liste de messages LLM standardisés
            
        Returns:
            Liste de messages au format Anthropic
        """
        anthropic_messages = []
        
        # Extraire le message système s'il existe
        system_message = None
        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                break
                
        # Convertir les autres messages
        for msg in messages:
            if msg.role == "system":
                continue  # Le message système est géré séparément
                
            elif msg.role == "user":
                anthropic_message = {"role": "user", "content": msg.content}
                anthropic_messages.append(anthropic_message)
                
            elif msg.role == "assistant":
                # Gérer les appels de fonction spécifiques à Claude
                content = msg.content
                anthropic_message = {"role": "assistant", "content": content}
                anthropic_messages.append(anthropic_message)
                
            elif msg.role == "function":
                # Claude n'a pas de format natif pour les réponses de fonction
                # On les convertit en messages utilisateur avec un préfixe
                converted_content = f"[Résultat fonction {msg.name}]\n{msg.content}"
                anthropic_message = {"role": "user", "content": converted_content}
                anthropic_messages.append(anthropic_message)
        
        return anthropic_messages, system_message
    
    async def complete(
        self, 
        messages: List[LLMMessage], 
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        Génère une complétion basée sur un historique de messages avec Claude
        
        Args:
            messages: Liste de messages représentant la conversation
            config: Configuration pour l'appel
            
        Returns:
            Réponse générée
        """
        # Utiliser la configuration par défaut si non spécifiée
        if config is None:
            config = LLMConfig(model=self.default_model)
            
        # Convertir les messages au format Anthropic
        anthropic_messages, system_message = await self._convert_to_anthropic_messages(messages)
        
        # Préparer les paramètres pour l'appel API
        params = {
            "model": config.model,
            "messages": anthropic_messages,
            "temperature": config.temperature,
            "top_p": config.top_p
        }
        
        # Ajouter les paramètres optionnels s'ils sont spécifiés
        if system_message:
            params["system"] = system_message
            
        if config.max_tokens:
            params["max_tokens"] = config.max_tokens
            
        if config.stop_sequences:
            params["stop_sequences"] = config.stop_sequences
            
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
                    response = await client.messages.create(**params)
                    elapsed_time = time.time() - start_time
                
                # Analyser la réponse
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                }
                
                # Mettre à jour les métriques
                self._total_tokens += usage["total_tokens"]
                
                # Extraire le contenu de la réponse
                content = response.content[0].text
                
                # Claude ne supporte pas nativement les function calls
                # Il faut les extraire du contenu via un parsing
                function_call = None
                tool_calls = None
                
                # Tenter de détecter et extraire les appels de fonction du texte
                # Format supposé : <tool>...</tool> ou JSON balisé
                if "<function>" in content and "</function>" in content:
                    try:
                        start_idx = content.find("<function>") + len("<function>")
                        end_idx = content.find("</function>", start_idx)
                        
                        if start_idx > 0 and end_idx > start_idx:
                            function_text = content[start_idx:end_idx].strip()
                            function_data = json.loads(function_text)
                            
                            function_call = {
                                "name": function_data.get("name", ""),
                                "arguments": function_data.get("arguments", "{}")
                            }
                            
                            # Nettoyer le contenu en retirant l'appel de fonction
                            content = content[:start_idx - len("<function>")] + content[end_idx + len("</function>"):]
                            content = content.strip()
                    except Exception as e:
                        logger.warning(f"Erreur lors de l'analyse de l'appel de fonction Claude: {e}")
                
                # Créer la réponse standardisée
                result = LLMResponse(
                    content=content,
                    model=response.model,
                    usage=usage,
                    finish_reason=response.stop_reason,
                    function_call=function_call,
                    tool_calls=tool_calls,
                    raw_response=response
                )
                
                # Journaliser le succès
                logger.debug(
                    f"Complétion Claude réussie: {usage['total_tokens']} tokens, "
                    f"{elapsed_time:.2f}s, modèle: {response.model}"
                )
                
                return result
                
            except asyncio.TimeoutError:
                retry_count += 1
                self._retry_count += 1
                delay = self.retry_delay * (2 ** retry_count)  # Backoff exponentiel
                
                logger.warning(
                    f"Timeout lors de l'appel Claude (tentative {retry_count}/{self.max_retries}). "
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
                        f"Erreur de rate limit Claude (tentative {retry_count}/{self.max_retries}). "
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
                        f"Erreur serveur Claude (tentative {retry_count}/{self.max_retries}). "
                        f"Nouvelle tentative dans {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    # Erreurs non récupérables
                    logger.error(f"Erreur Claude non récupérable: {str(e)}")
                    
                # Si l'erreur n'est pas récupérable ou nombre max de tentatives atteint
                if not is_recoverable or retry_count > self.max_retries:
                    raise
                    
                last_error = str(e)
        
        # Si toutes les tentatives ont échoué
        if last_error:
            logger.error(f"Échec de l'appel Claude après {self.max_retries} tentatives: {last_error}")
            raise Exception(f"Échec de l'appel Claude: {last_error}")
        
        # Ne devrait jamais atteindre ce point
        return None
    
    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Claude n'offre pas nativement de service d'embedding.
        Cette méthode génère un message d'erreur clair.
        
        Args:
            text: Texte à encoder
            model: Modèle d'embedding à utiliser
            
        Returns:
            Exception - non supporté
        """
        logger.error("Les embeddings ne sont pas pris en charge par l'API Claude d'Anthropic")
        raise NotImplementedError(
            "Les embeddings ne sont pas disponibles avec l'API Claude. "
            "Utilisez un autre provider comme OpenAI pour cette fonctionnalité."
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité et l'état de santé du provider Anthropic
        
        Returns:
            Dictionnaire avec statut et informations
        """
        try:
            # Test simple avec une complétion courte
            single_message = [LLMMessage(role="user", content="Bonjour, test de santé.")]
            
            # Configuration minimale
            test_config = LLMConfig(
                model=self.default_model,
                temperature=0.0,
                max_tokens=10
            )
            
            start_time = time.time()
            response = await self.complete(single_message, test_config)
            elapsed_time = time.time() - start_time
            
            # Vérifier si la réponse a été générée correctement
            is_healthy = response is not None and len(response.content) > 0
            
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
            logger.error(f"Échec du contrôle de santé Claude: {str(e)}")
            
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
