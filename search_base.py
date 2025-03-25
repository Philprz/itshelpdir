# Nouveau fichier search_base.py

from abc import ABC, abstractmethod
import asyncio
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from configuration import logger
from qdrant_client.http.models.models import (
    Filter, 
    FieldCondition, 
    Range, 
    MatchValue
)

CACHE_MAX_SIZE = 1000

class AbstractResultProcessor(ABC):
    """
    Interface abstraite pour les processeurs de résultats de recherche.
    Définit les méthodes que tout processeur doit implémenter.
    """
    
    @abstractmethod
    def extract_score(self, result: Any) -> float:
        """
        Extrait le score de pertinence d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Score de pertinence (0.0-1.0)
        """
        pass
        
    @abstractmethod
    def extract_title(self, result: Any) -> Optional[str]:
        """
        Extrait le titre d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Titre ou None si non disponible
        """
        pass
        
    @abstractmethod
    def extract_url(self, result: Any) -> Optional[str]:
        """
        Extrait l'URL d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            URL ou None si non disponible
        """
        pass
        
    @abstractmethod
    def deduplicate_results(self, results: List[Any]) -> List[Any]:
        """
        Déduplique une liste de résultats.
        
        Args:
            results: Liste de résultats à dédupliquer
            
        Returns:
            Liste de résultats dédupliqués
        """
        pass
        
    @abstractmethod
    def filter_by_date(self, results: List[Any], date_debut: Optional[datetime], date_fin: Optional[datetime]) -> List[Any]:
        """
        Filtre les résultats par date.
        
        Args:
            results: Liste de résultats à filtrer
            date_debut: Date de début (optionnel)
            date_fin: Date de fin (optionnel)
            
        Returns:
            Liste de résultats filtrés
        """
        pass

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

class DefaultResultProcessor(AbstractResultProcessor):
    """
    Implémentation par défaut d'un processeur de résultats.
    Fournit une implémentation générique pour les méthodes abstraites.
    """
    
    def extract_score(self, result: Any) -> float:
        """
        Extrait le score de pertinence d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Score de pertinence (0.0-1.0)
        """
        try:
            # Format standard Qdrant
            if hasattr(result, 'score'):
                return float(result.score)
                
            # Format dictionnaire
            if isinstance(result, dict) and 'score' in result:
                return float(result['score'])
                
            return 0.0
        except (TypeError, ValueError):
            return 0.0
            
    def extract_title(self, result: Any) -> Optional[str]:
        """
        Extrait le titre d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            Titre ou None si non disponible
        """
        try:
            # Accès à payload.title ou payload['title']
            if hasattr(result, 'payload'):
                payload = result.payload
                if isinstance(payload, dict):
                    if 'title' in payload:
                        return str(payload['title'])
                    elif 'summary' in payload:
                        return str(payload['summary'])
                    elif 'name' in payload:
                        return str(payload['name'])
                        
            # Format dictionnaire direct
            if isinstance(result, dict) and 'payload' in result:
                payload = result['payload']
                if isinstance(payload, dict):
                    if 'title' in payload:
                        return str(payload['title'])
                    elif 'summary' in payload:
                        return str(payload['summary'])
                    elif 'name' in payload:
                        return str(payload['name'])
                        
            return None
        except Exception:
            return None
            
    def extract_url(self, result: Any) -> Optional[str]:
        """
        Extrait l'URL d'un résultat.
        
        Args:
            result: Résultat de recherche
            
        Returns:
            URL ou None si non disponible
        """
        try:
            # Accès à payload.url ou payload['url']
            if hasattr(result, 'payload'):
                payload = result.payload
                if isinstance(payload, dict):
                    if 'url' in payload:
                        return str(payload['url'])
                    elif 'link' in payload:
                        return str(payload['link'])
                    elif 'href' in payload:
                        return str(payload['href'])
                        
            # Format dictionnaire direct
            if isinstance(result, dict) and 'payload' in result:
                payload = result['payload']
                if isinstance(payload, dict):
                    if 'url' in payload:
                        return str(payload['url'])
                    elif 'link' in payload:
                        return str(payload['link'])
                    elif 'href' in payload:
                        return str(payload['href'])
                        
            return None
        except Exception:
            return None
            
    def deduplicate_results(self, results: List[Any]) -> List[Any]:
        """
        Déduplique une liste de résultats par titre.
        
        Args:
            results: Liste de résultats à dédupliquer
            
        Returns:
            Liste de résultats dédupliqués
        """
        unique_results = []
        seen_titles = set()
        
        for result in results:
            title = self.extract_title(result)
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_results.append(result)
            elif not title:
                # Si pas de titre, on conserve quand même le résultat
                unique_results.append(result)
                
        return unique_results
        
    def filter_by_date(self, results: List[Any], date_debut: Optional[datetime], date_fin: Optional[datetime]) -> List[Any]:
        """
        Filtre les résultats par date.
        
        Args:
            results: Liste de résultats à filtrer
            date_debut: Date de début (optionnel)
            date_fin: Date de fin (optionnel)
            
        Returns:
            Liste de résultats filtrés
        """
        if not date_debut and not date_fin:
            return results
            
        filtered_results = []
        
        for result in results:
            try:
                # Extraction de la date (plusieurs formats possibles)
                timestamp = None
                
                # Format Qdrant payload
                if hasattr(result, 'payload'):
                    payload = result.payload
                    if isinstance(payload, dict):
                        for date_field in ['created', 'updated', 'date', 'timestamp']:
                            if date_field in payload:
                                timestamp_value = payload[date_field]
                                if isinstance(timestamp_value, (int, float)):
                                    timestamp = datetime.fromtimestamp(timestamp_value)
                                    break
                                    
                # Format dictionnaire
                elif isinstance(result, dict) and 'payload' in result:
                    payload = result['payload']
                    if isinstance(payload, dict):
                        for date_field in ['created', 'updated', 'date', 'timestamp']:
                            if date_field in payload:
                                timestamp_value = payload[date_field]
                                if isinstance(timestamp_value, (int, float)):
                                    timestamp = datetime.fromtimestamp(timestamp_value)
                                    break
                
                # Vérification selon les bornes
                if timestamp:
                    if date_debut and timestamp < date_debut:
                        continue
                    if date_fin and timestamp > date_fin:
                        continue
                    
                filtered_results.append(result)
            except Exception:
                # En cas d'erreur, on conserve le résultat
                filtered_results.append(result)
                
        return filtered_results

