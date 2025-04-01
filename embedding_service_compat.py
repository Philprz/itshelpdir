"""
Module de compatibilité pour embedding_service.

Ce module sert d'interface de compatibilité entre les implémentations
existantes d'embedding_service et l'application principale.
"""

import logging
import hashlib
import json
from typing import List, Dict, Any
import asyncio

# Configuration du logging
logger = logging.getLogger('ITS_HELP.embedding')

class JSONSerializableEncoder(json.JSONEncoder):
    """Encodeur personnalisé pour gérer les objets non sérialisables en JSON."""
    def default(self, obj):
        try:
            if hasattr(obj, 'to_json'):
                return obj.to_json()
            if hasattr(obj, '__getstate__'):
                return obj.__getstate__()
            return super().default(obj)
        except TypeError:
            return str(obj)

class SafeCacheProxy:
    """
    Proxy de sécurité pour le cache qui évite les problèmes de sérialisation.
    Ce proxy intercepte toutes les interactions avec le cache et s'assure qu'aucun
    objet non-sérialisable n'est transmis.
    """
    
    def __init__(self, cache):
        """
        Initialise le proxy avec l'objet cache sous-jacent.
        
        Args:
            cache: Objet cache à proxifier
        """
        self._cache = cache
        self._logger = logging.getLogger('ITS_HELP.embedding.cache_proxy')
        
    async def get(self, key: str) -> Any:
        """
        Récupère une valeur du cache de manière sécurisée.
        
        Args:
            key: Clé à rechercher
        
        Returns:
            Valeur associée à la clé ou None si non trouvée
        """
        try:
            # Tenter d'utiliser la méthode get() asynchrone
            if hasattr(self._cache, 'get') and callable(self._cache.get):
                try:
                    result = await self._cache.get(key, namespace="embeddings")
                    # Vérifier que la valeur est sérialisable
                    try:
                        json.dumps(result)
                    except Exception as ex:
                        self._logger.warning(f"Valeur non sérialisable récupérée du cache: {ex.__class__.__name__}")
                        return None
                    return result
                except Exception as e:
                    self._logger.debug(f"Erreur lors de l'accès au cache async: {e.__class__.__name__}")
        
            # Tenter d'utiliser get_embedding() si disponible
            if hasattr(self._cache, 'get_embedding') and callable(self._cache.get_embedding):
                try:
                    # Cette méthode est asynchrone dans GlobalCache
                    if asyncio.iscoroutinefunction(self._cache.get_embedding):
                        result = await self._cache.get_embedding(key)
                    else:
                        # Appel synchrone en fallback
                        result = self._cache.get_embedding(key)
                    
                    # Vérifier que le résultat est valide et sérialisable
                    if result is not None:
                        try:
                            json.dumps(result)
                            return result
                        except Exception:
                            self._logger.warning("Résultat d'embedding non sérialisable du cache")
                except Exception as e:
                    self._logger.debug(f"Erreur lors de l'accès à get_embedding: {e.__class__.__name__}")
            
            return None
        except Exception as e:
            self._logger.warning(f"Erreur proxifiée lors de la récupération depuis le cache: {e.__class__.__name__}")
            return None
        
    async def set(self, key: str, value: Any) -> None:
        """
        Stocke une valeur dans le cache de manière sécurisée.
        
        Args:
            key: Clé sous laquelle stocker la valeur
            value: Valeur à stocker
        """
        try:
            # Vérifier que la valeur est sérialisable
            # Ce test garantit que nous n'essayons pas de stocker des objets non-sérialisables
            json.dumps(value)
            
            # Tenter d'utiliser la méthode set() asynchrone
            if hasattr(self._cache, 'set') and callable(self._cache.set):
                try:
                    await self._cache.set(key, value, namespace="embeddings")
                    return
                except Exception as e:
                    self._logger.debug(f"Erreur lors de l'écriture dans le cache async: {e.__class__.__name__}")
        
            # Tenter d'utiliser set_embedding() si disponible
            # Note: cette méthode ne peut pas être utilisée correctement car nous avons perdu
            # le texte original en utilisant un hash comme clé
            return
        except (TypeError, OverflowError) as e:
            # La valeur n'est pas sérialisable, on ignore
            self._logger.warning(f"Tentative d'écrire une valeur non-sérialisable dans le cache: {e.__class__.__name__}")
            
    def to_json(self):
        """Méthode sécurisée pour convertir l'objet en structure JSON-compatible."""
        return {"type": "SafeCacheProxy"}
        
    def __getstate__(self):
        """Définit l'état de l'objet pour la sérialisation."""
        return self.to_json()
        
    def __repr__(self):
        """Représentation string pour le logging et le débogage."""
        return "SafeCacheProxy()"
            
