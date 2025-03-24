# Nouveau fichier search_base.py

from abc import ABC, abstractmethod
import asyncio
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from configuration import logger
from embedding_service import EmbeddingService
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, Range
from collections import OrderedDict

CACHE_MAX_SIZE = 1000
class SearchResultProcessor:
    """
    Classe utilitaire pour le traitement des résultats de recherche.
    Centralise les fonctions communes à tous les types de recherche.
    """
    
    @staticmethod
    def extract_payload(result: Any) -> Dict:
        """Extrait le payload du résultat de manière sécurisée."""
        if isinstance(result, dict):
            return result.get('payload', {}) if isinstance(result.get('payload'), dict) else result
        
        if not hasattr(result, 'payload'):
            return {}
            
        return result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})
    
    @staticmethod
    def extract_score(result: Any) -> float:
        """Extrait le score du résultat de manière sécurisée."""
        if isinstance(result, dict):
            return float(result.get('score', 0.0))
        return float(getattr(result, 'score', 0.0))
    
    @staticmethod
    def normalize_date(date_value: Any) -> Optional[datetime]:
        """Normalise une date avec gestion des différents formats."""
        if not date_value:
            return None
            
        try:
            if isinstance(date_value, (int, float)):
                return datetime.fromtimestamp(date_value, tz=timezone.utc)
                
            if isinstance(date_value, str):
                # Tentative avec isoformat
                try:
                    return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                except ValueError:
                    # Tentative avec différents formats
                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y/%m/%d", "%Y%m%d"]:
                        try:
                            dt = datetime.strptime(date_value, fmt)
                            return dt.replace(tzinfo=timezone.utc)
                        except ValueError:
                            continue
            
            return None
            
        except Exception as e:
            logger.warning(f"Erreur normalisation date: {str(e)}")
            return None
    
    @staticmethod
    def content_hash(content: str, length: int = 500) -> str:
        """Génère un hash du contenu pour la déduplication."""
        return hashlib.md5(str(content)[:length].encode('utf-8', errors='ignore')).hexdigest()
    
    @classmethod
    def deduplicate_results(cls, results: List[Any], prioritize_score: bool = True) -> List[Any]:
        """
        Déduplique les résultats en se basant sur le contenu.
        Conserve l'élément avec le meilleur score pour chaque contenu unique.
        """
        seen_hashes = {}
        
        for result in results:
            payload = cls.extract_payload(result)
            score = cls.extract_score(result)
            
            content = payload.get('content', '') or payload.get('text', '')
            content_hash = cls.content_hash(content)
            
            if content_hash not in seen_hashes or (prioritize_score and score > cls.extract_score(seen_hashes[content_hash])):
                seen_hashes[content_hash] = result
                
        return list(seen_hashes.values())
    
    @classmethod
    def filter_by_date(cls, results: List[Any], date_debut: Optional[datetime], date_fin: Optional[datetime]) -> List[Any]:
        """Filtre les résultats par date."""
        if not date_debut and not date_fin:
            return results
            
        filtered = []
        
        for result in results:
            payload = cls.extract_payload(result)
            
            # Recherche dans plusieurs champs de date possibles
            for date_field in ['created', 'last_updated', 'updated']:
                date_value = payload.get(date_field)
                if date_value:
                    created_date = cls.normalize_date(date_value)
                    if created_date:
                        # Vérification des bornes
                        if date_debut and created_date < date_debut:
                            break
                        if date_fin and created_date > date_fin:
                            break
                        
                        # Stockage de la date normalisée pour tri ultérieur
                        payload[f'_normalized_{date_field}'] = created_date
                        filtered.append(result)
                        break
            else:
                # Pas de date trouvée, on conserve par défaut
                filtered.append(result)
                
        return filtered

