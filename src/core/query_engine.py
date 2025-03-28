"""
Module query_engine.py - Analyse et recherche à travers différentes sources

Ce module implémente le moteur de requête qui analyse les questions utilisateur
et coordonne les recherches à travers les différentes sources de données (Jira, 
Zendesk, Confluence, NetSuite, etc.) en utilisant les adaptateurs appropriés.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Union, Set
from dataclasses import dataclass, field

from src.adapters.vector_stores.factory import get_vector_store
from src.adapters.embeddings.factory import get_embedding_service
from src.adapters.llm.factory import get_llm_adapter

# Configuration du logging
logger = logging.getLogger("ITS_HELP.core.query_engine")

@dataclass
class QueryResult:
    """Résultat d'une exécution de requête à travers les différentes sources"""
    
    query: str
    results: Dict[str, List[Dict[str, Any]]]
    total_results: int = 0
    execution_time: float = 0.0
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_results(self, source: str, results: List[Dict[str, Any]]):
        """
        Ajoute des résultats pour une source spécifique
        
        Args:
            source: Nom de la source
            results: Liste des résultats à ajouter
        """
        if source not in self.results:
            self.results[source] = []
            self.sources.append(source)
            
        self.results[source].extend(results)
        self.total_results += len(results)


class CircuitBreaker:
    """
    Implémentation du pattern Circuit Breaker pour protéger contre les erreurs répétées
    """
    
    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: int = 60):
        """
        Initialise le circuit breaker
        
        Args:
            name: Nom du circuit
            failure_threshold: Nombre d'échecs avant ouverture
            reset_timeout: Temps avant tentative de réinitialisation (secondes)
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.logger = logging.getLogger(f'ITS_HELP.circuit_breaker.{name}')
        
    def record_success(self):
        """Enregistre un succès et réinitialise le compteur d'échec"""
        self.failure_count = 0
        if self.state == "HALF-OPEN":
            self.state = "CLOSED"
            self.logger.info(f"Circuit {self.name} fermé après succès en état half-open")
            
    def record_failure(self):
        """Enregistre un échec et ouvre le circuit si le seuil est atteint"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                self.logger.warning(f"Circuit {self.name} ouvert après {self.failure_count} échecs")
                self.state = "OPEN"
            
    def can_execute(self):
        """Vérifie si une opération peut être exécutée selon l'état du circuit"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            # Vérifier si le temps de réinitialisation est écoulé
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF-OPEN"
                self.logger.info(f"Circuit {self.name} passé en half-open après {self.reset_timeout}s")
                return True
            return False
        elif self.state == "HALF-OPEN":
            return True
        return False
        
    def reset(self):
        """Réinitialise le circuit à son état fermé"""
        self.failure_count = 0
        self.state = "CLOSED"
        self.logger.info(f"Circuit {self.name} réinitialisé manuellement")
        
    def get_status(self):
        """Retourne l'état actuel du circuit pour monitoring"""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time,
            "threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout
        }