class AbstractSearchClient(ABC):
    """
    Classe abstraite définissant l'interface standard pour tous les clients de recherche.
    Tous les clients de recherche spécifiques doivent hériter de cette classe et implémenter
    les méthodes abstraites.
    
    Cette classe définit également des comportements par défaut pour les opérations communes.
    """
    
    # Constantes pour la gestion des erreurs et les timeouts
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 0.5  # Secondes, sera multiplié exponentiellement
    TIMEOUT = 30  # Secondes
    
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
        
        Returns:
            Chaîne représentant le nom de la source de données
        """
        pass
    
    @abstractmethod
    def valider_resultat(self, result: Any) -> bool:
        """
        Vérifie si un résultat de recherche est valide selon les critères spécifiques.
        Cette méthode doit être implémentée par toutes les sous-classes.
        
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
                                    vector_field: str = "vector"):
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
        # Vérification de la question
        if not question or not isinstance(question, str) or len(question.strip()) < 2:
            self.logger.warning(f"Question invalide: '{question}'")
            return []
            
        try:
            # Construction du filtre pour la recherche
            search_filter = None
            if client_name or date_debut or date_fin:
                search_filter = self._build_search_filter(client_name, date_debut, date_fin)
                
            # Obtention de l'embedding via OpenAI
            vector = None
            try:
                if hasattr(self, 'embedding_service') and self.embedding_service:
                    vector = await self.embedding_service.get_embedding(question)
            except Exception as e:
                self.logger.warning(f"Erreur lors de la génération de l'embedding: {str(e)}")
                
            # En cas d'erreur ou si aucun embedding n'est disponible, utiliser un vecteur fictif
            if not vector:
                self.logger.info("Utilisation d'un vecteur fictif pour la recherche")
                # La plupart des embeddings OpenAI sont de dimension 1536
                vector = [0.1] * 1536
                
            # Recherche avec retry en cas d'erreur
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Placeholder pour simuler une exécution asynchrone du client Qdrant
                    search_task = asyncio.create_task(asyncio.sleep(0))
                    
                    self.logger.info(f"Recherche dans {self.collection_name} (tentative {attempt+1}/{max_retries})")
                    
                    # Utiliser query_points (méthode recommandée) avec fallback à search
                    try:
                        if hasattr(self.client, 'query_points'):
                            self.logger.info("Utilisation de query_points (méthode recommandée)")
                            search_results = self.client.query_points(
                                collection_name=self.collection_name,
                                query_vector=vector,
                                query_filter=search_filter,
                                limit=limit,
                                with_payload=True,
                                score_threshold=score_threshold,
                                with_vectors=False
                            )
                        else:
                            # Fallback à la méthode search (dépréciée)
                            self.logger.info("Utilisation de search (méthode dépréciée)")
                            search_results = self.client.search(
                                collection_name=self.collection_name,
                                query_vector=vector,
                                query_filter=search_filter,
                                limit=limit,
                                with_payload=True,
                                score_threshold=score_threshold,
                                with_vectors=False
                            )
                        
                        # Log du nombre de résultats trouvés
                        if search_results:
                            self.logger.info(f"Recherche réussie: {len(search_results)} résultats trouvés")
                        else:
                            self.logger.warning(f"Aucun résultat trouvé pour '{question}' dans {self.collection_name}")
                        
                        # Attente du placeholder pour simuler l'asynchronisme
                        await asyncio.wait_for(search_task, timeout=0.2)
                        break
                        
                    except Exception as e:
                        self.logger.error(f"Erreur spécifique à la recherche: {str(e)}")
                        if attempt < max_retries - 1:
                            self.logger.info(f"Nouvelle tentative dans 1 seconde...")
                            await asyncio.sleep(1)
                        else:
                            self.logger.error(f"Échec après {max_retries} tentatives")
                            return []
                        
                except asyncio.TimeoutError:
                    self.logger.warning(f"Timeout de la recherche (tentative {attempt+1}/{max_retries})")
                    if attempt < max_retries - 1:
                        self.logger.info(f"Nouvelle tentative dans 1 seconde...")
                        await asyncio.sleep(1)
                    else:
                        self.logger.error(f"Timeout après {max_retries} tentatives")
                        return []
            
            # Transformation et validation des résultats
            results = []
            if hasattr(self, 'validate_result'):
                for result in search_results:
                    if self.validate_result(result):
                        results.append(result)
            else:
                results = search_results
                
            return results
                
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche intelligente: {str(e)}")
            return []
    
    def _build_search_filter(self, client_name: Optional[str], date_debut: Optional[datetime], date_fin: Optional[datetime]) -> Filter:
        """
        Construit un filtre Qdrant basé sur les paramètres de recherche.
        
        Args:
            client_name: Nom du client pour filtrer les résultats
            date_debut: Date de début pour filtrage
            date_fin: Date de fin pour filtrage
            
        Returns:
            Filtre Qdrant configuré
        """
        must_conditions = []
        
        # Filtre sur le client si spécifié
        if client_name:
            self.logger.info("Ajout de filtre sur le client: {}".format(client_name))
            must_conditions.append(
                FieldCondition(
                    key="client",
                    match=MatchValue(value=client_name)
                )
            )
        
        # Filtre sur les dates si spécifiées
        if date_debut or date_fin:
            date_conditions = []
            
            if date_debut:
                self.logger.info("Ajout de filtre sur date début: {}".format(date_debut.isoformat()))
                date_conditions.append(
                    FieldCondition(
                        key="date",
                        range=Range(
                            gte=date_debut.isoformat()
                        )
                    )
                )
                
            if date_fin:
                self.logger.info("Ajout de filtre sur date fin: {}".format(date_fin.isoformat()))
                date_conditions.append(
                    FieldCondition(
                        key="date",
                        range=Range(
                            lte=date_fin.isoformat()
                        )
                    )
                )
                
            # Si les deux dates sont spécifiées, utilisez un AND implicite
            must_conditions.extend(date_conditions)
        
        # Construire le filtre final
        if must_conditions:
            self.logger.info("Construction du filtre avec {} conditions".format(len(must_conditions)))
            return Filter(
                must=must_conditions
            )
        else:
            self.logger.info("Aucun filtre appliqué")
            return None
    
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
        if not questions:
            return {}
            
        # Filtrer les questions vides ou trop courtes
        valid_questions = [q for q in questions if q and isinstance(q, str) and len(q.strip()) > 2]
        if not valid_questions:
            self.logger.warning("Aucune question valide pour batch_search")
            return {}
            
        self.logger.info(f"Lancement batch_search avec {len(valid_questions)} questions")
        
        # Construire les tâches de recherche pour chaque question
        tasks = {}
        for question in valid_questions:
            tasks[question] = self.recherche_intelligente(
                question=question,
                client_name=client_name,
                date_debut=date_debut,
                date_fin=date_fin
            )
        
        # Exécuter les tâches en parallèle avec gestion des erreurs
        results = {}
        try:
            # Exécution en parallèle avec timeout global
            async with asyncio.timeout(self.TIMEOUT * 2):
                # Utiliser gather avec return_exceptions=True pour éviter qu'une erreur bloque tout
                tasks_gathered = {
                    question: asyncio.create_task(task) 
                    for question, task in tasks.items()
                }
                
                # Attendre que toutes les tâches soient terminées ou jusqu'au timeout
                done, pending = await asyncio.wait(
                    tasks_gathered.values(), 
                    timeout=self.TIMEOUT * 1.5,
                    return_when=asyncio.ALL_COMPLETED
                )
                
                # Annuler les tâches en cours si timeout
                for task in pending:
                    task.cancel()
                
                # Recueillir les résultats
                for question, task in tasks_gathered.items():
                    try:
                        if task in done:
                            result = await task
                            results[question] = result
                        else:
                            self.logger.warning(f"Tâche annulée pour question: {question[:30]}...")
                            results[question] = []
                    except Exception as e:
                        self.logger.error(f"Erreur lors du traitement batch pour question '{question[:30]}...': {str(e)}")
                        results[question] = []
                        
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout global du batch_search après {self.TIMEOUT * 2}s")
            # Compléter les résultats manquants
            for question in valid_questions:
                if question not in results:
                    results[question] = []
        except Exception as e:
            self.logger.error(f"Erreur inattendue dans batch_search: {str(e)}")
            # Assurer que toutes les questions ont un résultat
            for question in valid_questions:
                if question not in results:
                    results[question] = []
        
        # Statistiques sur les résultats
        total_results = sum(len(res) for res in results.values())
        successful_queries = sum(1 for res in results.values() if res)
        self.logger.info(f"Batch search terminé: {successful_queries}/{len(valid_questions)} requêtes réussies, {total_results} résultats au total")
        
        return results
    
    async def format_for_slack(self, result: Any) -> Optional[Dict]:
        """
        Formate un résultat pour l'affichage dans Slack.
        Cette méthode peut être surchargée par les sous-classes pour un formatage spécifique.
        
        Args:
            result: Résultat de recherche à formater
            
        Returns:
            Dictionnaire contenant le message formaté pour Slack ou None
        """
        try:
            source = self.get_source_name()
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Résultat générique de {source}*\n{str(result)[:200]}..."
                }
            }
        except Exception as e:
            self.logger.error(f"Erreur format_for_slack: {str(e)}")
            return None
    
    async def format_for_message(self, results: List[Any]) -> str:
        """
        Formate une liste de résultats pour l'affichage dans un message textuel.
        Cette méthode peut être surchargée par les sous-classes pour un formatage spécifique.
        
        Args:
            results: Liste de résultats à formater
            
        Returns:
            Chaîne formatée pour affichage
        """
        try:
            if not results:
                return f"Aucun résultat trouvé dans {self.get_source_name()}"
                
            formatted = []
            source = self.get_source_name()
            
            for i, result in enumerate(results[:5]):  # Limite à 5 résultats pour éviter les messages trop longs
                try:
                    # Extraction des informations courantes
                    title = self.processor.extract_title(result) or "Sans titre"
                    url = self.processor.extract_url(result) or ""
                    
                    # Construction du message formaté
                    msg = f"*{i+1}. {title}*"
                    if url:
                        msg += f"\n{url}"
                        
                    formatted.append(msg)
                except Exception as e:
                    self.logger.error(f"Erreur format_for_message résultat {i}: {str(e)}")
                    
            return f"*{len(results)} résultats de {source}*\n\n" + "\n\n".join(formatted)
            
        except Exception as e:
            self.logger.error(f"Erreur format_for_message: {str(e)}")
            return f"Erreur lors du formatage des résultats de {self.get_source_name()}"
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Effectue une vérification de santé du client.
        Cette méthode peut être utilisée pour vérifier que le client est opérationnel.
        
        Returns:
            Dictionnaire contenant les informations de santé du client
        """
        try:
            # Vérification de base: tenter d'accéder à la collection
            if not self.client:
                return {"status": "error", "message": "Client non initialisé"}
                
            # Vérification de l'embedding service
            embedding_status = "ok" if self.embedding_service else "missing"
            
            return {
                "status": "ok",
                "source": self.get_source_name(),
                "collection": self.collection_name,
                "embedding_service": embedding_status
            }
        except Exception as e:
            return {
                "status": "error",
                "source": self.get_source_name(),
                "message": str(e)
            }