class AbstractSearchClient(ABC):
    """
    Classe abstraite définissant l'interface commune à tous les clients de recherche.
    Intègre les fonctionnalités de BaseQdrantSearch.
    """
    
    def __init__(self, collection_name: str, qdrant_client: QdrantClient, embedding_service: EmbeddingService):
        self.collection_name = collection_name
        self.client = qdrant_client
        self.embedding_service = embedding_service
        self.logger = logging.getLogger(f'ITS_HELP.search.{collection_name.lower()}')
        self.processor = SearchResultProcessor()
        
        # Intégration des caches de BaseQdrantSearch
        self._embedding_cache = OrderedDict()
        self.CACHE_ENABLED = True
        self.MAX_RETRIES = 3
        self.RETRY_BASE_DELAY = 2
        self.TIMEOUT = 15
        
    # Méthodes de BaseQdrantSearch importées
    def _get_from_cache(self, key: str) -> Optional[List[float]]:
        """Récupère un embedding du cache."""
        return self._embedding_cache.get(key, None)

    def _add_to_cache(self, key: str, vector: List[float]):
        """Ajoute un embedding au cache avec une suppression optimisée."""
        if len(self._embedding_cache) >= self.CACHE_MAX_SIZE:
            self._embedding_cache.popitem(last=False)  # Suppression FIFO efficace
        self._embedding_cache[key] = vector
        
    @abstractmethod
    async def format_for_slack(self, result: Any) -> Dict:
        """Formate un résultat pour affichage dans Slack."""
        pass
        
    @abstractmethod
    def valider_resultat(self, result: Any) -> bool:
        """Valide qu'un résultat est exploitable."""
        pass
    
    async def recherche_intelligente(self, 
                                    question: str, 
                                    client_name: Optional[Dict] = None,
                                    date_debut: Optional[datetime] = None, 
                                    date_fin: Optional[datetime] = None) -> List[Any]:
        """
        Méthode commune de recherche intelligente pour toutes les sources.
        
        Args:
            question: Question ou texte à rechercher
            client_name: Informations sur le client (optionnel)
            date_debut: Date de début pour filtrage (optionnel)
            date_fin: Date de fin pour filtrage (optionnel)
            
        Returns:
            Liste des résultats pertinents
        """
        try:
            self.logger.info(f"Recherche: {question[:50]}...")
            
            # 1. Obtention du vecteur d'embedding
            vector = await self.embedding_service.get_embedding(question)
            if not vector:
                self.logger.error("Échec génération embedding")
                return []
                
            # 2. Construction du filtre
            query_filter = self._build_filter(client_name, date_debut, date_fin)
            
            # 3. Exécution de la recherche avec timeout
            async with asyncio.timeout(30):
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=vector,
                    query_filter=query_filter,
                    limit=50  # Limite élevée initiale pour post-traitement
                )
                
                if not results:
                    self.logger.info("Aucun résultat")
                    return []
                    
                # 4. Filtrage par score et validation
                min_score = 0.45
                valid_results = [r for r in results if self.processor.extract_score(r) >= min_score and self.valider_resultat(r)]
                
                # 5. Déduplication
                deduplicated = self.processor.deduplicate_results(valid_results)
                
                # 6. Filtrage par date
                date_filtered = self.processor.filter_by_date(deduplicated, date_debut, date_fin)
                
                # 7. Tri final
                sorted_results = sorted(date_filtered, key=lambda x: -self.processor.extract_score(x))
                
                # 8. Limitation du nombre de résultats
                final_results = sorted_results[:3]
                
                self.logger.info(f"Recherche terminée: {len(final_results)}/{len(results)} résultats pertinents")
                return final_results
                
        except asyncio.TimeoutError:
            self.logger.error("Timeout de la recherche")
            return []
        except Exception as e:
            self.logger.error(f"Erreur recherche: {str(e)}")
            return []
    
    def _build_filter(self, client_name: Optional[Dict], date_debut: Optional[datetime], date_fin: Optional[datetime]) -> Filter:
        """
        Construit un filtre Qdrant basé sur les paramètres de recherche.
        
        Args:
            client_name: Informations sur le client
            date_debut: Date de début pour filtrage
            date_fin: Date de fin pour filtrage
            
        Returns:
            Filtre Qdrant configuré
        """
        must_conditions = []
        
        # Filtre par client
        if client_name and not client_name.get("ambiguous"):
            client_value = client_name.get("source", "")
            if client_value:
                must_conditions.append(
                    FieldCondition(
                        key="client",
                        match=MatchValue(value=str(client_value))
                    )
                )
                
        # Filtres de date
        if date_debut or date_fin:
            date_range = Range()
            
            if date_debut:
                date_range.gte = int(date_debut.timestamp())
                
            if date_fin:
                date_range.lte = int(date_fin.timestamp())
                
            must_conditions.append(
                FieldCondition(
                    key="created",
                    range=date_range
                )
            )
            
        return Filter(must=must_conditions) if must_conditions else Filter()
    async def batch_search(self, questions: List[str], client_name: Optional[Dict] = None,
                      date_debut: Optional[datetime] = None, 
                      date_fin: Optional[datetime] = None) -> Dict[str, List[Any]]:
        """
        Exécute plusieurs recherches en parallèle pour optimiser les performances.
        
        Args:
            questions: Liste de questions à rechercher
            client_name: Informations sur le client
            date_debut: Date de début pour filtrage
            date_fin: Date de fin pour filtrage
            
        Returns:
            Dictionnaire {question: résultats}
        """
        # Construction d'une tâche par question
        async def search_task(question):
            return question, await self.recherche_intelligente(question, client_name, date_debut, date_fin)
            
        # Exécution parallèle des recherches
        tasks = [search_task(q) for q in questions]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Traitement des résultats
        output = {}
        for i, (question, result) in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Erreur recherche batch #{i}: {str(result)}")
                output[question] = []
            else:
                output[question] = result
                
        return output