"""
Module vector_store_compat.py - Adaptateur de compatibilité pour les bases vectorielles

Ce module fournit une interface de compatibilité entre l'architecture 
existante et la nouvelle architecture d'adaptateurs vectoriels.
"""

import logging
import asyncio
import time
import os
from typing import Dict, List, Any, Optional, Union

# Import de la nouvelle architecture
from .factory import VectorStoreFactory

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.vector_stores.vector_store_compat")

class QdrantClientCompat:
    """
    Client Qdrant compatible avec l'ancien système
    
    Cette classe fournit une interface compatible avec l'ancien client Qdrant
    tout en utilisant notre nouvel adaptateur sous le capot.
    """
    
    def __init__(
        self, 
        url: str = None, 
        api_key: str = None,
        collection_name: str = "default",
        embedding_service = None
    ):
        """
        Initialise le client Qdrant compatible
        
        Args:
            url: URL du serveur Qdrant
            api_key: Clé API Qdrant
            collection_name: Nom de la collection par défaut
            embedding_service: Service d'embedding à utiliser
        """
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.embedding_service = embedding_service
        
        # Statistiques pour la compatibilité
        self.call_count = 0
        self.error_count = 0
        
        # Initialiser l'adaptateur vectoriel
        try:
            self.vector_adapter = VectorStoreFactory.create_adapter(
                provider="qdrant",
                qdrant_url=self.url,
                qdrant_api_key=self.api_key,
                embedding_service=self.embedding_service
            )
            
            logger.info(f"Client Qdrant compatible initialisé avec succès pour {self.url}")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du client Qdrant compatible: {str(e)}")
            self.vector_adapter = None
    
    def _get_collection_name(self, collection = None):
        """Récupère le nom de collection effectif"""
        return collection or self.collection_name
    
    async def search(
        self, 
        query_vector: List[float],
        collection_name: str = None,
        limit: int = 10,
        filter_query: Optional[Dict[str, Any]] = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Effectue une recherche par vecteur
        Compatible avec l'ancien système
        
        Args:
            query_vector: Vecteur de requête
            collection_name: Nom de la collection à interroger
            limit: Nombre maximum de résultats
            filter_query: Filtre à appliquer aux métadonnées
            with_payload: Inclure les métadonnées dans les résultats
            with_vectors: Inclure les vecteurs dans les résultats
            score_threshold: Score minimum pour les résultats
            
        Returns:
            Liste de résultats
        """
        if not self.vector_adapter:
            logger.error("Adaptateur vectoriel non initialisé")
            self.error_count += 1
            return []
        
        try:
            # Mettre à jour les statistiques
            self.call_count += 1
            
            # Déléguer à l'adaptateur
            collection = self._get_collection_name(collection_name)
            results = await self.vector_adapter.search(
                query_vector=query_vector,
                collection_name=collection,
                limit=limit,
                filter_query=filter_query,
                with_payload=with_payload,
                with_vectors=with_vectors,
                score_threshold=score_threshold
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche vectorielle: {str(e)}")
            self.error_count += 1
            return []
    
    async def search_by_embedding(
        self, 
        text: str,
        collection_name: str = None,
        limit: int = 10,
        filter_query: Optional[Dict[str, Any]] = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Effectue une recherche par texte
        Compatible avec l'ancien système
        
        Args:
            text: Texte de requête
            collection_name: Nom de la collection à interroger
            limit: Nombre maximum de résultats
            filter_query: Filtre à appliquer aux métadonnées
            with_payload: Inclure les métadonnées dans les résultats
            with_vectors: Inclure les vecteurs dans les résultats
            score_threshold: Score minimum pour les résultats
            
        Returns:
            Liste de résultats
        """
        if not self.vector_adapter:
            logger.error("Adaptateur vectoriel non initialisé")
            self.error_count += 1
            return []
        
        try:
            # Mettre à jour les statistiques
            self.call_count += 1
            
            # Déléguer à l'adaptateur
            collection = self._get_collection_name(collection_name)
            results = await self.vector_adapter.search_by_text(
                query_text=text,
                collection_name=collection,
                limit=limit,
                filter_query=filter_query,
                with_payload=with_payload,
                with_vectors=with_vectors,
                score_threshold=score_threshold
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche par texte: {str(e)}")
            self.error_count += 1
            return []
    
    async def retrieve(
        self,
        ids: Union[str, List[str]],
        collection_name: str = None,
        with_vectors: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Récupère des éléments par leurs IDs
        Compatible avec l'ancien système
        
        Args:
            ids: ID ou liste d'IDs à récupérer
            collection_name: Nom de la collection
            with_vectors: Inclure les vecteurs dans le résultat
            
        Returns:
            Liste d'éléments
        """
        if not self.vector_adapter:
            logger.error("Adaptateur vectoriel non initialisé")
            self.error_count += 1
            return []
        
        # Normaliser les IDs en liste
        if isinstance(ids, str):
            ids = [ids]
        
        try:
            # Mettre à jour les statistiques
            self.call_count += 1
            
            # Déléguer à l'adaptateur pour chaque ID
            collection = self._get_collection_name(collection_name)
            results = []
            
            for id in ids:
                item = await self.vector_adapter.get_by_id(
                    id=id,
                    collection_name=collection,
                    with_vectors=with_vectors
                )
                
                if item:
                    results.append(item)
            
            return results
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération par IDs: {str(e)}")
            self.error_count += 1
            return []
    
    async def upsert(
        self,
        points: List[Dict[str, Any]],
        collection_name: str = None
    ) -> bool:
        """
        Insère ou met à jour des éléments
        Compatible avec l'ancien système
        
        Args:
            points: Liste de points à insérer/mettre à jour
            collection_name: Nom de la collection
            
        Returns:
            True si l'opération a réussi
        """
        if not self.vector_adapter:
            logger.error("Adaptateur vectoriel non initialisé")
            self.error_count += 1
            return False
        
        try:
            # Mettre à jour les statistiques
            self.call_count += 1
            
            # Déléguer à l'adaptateur pour chaque point
            collection = self._get_collection_name(collection_name)
            success = True
            
            for point in points:
                # Extraire les informations du point
                point_id = point.get("id")
                vector = point.get("vector")
                payload = point.get("payload", {})
                
                # Vérifier les données requises
                if not point_id or not vector:
                    logger.warning(f"Point incomplet ignoré: {point}")
                    continue
                
                # Effectuer l'upsert
                result = await self.vector_adapter.upsert(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                    collection_name=collection
                )
                
                success = success and result
            
            return success
            
        except Exception as e:
            logger.error(f"Erreur lors de l'insertion/mise à jour: {str(e)}")
            self.error_count += 1
            return False
    
    async def delete(
        self,
        ids: Union[str, List[str]],
        collection_name: str = None
    ) -> bool:
        """
        Supprime des éléments
        Compatible avec l'ancien système
        
        Args:
            ids: ID ou liste d'IDs à supprimer
            collection_name: Nom de la collection
            
        Returns:
            True si l'opération a réussi
        """
        if not self.vector_adapter:
            logger.error("Adaptateur vectoriel non initialisé")
            self.error_count += 1
            return False
        
        # Normaliser les IDs en liste
        if isinstance(ids, str):
            ids = [ids]
        
        try:
            # Mettre à jour les statistiques
            self.call_count += 1
            
            # Déléguer à l'adaptateur pour chaque ID
            collection = self._get_collection_name(collection_name)
            success = True
            
            for id in ids:
                result = await self.vector_adapter.delete(
                    id=id,
                    collection_name=collection
                )
                
                success = success and result
            
            return success
            
        except Exception as e:
            logger.error(f"Erreur lors de la suppression: {str(e)}")
            self.error_count += 1
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité et l'état de santé
        Compatible avec l'ancien système
        
        Returns:
            Dictionnaire avec statut et informations
        """
        if not self.vector_adapter:
            return {
                "status": "unhealthy",
                "error": "Adaptateur vectoriel non initialisé",
                "url": self.url,
                "collection": self.collection_name,
                "stats": {
                    "calls": self.call_count,
                    "errors": self.error_count,
                    "error_rate": f"{(self.error_count / self.call_count * 100) if self.call_count > 0 else 0:.2f}%"
                }
            }
        
        try:
            # Récupérer l'état de santé de l'adaptateur
            adapter_health = await self.vector_adapter.health_check()
            
            # Ajouter les statistiques de compatibilité
            health = {
                "status": adapter_health.get("status", "unknown"),
                "url": self.url,
                "collection": self.collection_name,
                "collections": adapter_health.get("collections", []),
                "stats": {
                    "calls": self.call_count,
                    "errors": self.error_count,
                    "error_rate": f"{(self.error_count / self.call_count * 100) if self.call_count > 0 else 0:.2f}%"
                },
                "adapter": adapter_health
            }
            
            return health
            
        except Exception as e:
            logger.error(f"Erreur lors du contrôle de santé: {str(e)}")
            
            return {
                "status": "error",
                "error": str(e),
                "url": self.url,
                "collection": self.collection_name,
                "stats": {
                    "calls": self.call_count,
                    "errors": self.error_count,
                    "error_rate": f"{(self.error_count / self.call_count * 100) if self.call_count > 0 else 0:.2f}%"
                }
            }
