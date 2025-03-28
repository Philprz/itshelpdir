"""
Module compat.py - Compatibilité avec l'ancienne architecture

Ce module fournit des adaptateurs et wrappers qui permettent aux composants
existants (search/) de fonctionner avec la nouvelle architecture (src/)
sans rupture, pendant la phase de transition.
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional, Union

# Imports de la nouvelle architecture
from src.core.pipeline import Pipeline, PipelineConfig
from src.core.query_engine import QueryEngine
from src.infrastructure.cache import get_cache_instance

# Configuration du logging
logger = logging.getLogger("ITS_HELP.core.compat")

# Instance partagée du pipeline
_shared_pipeline = None

async def get_pipeline() -> Pipeline:
    """
    Récupère ou crée l'instance partagée du pipeline
    
    Returns:
        Instance du pipeline
    """
    global _shared_pipeline
    
    if _shared_pipeline is None:
        config = PipelineConfig(
            enable_cache=True,
            parallel_searches=True,
            max_concurrent_searches=6,
            enable_circuit_breakers=True,
            search_limit=10,
            similarity_threshold=0.6
        )
        
        _shared_pipeline = Pipeline(config)
        await _shared_pipeline.initialize()
        
    return _shared_pipeline

class SearchFactoryAdapter:
    """
    Adaptateur pour SearchClientFactory de l'ancienne architecture
    
    Cette classe imite l'interface de SearchClientFactory tout en utilisant
    la nouvelle architecture sous le capot, permettant une transition transparente.
    """
    
    def __init__(self):
        """Initialise l'adaptateur"""
        self.pipeline = None
        self.query_engine = None
        self.initialized = False
        self.logger = logging.getLogger('ITS_HELP.search.factory')
        
    async def initialize(self):
        """Initialise les composants sous-jacents"""
        if self.initialized:
            return
            
        self.pipeline = await get_pipeline()
        self.query_engine = self.pipeline.query_engine
        self.initialized = True
        
    async def get_search_client(self, client_type: str):
        """
        Récupère un client de recherche du type spécifié
        
        Args:
            client_type: Type du client (jira, zendesk, etc.)
            
        Returns:
            Client adapté à l'ancienne interface
        """
        if not self.initialized:
            await self.initialize()
            
        # Créer un adaptateur pour le client de recherche demandé
        return SearchClientAdapter(client_type, self.query_engine)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Renvoie l'état actuel de l'adaptateur
        
        Returns:
            Dictionnaire avec les informations d'état
        """
        if self.pipeline:
            return self.pipeline.get_status()
        
        return {
            "initialized": self.initialized,
            "message": "Non initialisé"
        }
        
    # Compatibilité avec les attributs de l'ancien SearchClientFactory
    @property
    def clients(self):
        return {}  # Simuler un dictionnaire vide
        
    @property
    def default_collections(self):
        return self.query_engine.collection_types if self.query_engine else {}


class SearchClientAdapter:
    """
    Adaptateur pour les clients de recherche de l'ancienne architecture
    
    Cette classe imite l'interface des clients de recherche spécifiques
    tout en utilisant le QueryEngine de la nouvelle architecture.
    """
    
    def __init__(self, client_type: str, query_engine: QueryEngine):
        """
        Initialise l'adaptateur
        
        Args:
            client_type: Type du client (jira, zendesk, etc.)
            query_engine: Instance de QueryEngine
        """
        self.client_type = client_type
        self.query_engine = query_engine
        self.logger = logging.getLogger(f'ITS_HELP.search.clients.{client_type}')
        
    async def recherche_intelligente(self, question: str, **kwargs):
        """
        Imite la méthode recherche_intelligente des anciens clients
        
        Args:
            question: Question à rechercher
            **kwargs: Arguments additionnels
            
        Returns:
            Résultats de la recherche
        """
        try:
            # Exécuter la recherche avec le QueryEngine
            query_result = await self.query_engine.execute_query(
                query=question,
                collections=[self.client_type],
                limit_per_collection=kwargs.get('limit', 10),
                similarity_threshold=kwargs.get('similarity_threshold', 0.6),
                enable_semantic=True,
                timeout=kwargs.get('timeout', 30.0)
            )
            
            # Convertir les résultats au format attendu
            if self.client_type in query_result.results:
                results = query_result.results[self.client_type]
                return self._format_results(results)
            
            return []
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche: {str(e)}")
            return []
    
    async def recherche_similaire(self, vecteur, filtre=None, limit=10, min_score=0.6):
        """
        Imite la méthode recherche_similaire des anciens clients
        
        Args:
            vecteur: Vecteur d'embedding
            filtre: Filtre Qdrant (optionnel)
            limit: Nombre max de résultats
            min_score: Score minimal
            
        Returns:
            Résultats de la recherche
        """
        try:
            if not isinstance(vecteur, list):
                raise ValueError("L'embedding doit être une liste de flottants")
                
            # Récupérer le vector store
            vector_store = self.query_engine.vector_stores.get(self.client_type)
            if not vector_store:
                self.logger.error(f"Vector store '{self.client_type}' non disponible")
                return []
                
            # Exécuter la recherche
            search_results = await vector_store.similarity_search_with_score(
                embedding=vecteur,
                limit=limit,
                similarity_threshold=min_score,
                filter=filtre
            )
            
            # Convertir les résultats au format attendu
            return self._format_results([
                self.query_engine._normalize_result(result, self.client_type)
                for result in search_results
            ])
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche similaire: {str(e)}")
            return []
    
    def _format_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Formate les résultats selon l'ancienne structure
        
        Args:
            results: Résultats au format nouveau
            
        Returns:
            Résultats au format ancien
        """
        formatted_results = []
        
        for result in results:
            # Compatibilité avec l'ancien format
            formatted = {
                "score": result.get("score", 0.0),
            }
            
            # Ajouter le contenu et les métadonnées
            if "content" in result:
                formatted["payload"] = result["content"]
            if "metadata" in result:
                formatted["metadata"] = result["metadata"]
                
            formatted_results.append(formatted)
            
        return formatted_results
    
    # Méthodes mimiques pour compatibilité
    def get_source_name(self):
        """Renvoie le nom de la source"""
        return self.client_type.upper()
    
    def valider_resultat(self, result: Any):
        """Valide un résultat (mimique)"""
        return True
    
    def format_for_slack(self, result: Any):
        """Formate un résultat pour Slack (mimique)"""
        if not result:
            return "Aucun résultat trouvé."
            
        if isinstance(result, dict) and "payload" in result:
            payload = result["payload"]
            
            # Extraction du titre
            title = None
            for field in ["title", "subject", "name", "key", "id"]:
                if field in payload and payload[field]:
                    title = payload[field]
                    break
                    
            # Extraction de l'URL
            url = None
            for field in ["url", "link", "href"]:
                if field in payload and payload[field]:
                    url = payload[field]
                    break
                    
            # Extraction du texte
            text = payload.get("text", "")
            if not text:
                for field in ["content", "description", "body", "message"]:
                    if field in payload and payload[field]:
                        text = payload[field]
                        break
                        
            # Formater pour Slack
            formatted = f"*{title or 'Résultat'}*\n"
            if url:
                formatted += f"<{url}|Lien>\n"
            if text:
                # Limiter la taille du texte
                max_length = 300
                if len(text) > max_length:
                    text = text[:max_length] + "..."
                formatted += text
                
            return formatted
        
        return str(result)


# Instance singleton pour compatibilité
search_factory_adapter = SearchFactoryAdapter()

# Fonctions d'aide pour compatibilité
async def get_search_factory():
    """
    Récupère l'adaptateur de SearchClientFactory
    
    Returns:
        Instance de SearchFactoryAdapter
    """
    await search_factory_adapter.initialize()
    return search_factory_adapter