class QueryEngine:
    """
    Moteur de requête intelligent gérant l'analyse et la recherche
    
    Ce moteur:
    1. Analyse les questions utilisateur pour en extraire les intentions et entités
    2. Coordonne les recherches à travers les différentes sources
    3. Agrège et normalise les résultats
    4. Applique des transformations et filtrages intelligents
    """
    
    def __init__(self):
        """Initialise le moteur de requête"""
        self.vector_stores = {}
        self.embedding_service = None
        self.llm_adapter = None
        
        # Circuit breakers pour chaque source
        self.circuit_breakers = {}
        
        # Configuration
        self.parallel_execution = True
        self.max_concurrent = 6
        self.enable_circuit_breakers = True
        
        # Mapping des types de collections
        self.collection_types = {
            "jira": "jira",
            "zendesk": "zendesk",
            "confluence": "confluence",
            "netsuite": "netsuite", 
            "netsuite_dummies": "netsuite_dummies",
            "sap": "sap",
            "erp": "erp"
        }
        
        # État interne
        self._initialized = False
        self._semaphore = None
        
    async def initialize(self, parallel_execution: bool = True, 
                      max_concurrent: int = 6, 
                      enable_circuit_breakers: bool = True):
        """
        Initialise le moteur de requête et ses dépendances
        
        Args:
            parallel_execution: Activer l'exécution parallèle des recherches
            max_concurrent: Nombre maximum de recherches concurrentes
            enable_circuit_breakers: Activer les circuit breakers
        """
        if self._initialized:
            logger.debug("QueryEngine déjà initialisé, ignoré")
            return
            
        logger.info("Initialisation du QueryEngine...")
        start_time = time.time()
        
        # Mise à jour de la configuration
        self.parallel_execution = parallel_execution
        self.max_concurrent = max_concurrent
        self.enable_circuit_breakers = enable_circuit_breakers
        
        # Création du sémaphore pour limiter la concurrence
        self._semaphore = asyncio.Semaphore(max_concurrent)
        
        # Initialisation des services
        self.embedding_service = await get_embedding_service()
        self.llm_adapter = await get_llm_adapter()
        
        # Initialisation des vector stores pour chaque type de collection
        for collection_type in self.collection_types.values():
            circuit_name = f"vectorstore_{collection_type}"
            
            # Créer un circuit breaker pour cette source
            if enable_circuit_breakers:
                self.circuit_breakers[collection_type] = CircuitBreaker(
                    name=circuit_name,
                    failure_threshold=3,
                    reset_timeout=60
                )
            
            # Initialiser le vector store
            try:
                self.vector_stores[collection_type] = await get_vector_store(collection_type)
                logger.info(f"Vector store pour '{collection_type}' initialisé avec succès")
            except Exception as e:
                logger.error(f"Erreur lors de l'initialisation du vector store '{collection_type}': {str(e)}")
                # Le vector store sera initialisé à la demande
        
        self._initialized = True
        duration = time.time() - start_time
        logger.info(f"QueryEngine initialisé en {duration:.2f}s avec {len(self.vector_stores)} vector stores")
    
    async def execute_query(self, query: str, 
                         collections: Optional[List[str]] = None,
                         limit_per_collection: int = 10,
                         similarity_threshold: float = 0.6,
                         enable_semantic: bool = True,
                         timeout: float = 30.0,
                         metadata: Optional[Dict[str, Any]] = None) -> QueryResult:
        """
        Exécute une requête à travers les différentes sources
        
        Args:
            query: Texte de la requête
            collections: Liste des collections à interroger (None = toutes)
            limit_per_collection: Nombre max de résultats par collection
            similarity_threshold: Seuil minimal de similarité
            enable_semantic: Activer la recherche sémantique
            timeout: Timeout global pour l'exécution (secondes)
            metadata: Métadonnées additionnelles pour la requête
            
        Returns:
            QueryResult avec résultats agrégés
        """
        if not self._initialized:
            await self.initialize()
        
        # Préparation du résultat
        result = QueryResult(
            query=query,
            results={},
            metadata=metadata or {}
        )
        
        # Déterminer les collections à interroger
        target_collections = collections or list(self.collection_types.values())
        
        # Enrichir la requête avec l'analyse préliminaire (intentions, entités)
        enriched_query = await self._enrich_query(query)
        
        # Début du timing d'exécution
        start_time = time.time()
        
        # Exécution des recherches (parallèle ou séquentielle)
        if self.parallel_execution:
            async with asyncio.timeout(timeout):
                search_tasks = []
                
                for collection in target_collections:
                    if collection in self.vector_stores:
                        task = self._execute_collection_search(
                            enriched_query=enriched_query,
                            collection=collection,
                            limit=limit_per_collection,
                            similarity_threshold=similarity_threshold,
                            enable_semantic=enable_semantic
                        )
                        search_tasks.append(task)
                    else:
                        logger.warning(f"Collection '{collection}' non disponible, ignorée")
                
                # Attendre les résultats des recherches parallèles
                search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
                
                # Traiter les résultats et les exceptions
                for i, collection_result in enumerate(search_results):
                    collection = target_collections[i] if i < len(target_collections) else "unknown"
                    
                    if isinstance(collection_result, Exception):
                        logger.error(f"Erreur lors de la recherche dans '{collection}': {str(collection_result)}")
                        result.metadata[f"error_{collection}"] = str(collection_result)
                    elif collection_result:
                        source, results = collection_result
                        result.add_results(source, results)
        else:
            # Recherche séquentielle
            try:
                async with asyncio.timeout(timeout):
                    for collection in target_collections:
                        if collection not in self.vector_stores:
                            logger.warning(f"Collection '{collection}' non disponible, ignorée")
                            continue
                            
                        try:
                            collection_result = await self._execute_collection_search(
                                enriched_query=enriched_query,
                                collection=collection,
                                limit=limit_per_collection,
                                similarity_threshold=similarity_threshold,
                                enable_semantic=enable_semantic
                            )
                            
                            if collection_result:
                                source, results = collection_result
                                result.add_results(source, results)
                        except Exception as e:
                            logger.error(f"Erreur lors de la recherche dans '{collection}': {str(e)}")
                            result.metadata[f"error_{collection}"] = str(e)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout lors de l'exécution de la requête: {timeout}s écoulées")
                result.metadata["timeout"] = True
        
        # Finalisation du résultat
        result.execution_time = time.time() - start_time
        logger.info(f"Requête exécutée en {result.execution_time:.2f}s, {result.total_results} résultats trouvés")
        
        return result
    
    async def _enrich_query(self, query: str) -> Dict[str, Any]:
        """
        Enrichit la requête avec analyse préliminaire (intentions, entités)
        
        Args:
            query: Texte de la requête
            
        Returns:
            Dictionnaire avec requête enrichie
        """
        # Structure de base
        enriched = {
            "original": query,
            "normalized": query.lower().strip(),
            "entities": {},
            "intents": [],
            "embedding": None
        }
        
        # Génération de l'embedding si le service est disponible
        if self.embedding_service:
            try:
                enriched["embedding"] = await self.embedding_service.get_embedding(query)
            except Exception as e:
                logger.warning(f"Erreur lors de la génération de l'embedding: {str(e)}")
        
        # Analyse des intentions (à améliorer avec LLM si disponible)
        # Cette version simplifiée utilise des heuristiques basiques
        if "comment" in enriched["normalized"] or "pourquoi" in enriched["normalized"]:
            enriched["intents"].append("explain")
        
        if "où" in enriched["normalized"] or "comment trouver" in enriched["normalized"]:
            enriched["intents"].append("locate")
        
        if "quand" in enriched["normalized"] or "date" in enriched["normalized"]:
            enriched["intents"].append("temporal")
            
        # Si aucune intention n'est identifiée, utiliser l'intention générique
        if not enriched["intents"]:
            enriched["intents"].append("information")
            
        return enriched
    
    async def _execute_collection_search(self, enriched_query: Dict[str, Any], 
                                      collection: str,
                                      limit: int = 10,
                                      similarity_threshold: float = 0.6,
                                      enable_semantic: bool = True) -> Optional[tuple]:
        """
        Exécute une recherche sur une collection spécifique
        
        Args:
            enriched_query: Requête enrichie
            collection: Nom de la collection
            limit: Nombre max de résultats
            similarity_threshold: Seuil minimal de similarité
            enable_semantic: Activer la recherche sémantique
            
        Returns:
            Tuple (source, résultats) ou None en cas d'erreur
        """
        # Vérifier le circuit breaker si activé
        if self.enable_circuit_breakers and collection in self.circuit_breakers:
            circuit = self.circuit_breakers[collection]
            if not circuit.can_execute():
                logger.warning(f"Circuit '{collection}' ouvert, recherche ignorée")
                return None
        
        # Limiter le nombre de recherches concurrentes
        async with self._semaphore:
            try:
                vector_store = self.vector_stores.get(collection)
                if not vector_store:
                    # Tentative d'initialisation à la demande
                    try:
                        vector_store = await get_vector_store(collection)
                        self.vector_stores[collection] = vector_store
                    except Exception as e:
                        logger.error(f"Impossible d'initialiser le vector store '{collection}': {str(e)}")
                        if self.enable_circuit_breakers and collection in self.circuit_breakers:
                            self.circuit_breakers[collection].record_failure()
                        return None
                
                # Recherche en fonction du type de collection
                original_query = enriched_query["original"]
                embedding = enriched_query.get("embedding")
                
                # Exécuter la recherche avec le vector store approprié
                if enable_semantic and embedding:
                    search_results = await vector_store.similarity_search_with_score(
                        embedding=embedding,
                        limit=limit,
                        similarity_threshold=similarity_threshold
                    )
                else:
                    # Fallback vers recherche par texte si embedding non disponible
                    search_results = await vector_store.text_search(
                        query=original_query,
                        limit=limit
                    )
                
                # Normalisation des résultats
                normalized_results = []
                for result in search_results:
                    # Convertir le résultat au format standardisé
                    normalized = self._normalize_result(result, collection)
                    if normalized:
                        normalized_results.append(normalized)
                
                # Mise à jour du circuit breaker en cas de succès
                if self.enable_circuit_breakers and collection in self.circuit_breakers:
                    self.circuit_breakers[collection].record_success()
                
                return (collection, normalized_results)
                
            except Exception as e:
                logger.error(f"Erreur lors de la recherche dans '{collection}': {str(e)}")
                
                # Mise à jour du circuit breaker en cas d'échec
                if self.enable_circuit_breakers and collection in self.circuit_breakers:
                    self.circuit_breakers[collection].record_failure()
                
                return None
    
    def _normalize_result(self, result: Any, source: str) -> Dict[str, Any]:
        """
        Normalise un résultat de recherche dans un format standard
        
        Args:
            result: Résultat brut de la recherche
            source: Source du résultat
            
        Returns:
            Résultat normalisé au format standard
        """
        # Extraction du score et du contenu
        score = result[1] if isinstance(result, tuple) and len(result) > 1 else 0.0
        content = result[0] if isinstance(result, tuple) else result
        
        # Structure normalisée
        normalized = {
            "source": source,
            "score": float(score),
            "content": {},
            "metadata": {}
        }
        
        # Extraction du contenu selon le format
        if hasattr(content, "page_content") and hasattr(content, "metadata"):
            # Format compatible avec LangChain Document
            normalized["content"]["text"] = content.page_content
            normalized["metadata"] = content.metadata.copy() if content.metadata else {}
        elif isinstance(content, dict):
            # Format dict standard (payload, metadata)
            if "payload" in content and isinstance(content["payload"], dict):
                normalized["content"] = content["payload"]
            else:
                # Utilisation directe du dictionnaire
                keys_to_exclude = {"score", "vector", "id", "metadata"}
                normalized["content"] = {k: v for k, v in content.items() if k not in keys_to_exclude}
            
            # Récupération des métadonnées
            if "metadata" in content and isinstance(content["metadata"], dict):
                normalized["metadata"] = content["metadata"].copy()
        else:
            # Tentative de conversion générique
            normalized["content"]["text"] = str(content)
        
        # Extraction du titre
        title_fields = ["title", "subject", "name", "key", "id"]
        for field in title_fields:
            if field in normalized["content"]:
                normalized["metadata"]["title"] = normalized["content"][field]
                break
        
        # Extraction de l'URL
        url_fields = ["url", "link", "href"]
        for field in url_fields:
            if field in normalized["content"]:
                normalized["metadata"]["url"] = normalized["content"][field]
                break
            elif field in normalized["metadata"]:
                normalized["metadata"]["url"] = normalized["metadata"][field]
                break
        
        return normalized
    
    def get_status(self) -> Dict[str, Any]:
        """
        Renvoie l'état actuel du moteur de requête
        
        Returns:
            Dictionnaire avec les informations d'état
        """
        status = {
            "initialized": self._initialized,
            "parallel_execution": self.parallel_execution,
            "max_concurrent": self.max_concurrent,
            "enable_circuit_breakers": self.enable_circuit_breakers,
            "vector_stores": list(self.vector_stores.keys()),
            "circuit_breakers": {k: v.get_status() for k, v in self.circuit_breakers.items()} if self.circuit_breakers else {}
        }
        
        return status
    
    async def shutdown(self):
        """Arrête proprement le moteur de requête et ses ressources"""
        logger.info("Arrêt du QueryEngine...")
        
        # Fermeture des vector stores
        for collection, vector_store in self.vector_stores.items():
            if hasattr(vector_store, 'close'):
                await vector_store.close()
                
        logger.info("QueryEngine arrêté avec succès")
