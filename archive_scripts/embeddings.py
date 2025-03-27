#embeddings.py
from base_de_donnees import global_cache
import hashlib
import logging
from typing import List, Optional, Tuple
import asyncio
class EmbeddingService:
    """Service centralisé de génération d'embeddings avec cache optimisé."""
    
    def __init__(self, openai_client, cache=None):
        self.openai_client = openai_client
        self.cache = cache or global_cache  # Utilise le cache global par défaut
        self.logger = logging.getLogger('ITS_HELP.embeddings')
        self.namespace = "embeddings"
        self.model = "text-embedding-ada-002"
        self.dimension = 1536  # Dimension attendue pour ada-002
        self.max_retries = 3
        self.retry_base_delay = 1
        self.stats = {"hits": 0, "misses": 0, "errors": 0}
        
    def _get_cache_key(self, text: str) -> str:
        """Génère une clé de cache unique pour le texte."""
        return hashlib.md5(text.strip().encode('utf-8')).hexdigest()
    
    def _validate_vector(self, vector: List[float]) -> bool:
        """Valide le vecteur d'embedding."""
        if not isinstance(vector, list):
            return False
        if not vector or len(vector) != self.dimension:
            return False
        if not all(isinstance(x, float) for x in vector):
            return False
        return True
    
    async def get_embedding(self, text: str, force_refresh=False) -> Optional[List[float]]:
        """
        Génère un embedding avec gestion optimisée du cache et des erreurs.
        
        Args:
            text: Texte à transformer en embedding
            force_refresh: Force la régénération même si présent en cache
            
        Returns:
            Liste des valeurs de l'embedding ou None en cas d'erreur
        """
        if not text or not isinstance(text, str) or len(text.strip()) < 2:
            self.logger.warning("Texte invalide ou trop court")
            return None
            
        # Normalisation du texte
        text = text.strip()
        
        # Vérification du cache
        cache_key = self._get_cache_key(text)
        if not force_refresh:
            cached_vector = await self.cache.get(cache_key, self.namespace)
            if cached_vector:
                self.stats["hits"] += 1
                return cached_vector
        
        self.stats["misses"] += 1
        
        # Génération avec gestion des tentatives
        for attempt in range(self.max_retries):
            try:
                response = await self.openai_client.embeddings.create(
                    input=text,
                    model=self.model
                )
                
                if not response.data:
                    raise ValueError("Réponse OpenAI vide")
                    
                vector = response.data[0].embedding
                
                if not self._validate_vector(vector):
                    raise ValueError(f"Format d'embedding invalide: longueur={len(vector)}")
                    
                # Mise en cache
                await self.cache.set(cache_key, vector, self.namespace)
                
                return vector
                
            except Exception as e:
                self.logger.warning(f"Tentative {attempt+1}/{self.max_retries} échouée: {str(e)}")
                
                if attempt < self.max_retries - 1:
                    # Délai exponentiel entre les tentatives
                    retry_delay = self.retry_base_delay * (2 ** attempt)
                    await asyncio.sleep(retry_delay)
                else:
                    self.stats["errors"] += 1
                    self.logger.error(f"Échec définitif après {self.max_retries} tentatives: {str(e)}")
                    return None
    
    async def get_similar_embeddings(self, text: str, threshold=0.85) -> List[Tuple[str, List[float]]]:
        """
        Trouve des embeddings similaires dans le cache.
        Utile pour suggérer des questions similaires ou réutiliser des embeddings proches.
        
        Args:
            text: Texte de référence
            threshold: Seuil de similarité (cosinus)
            
        Returns:
            Liste de tuples (texte original, embedding)
        """
        # À implémenter lorsque nous aurons une façon de stocker le texte original
        # avec les embeddings dans le cache
        return []
    
    def get_stats(self):
        """Retourne les statistiques d'utilisation."""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total) * 100 if total > 0 else 0
        
        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "errors": self.stats["errors"],
            "hit_rate": f"{hit_rate:.1f}%",
            "total_requests": total
        }