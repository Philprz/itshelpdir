"""
Module base.py - Interface abstraite pour les adaptateurs vectoriels

Ce module définit l'interface commune que tous les adaptateurs de bases 
de données vectorielles doivent implémenter, permettant une abstraction 
complète du système sous-jacent.
"""

import abc
from typing import Dict, List, Any, Optional, Union, Tuple

class VectorStoreAdapter(abc.ABC):
    """Interface abstraite pour tous les adaptateurs de bases de données vectorielles"""
    
    @abc.abstractmethod
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
        Effectue une recherche par similarité dans la base vectorielle
        
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
        pass
    
    @abc.abstractmethod
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
        Effectue une recherche par texte dans la base vectorielle
        
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
        pass
    
    @abc.abstractmethod
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
        pass
    
    @abc.abstractmethod
    async def upsert(
        self,
        id: str,
        vector: List[float],
        payload: Dict[str, Any],
        collection_name: str
    ) -> bool:
        """
        Insère ou met à jour un élément dans la base vectorielle
        
        Args:
            id: Identifiant de l'élément
            vector: Vecteur d'embedding
            payload: Métadonnées associées
            collection_name: Nom de la collection
            
        Returns:
            True si l'opération a réussi
        """
        pass
    
    @abc.abstractmethod
    async def delete(
        self,
        id: str,
        collection_name: str
    ) -> bool:
        """
        Supprime un élément de la base vectorielle
        
        Args:
            id: Identifiant de l'élément
            collection_name: Nom de la collection
            
        Returns:
            True si l'opération a réussi
        """
        pass
    
    @abc.abstractmethod
    async def list_collections(self) -> List[str]:
        """
        Liste les collections disponibles
        
        Returns:
            Liste des noms de collections
        """
        pass
    
    @abc.abstractmethod
    async def collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        Récupère les informations sur une collection
        
        Args:
            collection_name: Nom de la collection
            
        Returns:
            Informations sur la collection
        """
        pass
    
    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """
        Nom du fournisseur de base vectorielle
        
        Returns:
            Nom du provider
        """
        pass
    
    @abc.abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité et l'état de santé de la base vectorielle
        
        Returns:
            Dictionnaire avec statut et informations
        """
        pass
