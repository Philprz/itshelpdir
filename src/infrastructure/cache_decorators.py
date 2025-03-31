"""
Module cache_decorators - Décorateurs pour une gestion robuste du cache

Ce module fournit des décorateurs qui protègent les méthodes utilisant le cache
contre les erreurs courantes, notamment les problèmes de sérialisation JSON.
"""

import logging
import functools
import asyncio
from typing import Any, Callable, TypeVar, cast

# Configuration du logging
logger = logging.getLogger("ITS_HELP.infrastructure.cache_decorators")

# Type générique pour les fonctions
F = TypeVar('F', bound=Callable[..., Any])

def safe_cache_operation(fallback_value: Any = None) -> Callable[[F], F]:
    """
    Décorateur pour protéger les opérations de cache contre les erreurs.
    Capture les erreurs de sérialisation JSON et autres erreurs liées au cache,
    en fournissant une valeur de repli en cas d'échec.
    
    Args:
        fallback_value: Valeur à retourner en cas d'erreur (None par défaut)
        
    Returns:
        Décorateur qui protège la fonction décorée
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper_sync(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except TypeError as e:
                if "is not JSON serializable" in str(e):
                    logger.warning(f"Erreur de sérialisation JSON dans {func.__name__}: {str(e)}")
                else:
                    logger.error(f"Erreur de type dans {func.__name__}: {str(e)}")
                return fallback_value
            except Exception as e:
                logger.error(f"Erreur dans {func.__name__}: {str(e)}")
                return fallback_value
                
        @functools.wraps(func)
        async def wrapper_async(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except TypeError as e:
                if "is not JSON serializable" in str(e):
                    logger.warning(f"Erreur de sérialisation JSON dans {func.__name__}: {str(e)}")
                else:
                    logger.error(f"Erreur de type dans {func.__name__}: {str(e)}")
                return fallback_value
            except Exception as e:
                logger.error(f"Erreur dans {func.__name__}: {str(e)}")
                return fallback_value
        
        # Déterminer si la fonction est asynchrone ou synchrone
        if asyncio.iscoroutinefunction(func):
            return cast(F, wrapper_async)
        else:
            return cast(F, wrapper_sync)
            
    return decorator

def log_cache_operation(log_level: str = "debug") -> Callable[[F], F]:
    """
    Décorateur pour journaliser les opérations de cache de manière sécurisée.
    Évite de journaliser des objets non-sérialisables en utilisant str() et
    des versions simplifiées des arguments.
    
    Args:
        log_level: Niveau de journalisation à utiliser ("debug", "info", "warning", "error")
        
    Returns:
        Décorateur qui journalise les opérations de cache
    """
    def get_logger_method(level: str):
        if level.lower() == "debug":
            return logger.debug
        elif level.lower() == "info":
            return logger.info
        elif level.lower() == "warning":
            return logger.warning
        elif level.lower() == "error":
            return logger.error
        else:
            return logger.debug
    
    log_method = get_logger_method(log_level)
    
    def safe_repr(obj: Any) -> str:
        """Retourne une représentation sécurisée d'un objet pour le logging."""
        try:
            # Si l'objet a une méthode to_dict(), l'utiliser
            if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
                return str(obj.to_dict())
            # Sinon utiliser __str__ ou __repr__
            return str(obj)
        except Exception:
            return "<Non-representable object>"
    
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper_sync(*args: Any, **kwargs: Any) -> Any:
            # Enregistrer l'appel sans les arguments complexes
            arg_repr = [safe_repr(arg) for arg in args[1:]]  # Exclure self
            kwarg_repr = {k: safe_repr(v) for k, v in kwargs.items()}
            
            log_method(f"Appel {func.__name__}({', '.join(arg_repr)}, {kwarg_repr})")
            
            try:
                result = func(*args, **kwargs)
                log_method(f"{func.__name__} terminé avec succès")
                return result
            except Exception as e:
                logger.error(f"Erreur dans {func.__name__}: {str(e)}")
                raise
                
        @functools.wraps(func)
        async def wrapper_async(*args: Any, **kwargs: Any) -> Any:
            # Enregistrer l'appel sans les arguments complexes
            arg_repr = [safe_repr(arg) for arg in args[1:]]  # Exclure self
            kwarg_repr = {k: safe_repr(v) for k, v in kwargs.items()}
            
            log_method(f"Appel {func.__name__}({', '.join(arg_repr)}, {kwarg_repr})")
            
            try:
                result = await func(*args, **kwargs)
                log_method(f"{func.__name__} terminé avec succès")
                return result
            except Exception as e:
                logger.error(f"Erreur dans {func.__name__}: {str(e)}")
                raise
        
        # Déterminer si la fonction est asynchrone ou synchrone
        if asyncio.iscoroutinefunction(func):
            return cast(F, wrapper_async)
        else:
            return cast(F, wrapper_sync)
            
    return decorator

# Exemple d'utilisation:
"""
@safe_cache_operation(fallback_value=[])
async def recherche_avec_cache(self, query, cache):
    # Le code est protégé contre les erreurs de sérialisation
    # En cas d'erreur, la fonction retournera []
    return await cache.get(query)
"""
