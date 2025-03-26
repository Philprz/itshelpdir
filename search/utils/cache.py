"""
Module cache - Système de cache pour les recherches
"""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger('ITS_HELP.cache')

class SearchCache:
    """
    Système de cache pour les résultats de recherche et les embeddings.
    Permet de réduire les appels aux services externes et d'améliorer les performances.
    """
    
    def __init__(self, max_size: int = 500, ttl_seconds: int = 3600):
        """
        Initialise le cache avec une taille maximale et un temps de vie.
        
        Args:
            max_size: Nombre maximum d'éléments dans le cache
            ttl_seconds: Temps de vie des éléments en secondes
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Tuple[Any, float]] = {}  # {key: (value, timestamp)}
        self.hits = 0
        self.misses = 0
        self.logger = logger
        
    def _generate_key(self, prefix: str, query: str, **kwargs) -> str:
        """
        Génère une clé unique pour le cache basée sur les paramètres.
        
        Args:
            prefix: Préfixe pour identifier le type d'élément caché
            query: Requête principale
            kwargs: Paramètres additionnels pour la clé
            
        Returns:
            Clé unique pour le cache
        """
        # Normalisation de la requête et extraction des informations clés
        query = query.strip().lower()
        
        # Création de la clé avec le préfixe et la requête
        key_parts = [prefix, query]
        
        # Ajout des paramètres additionnels
        for k, v in sorted(kwargs.items()):
            if v is not None:
                if isinstance(v, (list, tuple)):
                    key_parts.append(f"{k}={','.join(str(x) for x in v)}")
                else:
                    key_parts.append(f"{k}={v}")
        
        return ":".join(key_parts)
    
    def get(self, key: str) -> Optional[Any]:
        """
        Récupère une valeur du cache.
        
        Args:
            key: Clé de l'élément à récupérer
            
        Returns:
            Valeur associée à la clé ou None si l'élément n'est pas dans le cache
            ou s'il a expiré
        """
        if key not in self.cache:
            self.misses += 1
            return None
            
        value, timestamp = self.cache[key]
        current_time = time.time()
        
        # Vérifier si l'élément a expiré
        if current_time - timestamp > self.ttl_seconds:
            del self.cache[key]
            self.misses += 1
            return None
            
        self.hits += 1
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        Ajoute ou met à jour un élément dans le cache.
        
        Args:
            key: Clé de l'élément
            value: Valeur à stocker
        """
        # Si le cache a atteint sa taille maximale, supprimer l'élément le plus ancien
        if len(self.cache) >= self.max_size:
            # Trouver la clé avec le timestamp le plus ancien
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
            
        self.cache[key] = (value, time.time())
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Récupère un embedding du cache.
        
        Args:
            text: Texte pour lequel récupérer l'embedding
            
        Returns:
            Liste d'embedding ou None si non trouvé
        """
        key = self._generate_key("embedding", text)
        return self.get(key)
    
    def set_embedding(self, text: str, embedding: List[float]) -> None:
        """
        Stocke un embedding dans le cache.
        
        Args:
            text: Texte pour lequel stocker l'embedding
            embedding: Embedding à stocker
        """
        key = self._generate_key("embedding", text)
        self.set(key, embedding)
    
    def get_search_results(self, 
                           source: str, 
                           query: str, 
                           client_name: Optional[str] = None,
                           limit: int = 10) -> Optional[List[Any]]:
        """
        Récupère des résultats de recherche du cache.
        
        Args:
            source: Source de données (ex: jira, zendesk)
            query: Requête de recherche
            client_name: Nom du client pour filtrer les résultats
            limit: Nombre maximum de résultats
            
        Returns:
            Liste de résultats ou None si non trouvé
        """
        key = self._generate_key("search", query, source=source, client=client_name, limit=limit)
        return self.get(key)
    
    def set_search_results(self, 
                          source: str, 
                          query: str, 
                          results: List[Any],
                          client_name: Optional[str] = None,
                          limit: int = 10) -> None:
        """
        Stocke des résultats de recherche dans le cache.
        
        Args:
            source: Source de données (ex: jira, zendesk)
            query: Requête de recherche
            results: Liste de résultats à stocker
            client_name: Nom du client pour filtrer les résultats
            limit: Nombre maximum de résultats
        """
        key = self._generate_key("search", query, source=source, client=client_name, limit=limit)
        self.set(key, results)
    
    def clear(self) -> None:
        """Vide le cache."""
        self.cache.clear()
        
    def get_stats(self) -> Dict[str, Any]:
        """
        Retourne des statistiques sur l'utilisation du cache.
        
        Returns:
            Dictionnaire de statistiques
        """
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests) * 100 if total_requests > 0 else 0
        
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.2f}%",
            "total_requests": total_requests
        }
