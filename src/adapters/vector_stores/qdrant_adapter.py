"""
Module qdrant_adapter.py - Adaptateur pour Qdrant

Ce module implémente l'interface VectorStoreAdapter pour Qdrant,
fournissant un accès abstrait aux collections vectorielles.
"""

import logging
import asyncio
import time
from typing import Dict, List, Any, Optional
import os

# Import de l'interface abstraite
from .base import VectorStoreAdapter

# Import du service d'embedding
from ..embeddings.factory import EmbeddingServiceFactory

# Configuration du logging
logger = logging.getLogger("ITS_HELP.adapters.vector_stores.qdrant")

class QdrantAdapter(VectorStoreAdapter):
    """
    Adaptateur pour la base vectorielle Qdrant avec support multi-collections
    """
    
    def __init__(
        self, 
        qdrant_url: str = None,
        qdrant_api_key: str = None,
        embedding_service = None,
        connection_timeout: float = 5.0,
        operation_timeout: float = 30.0
    ):
        """
        Initialise l'adaptateur Qdrant
        
        Args:
            qdrant_url: URL du serveur Qdrant (défaut: variable d'environnement QDRANT_URL)
            qdrant_api_key: Clé API pour l'authentification (défaut: variable d'environnement QDRANT_API_KEY)
            embedding_service: Service d'embedding à utiliser
            connection_timeout: Timeout de connexion en secondes
            operation_timeout: Timeout des opérations en secondes
        """
        # Configuration des variables
        self.qdrant_url = qdrant_url or os.getenv('QDRANT_URL', 'http://localhost:6333')
        self.qdrant_api_key = qdrant_api_key or os.getenv('QDRANT_API_KEY')
        self._provider_name = "qdrant"  # Stocké comme attribut privé
        self.connection_timeout = connection_timeout
        self.operation_timeout = operation_timeout
        
        # Client Qdrant (initialisé à la demande)
        self._client = None
        
        # Vérifier si un service d'embedding est fourni
        if embedding_service:
            self.embedding_service = embedding_service
        else:
            # Utiliser le service d'embedding par défaut (OpenAI)
            self.embedding_service = EmbeddingServiceFactory.create_service("openai")
            
        # Sémaphore pour limiter les connexions concurrentes
        self._connection_semaphore = asyncio.Semaphore(10)
        
        logger.info(f"Adaptateur Qdrant initialisé: {self.qdrant_url}")
        
    async def _get_client(self):
        """
        Récupère ou crée le client Qdrant
        
        Returns:
            Client Qdrant initialisé
        """
        # Si le client existe déjà, le retourner
        if self._client:
            return self._client
            
        # Importer Qdrant seulement quand nécessaire
        try:
            from qdrant_client import QdrantClient
            
            # Créer le client avec les paramètres configurés
            self._client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
                timeout=self.connection_timeout
            )
            
            # Tester la connexion
            await asyncio.to_thread(self._client.get_collections)
            
            logger.info(f"Connexion Qdrant établie: {self.qdrant_url}")
            return self._client
            
        except Exception as e:
            logger.error(f"Erreur de connexion à Qdrant: {str(e)}")
            # Réinitialiser le client pour les prochaines tentatives
            self._client = None
            raise
    
    @property
    def provider_name(self) -> str:
        """
        Retourne le nom du provider
        
        Returns:
            'qdrant'
        """
        return self._provider_name
    
    def _normalize_result(self, result, with_vectors=False, include_score=True) -> Dict[str, Any]:
        """
        Normalise un résultat Qdrant au format standard
        
        Args:
            result: Résultat Qdrant
            with_vectors: Inclure les vecteurs
            include_score: Inclure le score
            
        Returns:
            Résultat normalisé
        """
        normalized = {}
        
        # Ajouter l'identifiant
        if hasattr(result, 'id'):
            normalized["id"] = result.id
        
        # Ajouter le score si demandé
        if include_score and hasattr(result, 'score'):
            normalized["score"] = result.score
        
        # Ajouter le vecteur si demandé
        if with_vectors and hasattr(result, 'vector'):
            normalized["vector"] = result.vector
        
        # Ajouter les métadonnées (payload)
        if hasattr(result, 'payload'):
            normalized["payload"] = result.payload
        
        return normalized
    
    async def search(
        self, 
        query_vector: List[float],
        collection_name: str,
        limit: int = 10,
        filter_query: Optional[Dict[str, Any]] = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Effectue une recherche par similarité dans Qdrant
        
        Args:
            query_vector: Vecteur de requête
            collection_name: Nom de la collection à interroger
            limit: Nombre maximum de résultats
            filter_query: Filtre à appliquer aux métadonnées
            with_payload: Inclure les métadonnées dans les résultats
            with_vectors: Inclure les vecteurs dans les résultats
            score_threshold: Score minimum pour les résultats
            
        Returns:
            Liste de résultats triés par score décroissant
        """
        if not collection_name:
            logger.error("Nom de collection non spécifié pour la recherche")
            return []
        
        async with self._connection_semaphore:
            client = await self._get_client()
        
        try:
            # Incrémenter les métriques
            self._search_count += 1
            
            # Convertir le filtre au format Qdrant si nécessaire
            qdrant_filter = self._convert_filter(filter_query) if filter_query else None
            
            # Préparer les options de recherche
            search_params = {
                "collection_name": collection_name,
                "query_vector": query_vector,
                "limit": limit,
                "with_payload": with_payload,
                "with_vectors": with_vectors
            }
            
            # Ajouter le filtre et le seuil de score si spécifiés
            if qdrant_filter:
                search_params["query_filter"] = qdrant_filter
                
            if score_threshold is not None:
                search_params["score_threshold"] = score_threshold
            
            # Effectuer la recherche avec timeout
            async with asyncio.timeout(self.operation_timeout):
                start_time = time.time()
                results = client.search(**search_params)
                elapsed_time = time.time() - start_time
            
            # Journaliser le résultat
            logger.debug(
                f"Recherche Qdrant effectuée dans {collection_name}: "
                f"{len(results)} résultats en {elapsed_time:.2f}s"
            )
            
            # Normaliser les résultats
            normalized_results = [
                self._normalize_result(result, with_vectors=with_vectors)
                for result in results
            ]
            
            return normalized_results
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Erreur lors de la recherche dans Qdrant: {str(e)}")
            return []
    
    async def search_by_text(
        self,
        query_text: str,
        collection_name: str,
        limit: int = 10,
        filter_query: Optional[Dict[str, Any]] = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Effectue une recherche par texte dans Qdrant
        
        Args:
            query_text: Texte de requête
            collection_name: Nom de la collection à interroger
            limit: Nombre maximum de résultats
            filter_query: Filtre à appliquer aux métadonnées
            with_payload: Inclure les métadonnées dans les résultats
            with_vectors: Inclure les vecteurs dans les résultats
            score_threshold: Score minimum pour les résultats
            
        Returns:
            Liste de résultats triés par score décroissant
        """
        # Vérifier si un service d'embedding est disponible
        if not self.embedding_service:
            logger.error("Service d'embedding non disponible pour la recherche par texte")
            return []
        
        try:
            # Incrémenter les métriques
            self._query_count += 1
            
            # Générer l'embedding pour le texte de requête
            query_vector = await self.embedding_service.get_embedding(query_text)
            
            # Déléguer à la recherche par vecteur
            return await self.search(
                query_vector=query_vector,
                collection_name=collection_name,
                limit=limit,
                filter_query=filter_query,
                with_payload=with_payload,
                with_vectors=with_vectors,
                score_threshold=score_threshold
            )
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Erreur lors de la recherche par texte dans Qdrant: {str(e)}")
            return []
    
    async def get_by_id(
        self,
        id: str,
        collection_name: str,
        with_vectors: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Récupère un élément par son ID
        
        Args:
            id: Identifiant de l'élément
            collection_name: Nom de la collection
            with_vectors: Inclure les vecteurs dans le résultat
            
        Returns:
            Élément trouvé ou None
        """
        if not collection_name or not id:
            logger.error("Nom de collection ou ID non spécifié pour la récupération")
            return None
        
        async with self._connection_semaphore:
            client = await self._get_client()
        
        try:
            # Effectuer la récupération avec timeout
            async with asyncio.timeout(self.operation_timeout):
                start_time = time.time()
                result = client.retrieve(
                    collection_name=collection_name,
                    ids=[id],
                    with_vectors=with_vectors
                )
                elapsed_time = time.time() - start_time
            
            # Vérifier si un résultat a été trouvé
            if not result or len(result) == 0:
                logger.debug(f"Aucun élément trouvé avec l'ID {id} dans {collection_name}")
                return None
            
            # Journaliser le résultat
            logger.debug(
                f"Récupération par ID effectuée dans {collection_name} en {elapsed_time:.2f}s"
            )
            
            # Normaliser le résultat (sans score car retrieve ne retourne pas de score)
            normalized = self._normalize_result(result[0], with_vectors=with_vectors, include_score=False)
            return normalized
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Erreur lors de la récupération par ID dans Qdrant: {str(e)}")
            return None
    
    async def upsert(
        self,
        id: str,
        vector: List[float],
        payload: Dict[str, Any],
        collection_name: str
    ) -> bool:
        """
        Insère ou met à jour un élément dans Qdrant
        
        Args:
            id: Identifiant de l'élément
            vector: Vecteur d'embedding
            payload: Métadonnées associées
            collection_name: Nom de la collection
            
        Returns:
            True si l'opération a réussi
        """
        if not collection_name:
            logger.error("Nom de collection non spécifié pour l'insertion")
            return False
        
        async with self._connection_semaphore:
            client = await self._get_client()
        
        try:
            from qdrant_client.models import PointStruct
            
            # Incrémenter les métriques
            self._insert_count += 1
            
            # Préparer le point
            point = PointStruct(
                id=id,
                vector=vector,
                payload=payload
            )
            
            # Effectuer l'insertion avec timeout
            async with asyncio.timeout(self.operation_timeout):
                start_time = time.time()
                client.upsert(
                    collection_name=collection_name,
                    points=[point]
                )
                elapsed_time = time.time() - start_time
            
            # Journaliser le résultat
            logger.debug(
                f"Insertion/mise à jour effectuée dans {collection_name} "
                f"pour l'ID {id} en {elapsed_time:.2f}s"
            )
            
            return True
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Erreur lors de l'insertion dans Qdrant: {str(e)}")
            return False
    
    async def upsert_text(
        self, 
        id: str, 
        text: str,
        payload: Optional[Dict[str, Any]] = None, 
        collection_name: str = "default",
        model: Optional[str] = None
    ) -> bool:
        """
        Insère ou met à jour un document à partir de son texte en générant automatiquement l'embedding
        
        Args:
            id: Identifiant unique du document
            text: Texte du document pour générer l'embedding
            payload: Métadonnées associées au document
            collection_name: Nom de la collection
            model: Modèle d'embedding à utiliser (facultatif)
            
        Returns:
            True si succès, False sinon
        """
        if not text:
            logger.error("Le texte ne peut pas être vide pour générer un embedding")
            return False
            
        if not id:
            logger.error("L'ID ne peut pas être vide")
            return False
            
        try:
            # Générer l'embedding
            if not self.embedding_service:
                logger.error("Aucun service d'embedding n'est configuré")
                return False
                
            vector = await self.embedding_service.get_embedding(text, model)
            
            # Préparer le payload
            combined_payload = {
                "text": text  # Toujours inclure le texte original
            }
            
            # Ajouter les autres métadonnées
            if payload:
                # Si payload contient déjà 'text', il sera écrasé
                combined_payload.update(payload)
                
            # Insérer/mettre à jour avec l'embedding généré
            return await self.upsert(
                id=id,
                vector=vector,
                payload=combined_payload,
                collection_name=collection_name
            )
            
        except Exception as e:
            logger.error(f"Erreur lors de l'upsert par texte: {str(e)}")
            return False

    async def delete(
        self,
        id: str,
        collection_name: str
    ) -> bool:
        """
        Supprime un élément de Qdrant
        
        Args:
            id: Identifiant de l'élément
            collection_name: Nom de la collection
            
        Returns:
            True si l'opération a réussi
        """
        if not collection_name or not id:
            logger.error("Nom de collection ou ID non spécifié pour la suppression")
            return False
        
        async with self._connection_semaphore:
            client = await self._get_client()
        
        try:
            # Effectuer la suppression avec timeout
            async with asyncio.timeout(self.operation_timeout):
                start_time = time.time()
                client.delete(
                    collection_name=collection_name,
                    points_selector=[id]
                )
                elapsed_time = time.time() - start_time
            
            # Journaliser le résultat
            logger.debug(
                f"Suppression effectuée dans {collection_name} "
                f"pour l'ID {id} en {elapsed_time:.2f}s"
            )
            
            return True
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Erreur lors de la suppression dans Qdrant: {str(e)}")
            return False
    
    async def list_collections(self) -> List[str]:
        """
        Liste les collections disponibles
        
        Returns:
            Liste des noms de collections
        """
        async with self._connection_semaphore:
            client = await self._get_client()
        
        try:
            # Récupérer la liste des collections avec timeout
            async with asyncio.timeout(self.operation_timeout):
                start_time = time.time()
                collections = client.get_collections()
                elapsed_time = time.time() - start_time
            
            # Extraire les noms des collections
            collection_names = [collection.name for collection in collections.collections]
            
            # Journaliser le résultat
            logger.debug(
                f"{len(collection_names)} collections trouvées en {elapsed_time:.2f}s"
            )
            
            return collection_names
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Erreur lors de la récupération des collections Qdrant: {str(e)}")
            return []
    
    async def collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        Récupère les informations sur une collection
        
        Args:
            collection_name: Nom de la collection
            
        Returns:
            Informations sur la collection
        """
        if not collection_name:
            logger.error("Nom de collection non spécifié pour les informations")
            return {}
        
        async with self._connection_semaphore:
            client = await self._get_client()
        
        try:
            # Récupérer les informations sur la collection avec timeout
            async with asyncio.timeout(self.operation_timeout):
                start_time = time.time()
                collection_info = client.get_collection(collection_name)
                elapsed_time = time.time() - start_time
            
            # Journaliser le résultat
            logger.debug(
                f"Informations sur la collection {collection_name} récupérées en {elapsed_time:.2f}s"
            )
            
            # Convertir les informations en dictionnaire
            info = {
                "name": collection_name,
                "vectors_count": collection_info.vectors_count,
                "status": collection_info.status,
                "dimension": collection_info.config.params.vectors.size,
                "distance": collection_info.config.params.vectors.distance
            }
            
            # Ajouter les index si disponibles
            if hasattr(collection_info.config.params.vectors, "hnsw_config"):
                info["index_type"] = "hnsw"
                info["index_params"] = {
                    "m": collection_info.config.params.vectors.hnsw_config.m,
                    "ef_construct": collection_info.config.params.vectors.hnsw_config.ef_construct
                }
            
            return info
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Erreur lors de la récupération des informations sur la collection: {str(e)}")
            return {"name": collection_name, "error": str(e)}
    
    def _convert_filter(self, filter_query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convertit un filtre générique au format Qdrant
        
        Args:
            filter_query: Filtre à convertir
            
        Returns:
            Filtre au format Qdrant
        """
        # La plupart des filtres simples sont directement compatibles avec Qdrant
        # Pour les cas spéciaux, une conversion peut être nécessaire
        return filter_query
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité et l'état de santé de Qdrant
        
        Returns:
            Dictionnaire avec statut et informations
        """
        try:
            async with self._connection_semaphore:
                await self._get_client()
            
            # Test simple pour vérifier la connexion
            start_time = time.time()
            collections = await self.list_collections()
            elapsed_time = time.time() - start_time
            
            # Collecter des statistiques sur les collections
            collection_stats = []
            for collection_name in collections:
                try:
                    info = await self.collection_info(collection_name)
                    collection_stats.append(info)
                except Exception:
                    # Ignorer les erreurs pour une collection spécifique
                    pass
            
            return {
                "provider": self._provider_name,
                "status": "healthy",
                "latency_ms": int(elapsed_time * 1000),
                "url": self.qdrant_url,
                "collections_count": len(collections),
                "collections": collection_stats,
                "metrics": {
                    "searches": self._search_count,
                    "queries": self._query_count,
                    "inserts": self._insert_count,
                    "errors": self._error_count,
                    "error_rate": f"{(self._error_count / (self._search_count + self._query_count + self._insert_count) * 100) if (self._search_count + self._query_count + self._insert_count) > 0 else 0:.2f}%"
                }
            }
        except Exception as e:
            logger.error(f"Échec du contrôle de santé Qdrant: {str(e)}")
            
            return {
                "provider": self._provider_name,
                "status": "unhealthy",
                "error": str(e),
                "url": self.qdrant_url,
                "metrics": {
                    "searches": self._search_count,
                    "queries": self._query_count,
                    "inserts": self._insert_count,
                    "errors": self._error_count
                }
            }
