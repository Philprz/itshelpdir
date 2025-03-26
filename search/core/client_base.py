"""
Module client_base - Classes abstraites et génériques pour les clients de recherche
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, TypeVar, Generic
from datetime import datetime

from search.core.result_processor import AbstractResultProcessor, DefaultResultProcessor
from search.utils.filter_builder import build_qdrant_filter

# Type générique pour les résultats de recherche
T = TypeVar('T')
R = TypeVar('R')

class AbstractSearchClient(ABC, Generic[T, R]):
    """
    Classe abstraite définissant l'interface standard pour tous les clients de recherche.
    Tous les clients de recherche spécifiques doivent hériter de cette classe et implémenter
    les méthodes abstraites.
    
    Cette classe définit également des comportements par défaut pour les opérations communes.
    
    Génériques:
        T: Type des résultats bruts retournés par le backend de recherche
        R: Type des résultats traités retournés aux appelants
    """
    
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 0.5
    TIMEOUT = 30
    
    def __init__(self, 
                collection_name: str, 
                qdrant_client: Any,  # Type évite l'import circulaire
                embedding_service: Any = None,  # Type évite l'import circulaire
                translation_service: Any = None,  # Type évite l'import circulaire
                processor: Optional[AbstractResultProcessor] = None):
        """
        Initialise un client de recherche avec les composants nécessaires.
        
        Args:
            collection_name: Nom de la collection Qdrant
            qdrant_client: Client Qdrant pour exécuter les requêtes vectorielles
            embedding_service: Service pour générer des embeddings (optional)
            translation_service: Service pour la traduction (optional)
            processor: Processeur personnalisé pour les résultats (optional)
        """
        self.collection_name = collection_name
        self.client = qdrant_client
        self.embedding_service = embedding_service
        self.translation_service = translation_service
        self.processor = processor or DefaultResultProcessor()
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
    
    @abstractmethod
    def get_source_name(self) -> str:
        """
        Renvoie le nom de la source de données (ex: 'JIRA', 'ZENDESK').
        Cette méthode doit être implémentée par toutes les sous-classes.
        
        Le nom retourné doit être CONSTANT pour chaque type de client et 
        correspondre au nom de la collection ou au type de données recherchées.
        
        Returns:
            Chaîne représentant le nom de la source de données
        """
        pass
    
    @abstractmethod
    def valider_resultat(self, result: T) -> bool:
        """
        Vérifie si un résultat de recherche est valide selon les critères spécifiques.
        Cette méthode doit être implémentée par toutes les sous-classes.
        
        Implémentation recommandée:
        1. Vérifier que le résultat contient les champs requis (payload, score, etc.)
        2. Vérifier que la payload contient les clés nécessaires (title, content, etc.)
        3. Vérifier que les valeurs sont du type attendu et non vides
        
        Args:
            result: Résultat de recherche à valider
            
        Returns:
            True si le résultat est valide, False sinon
        """
        pass
    
    async def recherche_intelligente(self, 
                                    question: str, 
                                    client_name: Optional[str] = None, 
                                    date_debut: Optional[datetime] = None, 
                                    date_fin: Optional[datetime] = None,
                                    limit: int = 10,
                                    score_threshold: float = 0.0,
                                    vector_field: str = "vector") -> List[R]:
        """
        Méthode commune de recherche intelligente pour toutes les sources.
        Implémente un comportement standard basé sur la recherche de similarité vectorielle.
        
        Args:
            question: Question ou texte à rechercher
            client_name: Nom du client pour filtrer les résultats (optionnel)
            date_debut: Date de début pour filtrage (optionnel)
            date_fin: Date de fin pour filtrage (optionnel)
            limit: Nombre maximum de résultats à retourner
            score_threshold: Score minimum pour considérer un résultat (0.0-1.0)
            vector_field: Nom du champ de vecteur à utiliser pour la recherche
            
        Returns:
            Liste des résultats pertinents
        """
        try:
            self.logger.info(f"Recherche intelligente dans {self.collection_name}: '{question[:50]}...'")
            self.logger.debug(f"Paramètres: client={client_name}, limit={limit}, threshold={score_threshold}")
            
            # Génération de l'embedding pour la recherche vectorielle
            if not self.embedding_service:
                self.logger.warning("Pas de service d'embedding disponible, recherche impossible")
                return []
                
            # Obtenir l'embedding de la question
            vector = await self.embedding_service.get_embedding(question)
            if not vector:
                self.logger.warning("Impossible d'obtenir un embedding pour la question")
                return []
                
            # Construction du filtre de recherche
            search_filter = self._build_search_filter(client_name, date_debut, date_fin)
            
            # Exécution de la recherche avec retry
            for attempt in range(self.MAX_RETRIES):
                try:
                    # Utilisation de search ou query_points selon la méthode disponible
                    search_method = getattr(self.client, 'query_points', None) or self.client.search
                    
                    search_results = search_method(
                        collection_name=self.collection_name,
                        query_vector=vector,
                        query_filter=search_filter,
                        limit=min(limit * 2, 100),  # Récupérer plus pour avoir assez après filtrage
                        score_threshold=score_threshold,
                        with_payload=True,
                        with_vectors=False
                    )
                    
                    # Traitement des résultats
                    if not search_results:
                        self.logger.info(f"Aucun résultat trouvé dans {self.collection_name}")
                        return []
                        
                    # Valider et filtrer les résultats
                    valid_results = []
                    for result in search_results:
                        if hasattr(result, 'score') and float(result.score) < score_threshold:
                            continue
                            
                        # Validation spécifique selon le type de client
                        if self.valider_resultat(result):
                            valid_results.append(result)
                        
                    # Déduplication et limite finale
                    if valid_results:
                        deduplicated = self.processor.deduplicate_results(valid_results)
                        final_results = deduplicated[:limit]
                        self.logger.info(f"Résultats après traitement: {len(final_results)}/{len(search_results)}")
                        return final_results
                    else:
                        self.logger.info("Aucun résultat valide après filtrage")
                        return []
                        
                except Exception as e:
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                        self.logger.warning(f"Erreur recherche (tentative {attempt+1}/{self.MAX_RETRIES}): {str(e)}")
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(f"Échec final recherche: {str(e)}")
                        raise
                        
        except Exception as e:
            self.logger.error(f"Erreur dans recherche_intelligente: {str(e)}")
            return []
    
    def _build_search_filter(self, client_name: Optional[str], date_debut: Optional[datetime], date_fin: Optional[datetime]):
        """
        Construit un filtre Qdrant basé sur les paramètres de recherche.
        
        Args:
            client_name: Nom du client pour filtrer les résultats
            date_debut: Date de début pour filtrage
            date_fin: Date de fin pour filtrage
            
        Returns:
            Filtre Qdrant configuré
        """
        # Utiliser l'utilitaire commun pour construire le filtre
        return build_qdrant_filter(client_name, date_debut, date_fin)
    
    async def batch_search(self, questions: List[str], client_name: Optional[Dict] = None,
                      date_debut: Optional[datetime] = None, 
                      date_fin: Optional[datetime] = None):
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
        if not questions:
            return {}
            
        # Lancer toutes les recherches en parallèle
        tasks = []
        for question in questions:
            task = asyncio.create_task(
                self.recherche_intelligente(
                    question=question,
                    client_name=client_name,
                    date_debut=date_debut,
                    date_fin=date_fin
                )
            )
            tasks.append((question, task))
            
        # Attendre et collecter les résultats
        results = {}
        for question, task in tasks:
            try:
                search_results = await task
                results[question] = search_results
            except Exception as e:
                self.logger.error(f"Erreur recherche batch pour '{question}': {str(e)}")
                results[question] = []
                
        return results
    
    async def format_for_slack(self, result: T):
        """
        Formate un résultat pour l'affichage dans Slack.
        Cette méthode peut être surchargée par les sous-classes pour un formatage spécifique.
        
        Args:
            result: Résultat de recherche à formater
            
        Returns:
            Dictionnaire contenant le message formaté pour Slack ou None
        """
        payload = self.processor.extract_payload(result)
        if not payload:
            return None
            
        source = self.get_source_name()
        score = self.processor.extract_score(result)
        score_percent = round(score * 100)
        
        # Créer un message par défaut basé sur les champs disponibles
        title = payload.get('title', payload.get('summary', 'Sans titre'))
        content = payload.get('content', payload.get('text', 'Pas de contenu'))
        content = (content[:197] + "...") if len(content) > 200 else content
        
        message = (
            f"*{source}* - {title}\n"
            f"Score: {score_percent}%\n"
            f"Description: {content}"
        )
            
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message
            }
        }
    
    async def format_for_message(self, results: List[T]):
        """
        Formate une liste de résultats pour l'affichage dans un message textuel.
        Cette méthode peut être surchargée par les sous-classes pour un formatage spécifique.
        
        Args:
            results: Liste de résultats à formater
            
        Returns:
            Chaîne formatée pour affichage
        """
        if not results:
            return "Aucun résultat trouvé."
            
        source = self.get_source_name()
        formatted_results = []
        
        for i, result in enumerate(results[:5], 1):
            payload = self.processor.extract_payload(result)
            score = self.processor.extract_score(result)
            
            title = payload.get('title', payload.get('summary', 'Sans titre'))
            title = title[:50] + '...' if len(title) > 50 else title
            
            formatted_results.append(f"{i}. {title} ({int(score*100)}%)")
            
        header = f"Résultats de la recherche dans {source}:"
        return header + "\n" + "\n".join(formatted_results)
    
    async def health_check(self):
        """
        Effectue une vérification de santé du client.
        Cette méthode peut être utilisée pour vérifier que le client est opérationnel.
        
        Returns:
            Dictionnaire contenant les informations de santé du client
        """
        try:
            # Vérifier que la connexion au client est active
            is_connected = self.client is not None
            
            # Vérifier que le service d'embedding est disponible
            has_embedding = self.embedding_service is not None
            embedding_ok = False
            if has_embedding:
                try:
                    # Test simple d'embedding
                    vector = await self.embedding_service.get_embedding("test")
                    embedding_ok = vector is not None and len(vector) > 0
                except Exception:
                    embedding_ok = False
            
            return {
                "name": self.get_source_name(),
                "collection": self.collection_name,
                "connected": is_connected,
                "has_embedding_service": has_embedding,
                "embedding_service_ok": embedding_ok,
                "status": "healthy" if (is_connected and embedding_ok) else "degraded"
            }
        except Exception as e:
            self.logger.error(f"Erreur health_check: {str(e)}")
            return {
                "name": self.get_source_name(),
                "status": "error",
                "error": str(e)
            }


class GenericSearchClient(AbstractSearchClient[Any, Any]):
    """
    Classe générique servant de pont entre AbstractSearchClient et les clients spécifiques.
    Implémente les méthodes communes à tous les clients de recherche.
    
    Cette classe utilise les types Any pour les résultats, mais les clients spécifiques
    devraient définir des types plus précis pour une meilleure vérification de type.
    """
    
    def get_source_name(self) -> str:
        """
        Implémentation par défaut du nom de source.
        
        Returns:
            Nom de la source sous forme de chaîne
        """
        return f"GENERIC_{self.collection_name.upper()}"
    
    def valider_resultat(self, result: Any) -> bool:
        """
        Validation de base d'un résultat.
        Cette méthode vérifie les conditions minimales qu'un résultat doit satisfaire.
        
        Args:
            result: Résultat à valider
            
        Returns:
            True si le résultat satisfait les critères de base, False sinon
        """
        if not result:
            return False
            
        # Vérifier que le résultat a un score
        if not hasattr(result, 'score'):
            return False
            
        # Vérifier que le résultat a un payload
        if not hasattr(result, 'payload') or not result.payload:
            return False
            
        return True
    
    async def recherche_similaire(self, query_vector, limit=5) -> List[Any]:
        """
        Méthode de recherche par similarité vectorielle simple.
        
        Args:
            query_vector: Vecteur d'embedding pour la recherche
            limit: Nombre maximum de résultats à retourner
            
        Returns:
            Liste des résultats similaires
        """
        try:
            self.logger.info(f"Recherche similaire dans {self.collection_name}")
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            return resultats
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche similaire: {str(e)}")
            return []
    
    async def recherche_avec_filtres(self, query_vector, filtres: dict, limit=5) -> List[Any]:
        """
        Méthode de recherche par similarité vectorielle avec filtres supplémentaires.
        
        Args:
            query_vector: Vecteur d'embedding pour la recherche
            filtres: Dictionnaire des filtres à appliquer
            limit: Nombre maximum de résultats à retourner
            
        Returns:
            Liste des résultats filtrés
        """
        try:
            self.logger.info(f"Recherche avec filtres: {filtres}")
            # Construire le filtre Qdrant si la méthode existe
            filter_obj = build_qdrant_filter(filtres.get('client_name'), 
                                           filtres.get('date_debut'), 
                                           filtres.get('date_fin'))
            
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=filter_obj,
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            self.logger.info(f"Résultats trouvés: {len(resultats)}")
            # Filtrer par score si nécessaire (peut être surchargé par les sous-classes)
            min_score = 0.45  # Score minimum par défaut
            return [r for r in resultats if hasattr(r, 'score') and r.score >= min_score]
        except Exception as e:
            self.logger.error(f"Erreur recherche filtrée: {str(e)}")
            return []