# Import du service original s'il existe
try:
    from search.utils.embedding_service import EmbeddingService as OriginalEmbeddingService
    logger.info("Utilisation du service d'embedding depuis search.utils")
    EmbeddingService = OriginalEmbeddingService
except ImportError:
    # Implémentation de secours si le module original n'est pas disponible
    logger.warning("Module original d'embedding non trouvé, utilisation du service de compatibilité")
    
    class EmbeddingService:
        """
        Service pour la génération d'embeddings utilisant diverses APIs.
        Version de compatibilité simplifiée.
        """
        
        def __init__(self, openai_client=None, cache=None, model="text-embedding-ada-002"):
            """
            Initialise le service d'embedding.
            
            Args:
                openai_client: Client OpenAI à utiliser
                cache: Cache pour stocker les embeddings
                model: Modèle d'embedding à utiliser
            """
            self.openai_client = openai_client
            self.model = model
            
            # Solution sécurisée pour le problème de sérialisation JSON
            # Utilisation d'un proxy pour le cache au lieu de stocker l'objet directement
            self._cache_proxy = None
            if cache is not None:
                self._cache_proxy = SafeCacheProxy(cache)
                
            self._local_cache = {}  # Cache local simple comme plan B
            self.logger = logger
            
            # Nombre d'appels effectués
            self.call_count = 0
            self.error_count = 0
            
            # Journaliser l'initialisation de manière sécurisée
            if cache:
                logger.info(f"EmbeddingService initialisé avec cache de type {type(cache).__name__}")
            else:
                logger.info("EmbeddingService initialisé sans cache")
            
        async def get_embedding(self, text: str) -> List[float]:
            """
            Génère l'embedding d'un texte.
            
            Args:
                text: Texte pour lequel générer l'embedding
                
            Returns:
                Vecteur d'embedding
            """
            if not text:
                self.logger.warning("Tentative de génération d'embedding pour un texte vide")
                return [0.0] * 1536  # Embedding par défaut pour un texte vide
                
            try:
                # Normaliser le texte et utiliser le cache
                text = self._normalize_text(text)
                cache_key = self._generate_cache_key(text)
                
                # Cache local (sécurisé)
                if cache_key in self._local_cache:
                    return self._local_cache[cache_key]
                    
                # Cache externe via proxy
                if self._cache_proxy:
                    try:
                        cached_embedding = await self._cache_proxy.get(cache_key)
                        if cached_embedding:
                            return cached_embedding
                    except Exception as e:
                        self.logger.warning(f"Erreur lors de l'accès au cache: {e.__class__.__name__}")
                
                # Génération via OpenAI avec gestion d'erreurs renforcée
                if self.openai_client:
                    embedding = await self._get_openai_embedding(text)
                    self._local_cache[cache_key] = embedding
                    
                    # Stocker dans le cache externe via le proxy sécurisé
                    if self._cache_proxy:
                        try:
                            await self._cache_proxy.set(cache_key, embedding)
                        except Exception as e:
                            self.logger.warning(f"Erreur lors de l'écriture dans le cache: {e.__class__.__name__}")
                    
                    return embedding
                else:
                    self.logger.error("Aucun client configuré pour la génération d'embeddings")
                    return [0.0] * 1536  # Embedding par défaut
            except Exception as e:
                self.error_count += 1
                self.logger.error(f"Erreur lors de la génération d'embedding: {str(e)}")
                return [0.0] * 1536  # Embedding par défaut en cas d'erreur
                
        def _normalize_text(self, text: str) -> str:
            """Normalise un texte pour la génération d'embedding."""
            # Tronquer si trop long (OpenAI a des limites de tokens)
            max_chars = 8000
            if len(text) > max_chars:
                text = text[:max_chars]
                
            # Supprimer les caractères spéciaux problématiques
            text = text.replace('\x00', ' ')
            
            # Normaliser les espaces
            text = ' '.join(text.split())
            
            return text
            
        def _generate_cache_key(self, text: str) -> str:
            """
            Génère une clé unique pour le cache basée sur le texte.
            Évite de passer l'objet texte complet pour la sérialisation.
            
            Args:
                text: Texte pour lequel générer une clé
                
            Returns:
                Clé unique pour le cache
            """
            # Créer un hash du texte normalisé pour l'utiliser comme clé
            if isinstance(text, str):
                hash_obj = hashlib.md5(text.encode('utf-8'))
            else:
                hash_obj = hashlib.md5(str(text).encode('utf-8'))
            return f"embedding:{hash_obj.hexdigest()}"
            
        async def _get_openai_embedding(self, text: str) -> List[float]:
            """Génère un embedding avec OpenAI."""
            self.call_count += 1
            
            try:
                # Vérifier si c'est l'ancienne ou nouvelle API OpenAI
                if hasattr(self.openai_client, 'embeddings'):
                    # Nouvelle API
                    result = await self.openai_client.embeddings.create(
                        model=self.model,
                        input=text
                    )
                    embedding = result.data[0].embedding
                else:
                    # Ancienne API
                    result = await self.openai_client.embedding(
                        input=text,
                        model=self.model
                    )
                    embedding = result["data"][0]["embedding"]
                                        
                return embedding
                
            except Exception as e:
                self.logger.error(f"Erreur API OpenAI: {str(e)}")
                return [0.0] * 1536  # Embedding par défaut en cas d'erreur
                
        def get_stats(self) -> Dict[str, Any]:
            """Retourne des statistiques sur l'utilisation du service."""
            return {
                "calls": self.call_count,
                "errors": self.error_count,
                "error_rate": f"{(self.error_count / self.call_count * 100) if self.call_count > 0 else 0:.2f}%",
                "model": self.model,
                "cache_enabled": self._cache_proxy is not None,
                "local_cache_size": len(self._local_cache)
            }
            
        def to_json(self):
            """Méthode sécurisée pour convertir l'objet en structure JSON-compatible."""
            try:
                return {
                    "model": str(self.model),
                    "calls": self.call_count,
                    "errors": self.error_count,
                    "cache_enabled": self._cache_proxy is not None,
                    "local_cache_size": len(self._local_cache) if hasattr(self, '_local_cache') else 0
                }
            except Exception as e:
                # Fallback en cas d'erreur
                return {
                    "model": str(self.model) if hasattr(self, "model") else "unknown",
                    "error": f"Erreur de sérialisation: {e.__class__.__name__}"
                }
            
        def __getstate__(self):
            """Définit l'état de l'objet pour la sérialisation."""
            # Retourner un dictionnaire contenant uniquement des attributs sérialisables
            state = {}
            try:
                # Attributs sûrs
                state["model"] = str(self.model) if hasattr(self, "model") else "unknown"
                state["call_count"] = self.call_count if hasattr(self, "call_count") else 0
                state["error_count"] = self.error_count if hasattr(self, "error_count") else 0
                
                # Information sur la présence d'attributs (mais pas les objets eux-mêmes)
                state["has_cache_proxy"] = hasattr(self, "_cache_proxy") and self._cache_proxy is not None
                state["has_openai_client"] = hasattr(self, "openai_client") and self.openai_client is not None
                state["has_logger"] = hasattr(self, "logger") and self.logger is not None
                
                # Taille du cache local sans inclure les objets
                if hasattr(self, "_local_cache"):
                    state["local_cache_size"] = len(self._local_cache)
            except Exception as e:
                # En cas d'erreur, retourner un état minimal
                state = {"serialization_error": True, "error_type": str(e.__class__.__name__)}
            
            return state
        
        def __deepcopy__(self, memo):
            """Support pour la copie profonde sans copier les objets non-copiables."""
            # Créer une nouvelle instance sans initialiser complètement
            result = self.__class__.__new__(self.__class__)
            memo[id(self)] = result
            
            # Copier les attributs simples
            for k, v in self.__getstate__().items():
                setattr(result, k, v)
                
            return result
            
        def __repr__(self):
            """Représentation string de la classe pour le logging et le débogage."""
            return f"EmbeddingService(model={self.model}, call_count={self.call_count})"
