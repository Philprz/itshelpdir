# qdrant_jira.py

import os
import re
import json
import logging
import asyncio
import hashlib
import time

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, Range

from datetime import datetime, timezone
from openai import OpenAI
from functools import lru_cache
from collections import OrderedDict
from sqlalchemy import Column, String, Integer, func, select
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from typing import Optional, Union, Dict, List, Any, Tuple

from configuration import MAX_SEARCH_RESULTS
from base_de_donnees import normalize_string, QdrantSessionManager, PayloadMapping

# Configuration du logger pour ce module
logger = logging.getLogger(__name__)
Base = declarative_base()

class JiraClient(Base):
    __tablename__ = 'clients'
    
    id = Column(Integer, primary_key=True)
    client = Column(String)
    consultant = Column(String)
    statut = Column(String)
    jira = Column(String)
    zendesk = Column(String)
    confluence = Column(String)
    erp = Column(String)

class BaseQdrantSearch:
    CACHE_MAX_SIZE = 1000  # ✅ Constante pour la limite du cache
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 2
    CACHE_ENABLED = True
    TIMEOUT = 15
    def __init__(self, collection_name=None, use_db=True):
        self.collection_name = collection_name
        self.use_db = use_db
        
        # ✅ LRU Cache optimisé
        self._embedding_cache = OrderedDict()
        
        self.logger = logging.getLogger('ITS_HELP.qdrant')
        self.logger.propagate = False
        
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

        if self.collection_name:
            self._init_qdrant_client()
    def validate_payload(self, payload: dict, source_type: str) -> bool:
        if not isinstance(payload, dict):
            return False
            
        required = PayloadMapping.COMMON_FIELDS | PayloadMapping.SOURCE_FIELDS[source_type]['required']
        return all(payload.get(field) for field in required)
    def _init_qdrant_client(self):
        """Initialisation séparée du client Qdrant."""
        try:
            self.client = QdrantClient(
                url=os.getenv('QDRANT_URL'),
                api_key=os.getenv('QDRANT_API_KEY')
            )
            self.client.get_collection(self.collection_name)
            self.logger.info(f"Connexion réussie à Qdrant '{self.collection_name}'.")
        except Exception as e:
            self.logger.error(f"Erreur connexion Qdrant: {str(e)}", exc_info=True)
            raise ValueError(f"Collection '{self.collection_name}' invalide : {str(e)}")

    def _get_from_cache(self, key: str) -> Optional[List[float]]:
        """Récupère un embedding du cache."""
        return self._embedding_cache.get(key, None)

    def _add_to_cache(self, key: str, vector: List[float]):
        """Ajoute un embedding au cache avec une suppression optimisée."""
        if len(self._embedding_cache) >= self.CACHE_MAX_SIZE:
            self._embedding_cache.popitem(last=False)  # ✅ Suppression FIFO efficace
        self._embedding_cache[key] = vector

    

    async def obtenir_embedding(self, texte: str, query_type: str = None) -> Optional[List[float]]:
        """
        Génère un embedding OpenAI avec gestion avancée du cache et des erreurs.
        
        Args:
            texte: Le texte à transformer en embedding
            query_type: Type de requête pour optimisation (optionnel)
        
        Returns:
            Liste des valeurs de l'embedding ou None en cas d'erreur
        """
        # Constantes pour les différents types de requêtes
        QUERY_TYPES = {
            'CONFIG': ['config', 'paramètr', 'workflow'],
            'INCIDENT': ['bug', 'erreur', 'incident', 'ticket'],
            'DOCUMENTATION': ['doc', 'guide', 'manuel'],
        }
        try:
            # Détection automatique du type de requête si non spécifié
            if not query_type:
                texte_lower = texte.lower()
                for qtype, keywords in QUERY_TYPES.items():
                    if any(kw in texte_lower for kw in keywords):
                        query_type = qtype
                        break
                        
            # Timeout dynamique en fonction du type de requête
            timeout = self.TIMEOUT
            if query_type == 'CONFIG':
                timeout = min(self.TIMEOUT * 1.5, 30)  # Plus de temps pour requêtes complexes
            
            async with asyncio.timeout(timeout):
                if not isinstance(texte, str) or not texte.strip():
                    self.logger.warning("Texte invalide ou vide")
                    return None

                texte = texte.strip()
                # Cache key avec query_type pour optimiser la réutilisation
                cache_components = [texte]
                if query_type:
                    cache_components.append(query_type)
                cache_key = hashlib.md5('|'.join(cache_components).encode('utf-8')).hexdigest()

                # Vérification du cache avec métriques
                if self.CACHE_ENABLED:
                    start_time = time.monotonic()
                    cached_vector = self._get_from_cache(cache_key)
                    if cached_vector:
                        cache_time = time.monotonic() - start_time
                        self.logger.debug(f"Cache hit: {cache_key[:8]}... en {cache_time:.4f}s")
                        return cached_vector

                # Gestion des tentatives avec backoff exponentiel
                for attempt in range(self.MAX_RETRIES):
                    retry_delay = min(self.RETRY_BASE_DELAY ** attempt, 8)

                    try:
                        # Tentative avec timeout spécifique pour la requête API
                        api_timeout = timeout * 0.8  # 80% du timeout total pour l'API
                        
                        # Utilisation de fonction asynchrone avec timeout
                        async with asyncio.timeout(api_timeout):
                            response = self.openai_client.embeddings.create(
                                input=texte,
                                model="text-embedding-ada-002"
                            )

                        if not response.data:
                            raise ValueError("Réponse OpenAI vide")

                        vector = response.data[0].embedding
                        
                        # Validation approfondie du vecteur
                        if not isinstance(vector, list) or not vector:
                            raise ValueError("Format embedding invalide")
                        
                        if len(vector) != 1536:  # Taille attendue pour ada-002
                            raise ValueError(f"Taille du vecteur invalide: {len(vector)}")

                        # Sauvegarde dans le cache
                        if self.CACHE_ENABLED:
                            self._add_to_cache(cache_key, vector)

                        return vector

                    except asyncio.TimeoutError:
                        self.logger.warning(f"Timeout API (tentative {attempt+1}/{self.MAX_RETRIES}), réessaie après {retry_delay}s")

                    except Exception as e:
                        self.logger.error(f"Erreur OpenAI: {str(e)} (tentative {attempt+1}/{self.MAX_RETRIES})")

                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(retry_delay)

                self.logger.error(f"Échec définitif après {self.MAX_RETRIES} tentatives pour un texte de {len(texte)} caractères")
                
                # Récupération d'un embedding similaire comme fallback
                if self.CACHE_ENABLED and len(texte) > 20:
                    similar_vector = await self._find_similar_embedding(texte)
                    if similar_vector:
                        self.logger.info("Utilisation d'un embedding similaire comme fallback")
                        return similar_vector
                        
                return None
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout global dépassé pour texte de {len(texte)} caractères")
            return None
        except Exception as e:
            self.logger.error(f"Erreur inattendue: {str(e)}")
            return None
            
    async def _find_similar_embedding(self, texte: str) -> Optional[List[float]]:
        """Trouve un embedding similaire dans le cache"""
        if not self._embedding_cache:
            return None
            
        # Calcul de similarité basique par mots-clés communs
        text_words = set(texte.lower().split())
        best_match = None
        best_score = 0
        
        for key, vector in self._embedding_cache.items():
            # Extraire le texte original du cache (si disponible)
            cache_text = getattr(key, '_original_text', '')
            if not cache_text:
                continue
                
            cache_words = set(cache_text.lower().split())
            common_words = text_words.intersection(cache_words)
            
            # Score basé sur le nombre de mots communs
            score = len(common_words) / max(len(text_words), 1)
            
            if score > 0.7 and score > best_score:  # Seuil de 70% de mots communs
                best_score = score
                best_match = vector
                
        return best_match
    def _format_json(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)

    def normalize_date(self, date_value: Any) -> Optional[datetime]:
        """Version synchrone de normalize_date"""
        if not date_value:
            return None
            
        try:
            if isinstance(date_value, (int, float)):
                return datetime.fromtimestamp(date_value, tz=timezone.utc)
            elif isinstance(date_value, str):
                try:
                    return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                except ValueError:
                    # Tentative avec différents formats
                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"]:
                        try:
                            return datetime.strptime(date_value, fmt).replace(tzinfo=timezone.utc)
                        except ValueError:
                            continue
            return None
        except Exception as e:
            self.logger.warning(f"Erreur normalisation date : {str(e)}")
            return None

    async def validate_required_fields(self, payload: dict, fields: List[str]) -> bool:
        if not isinstance(payload, dict):
            self.logger.warning("Payload invalide")
            return False
        missing = [f for f in fields if f not in payload]
        if missing:
            self.logger.warning(f"Champs manquants: {missing}")
            return False
        return True

    async def _connect_to_db(self):
        if self.use_db:
            try:
                self.engine = create_async_engine('sqlite+aiosqlite:///data/database.db')
                self.SessionLocal = async_sessionmaker(bind=self.engine, expire_on_commit=False)
            except Exception as e:
                self.logger.error(f"Erreur connexion DB: {str(e)}")
                raise

    def set_source_type(self, result, source_type):
        try:
            if isinstance(result, dict):
                result['source_type'] = source_type
                return
            if hasattr(result, '_source_type'):
                result._source_type = source_type
            if not hasattr(result, 'payload'):
                result.payload = {}
            if isinstance(result.payload, dict):
                result.payload['source_type'] = source_type
            else:
                payload_dict = result.payload.__dict__ if hasattr(result.payload, '__dict__') else {}
                payload_dict['source_type'] = source_type
                result.payload = payload_dict
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'attribution du source_type: {str(e)}")

    def _normalize_result_for_slack(self, result: Any) -> Dict:
        try:
            if isinstance(result, dict):
                normalized = {
                    'id': result.get('id') or result.get('ticket_id') or result.get('key'),
                    'key': result.get('key') or result.get('id') or result.get('ticket_id'),
                    'summary': result.get('summary') or result.get('title'),
                    'content': result.get('content') or result.get('text') or result.get('description'),
                    'client': result.get('client'),
                    'resolution': result.get('status') or result.get('resolution'),
                    'assignee': result.get('assignee'),
                    'created': result.get('created'), 
                    'updated': result.get('updated'),
                    'url': result.get('url') or result.get('page_url')
                }
                class ResultWrapper:
                    def __init__(self, data: Dict):
                        self.payload = data 
                        self.score = float(result.get('score', 0.0))
                if not all(normalized.get(field) for field in ['id', 'summary', 'content']):
                    self.logger.warning("Normalisation incomplète des champs requis")
                    return None
                return ResultWrapper(normalized)

            if hasattr(result, 'payload'):
                payload = result.payload if isinstance(result.payload, dict) else vars(result.payload)
                result.payload = {
                    'key': payload.get('id') or payload.get('key'),
                    'summary': payload.get('summary') or payload.get('title'), 
                    'client': payload.get('client'),
                    'resolution': payload.get('status') or payload.get('resolution'),
                    'assignee': payload.get('assignee'),
                    'created': payload.get('created'),
                    'updated': payload.get('updated'), 
                    'content': payload.get('content') or payload.get('text'),
                    'url': payload.get('url') or payload.get('page_url')
                }
                return result

            self.logger.warning(f"Format de résultat non géré: {type(result)}")
            return None

        except Exception as e:
            self.logger.error(f"Erreur normalisation résultat: {str(e)}")
            return None

    async def get_client_name(self, client_name: str, session) -> Optional[Dict]:
        if not client_name:
            return None
        try:
            if isinstance(client_name, dict):
                client_name = client_name.get('source', '')
            normalized_name = normalize_string(client_name)
            result = await session.execute(
                select(JiraClient).filter(
                    func.upper(JiraClient.client) == normalized_name
                )
            )
            clients = result.scalars().all()
            if not clients:
                return None
            if len(clients) == 1:
                client = clients[0]
                return {
                    "jira": client.jira or client.client,
                    "zendesk": client.zendesk or client.client, 
                    "confluence": client.confluence or client.client,
                    "erp": client.erp,
                    "source": client.client,
                    "valid": True
                }
            else:
                return {
                    "ambiguous": True,
                    "possibilities": [
                        {
                            "client": c.client,
                            "statut": c.statut,
                            "jira": c.jira,
                            "zendesk": c.zendesk,
                            "confluence": c.confluence,
                            "erp": c.erp
                        } for c in clients
                    ]
                }
        except Exception as e:
            self.logger.error(f"Erreur récupération client {client_name}: {str(e)}")
            return None

    def parse_date(self, date_value):
        if not date_value:
            return None
        try:
            if isinstance(date_value, (int, float)):
                return datetime.fromtimestamp(date_value, tz=timezone.utc)
            elif isinstance(date_value, str):
                if date_value.isdigit():
                    return datetime.fromtimestamp(float(date_value), tz=timezone.utc)
                try:
                    return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                except ValueError:
                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                        try:
                            return datetime.strptime(date_value, fmt).replace(tzinfo=timezone.utc)
                        except ValueError:
                            continue
            return None
        except Exception as e:
            self.logger.warning(f"Erreur parsing date {date_value}: {str(e)}")
            return None

    async def optimiser_requete(self, question: str, client_name: Optional[Dict] = None) -> tuple:
        """Première fonction optimiser_requete: complète et détaillée."""
        if client_name and client_name.get("source") and not client_name.get("ambiguous"):
            filtres = {
                "must": [
                    {"key": "client", "match": {"value": client_name["jira"]}}
                ]
            }
            return (question, filtres, 20)
        try:
            if not self.collection_name:
                return (question, {}, 500)
            prompt = f'''
            Analyse cette question : "{question}"

            Réponds en JSON uniquement :
            {{
                "requete_optimisee": "texte de la requête",
                "contient_date": true/false,
                "filtres": {{
                    "must": [],
                    "must_not": [],
                    "should": []
                }},
                "limit": 20
            }}
            '''
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Génère uniquement un JSON valide sans commentaire ni formatage."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            self.logger.info(f"Contenu brut GPT:\n{response.choices[0].message.content.strip()}")
            resultat = json.loads(response.choices[0].message.content.strip())

            filtres = self.validate_filters(resultat.get("filtres", {}))
            limit = max(resultat.get("limit", 500), 1)
            return (
                resultat.get("requete_optimisee", question),
                filtres,
                limit
            )
        except Exception as e:
            self.logger.error(f"Erreur optimisation requête : {str(e)}")
            return (question, {"must": [], "must_not": [], "should": []}, 500)

    def _validate_json_response(self, content: str) -> Optional[Dict]:
        try:
            if not content or not isinstance(content, str):
                return None
            content = content.strip()
            if '```' in content:
                pattern = r'```(?:json)?(.*?)```'
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    content = match.group(1).strip()
            if not (content.startswith('{') and content.endswith('}')):
                return None
            if not content or content.strip().startswith("<"):
                return None
            data = json.loads(content)
            if not isinstance(data, dict):
                return None
            cleaned_data = {}
            for key, value in data.items():
                if isinstance(key, str) and isinstance(value, str):
                    cleaned_value = re.sub(r'[^\w\s.,()-]', '', value)
                    if len(cleaned_value) > 100:
                        cleaned_value = cleaned_value[:97] + "..."
                    cleaned_data[key] = cleaned_value
                elif isinstance(key, str):
                    cleaned_data[key] = str(value)
            return cleaned_data if cleaned_data else None
        except json.JSONDecodeError:
            self.logger.error("Invalid JSON format")
            return None
        except Exception as e:
            self.logger.error(f"Error validating JSON: {str(e)}")
            return None

    def construire_filtre(self, client_info: Union[Dict, str, None]) -> Filter:
        if not client_info:
            return Filter()
        if isinstance(client_info, dict):
            client_value = client_info.get("source", "")
        else:
            client_value = str(client_info)
        self.logger.info(f"Construction du filtre pour client: {client_value}")
        must_conditions = [
            FieldCondition(
                key="client",
                match=MatchValue(value=str(client_value))
            )
        ] if client_value else []
        return Filter(must=must_conditions if must_conditions else None)

    async def send_searching_message(self, say: Any, question_type: str):
        try:
            if "ticket" in question_type.lower():
                await say({
                    "text": "Recherche en cours...",
                    "blocks": [{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🔍 Recherche en cours dans les tickets..."
                        }
                    }]
                })
            else:
                await say({
                    "text": "Recherche en cours...",
                    "blocks": [{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🔍 Analyse de votre demande en cours..."
                        }
                    }]
                })
        except Exception as e:
            self.logger.error(f"Erreur envoi message recherche: {str(e)}")

    def validate_filters(self, filtres: dict) -> dict:
        if not isinstance(filtres, dict):
            self.logger.warning("Filtres invalides, utilisation des valeurs par défaut")
            return {"must": [], "must_not": [], "should": []}
        return {k: v for k, v in filtres.items() if k in ["must", "must_not", "should"]}
    async def _analyser_pertinence(self, results: List[Dict], question: str) -> Dict[str, str]:
        """Analyse la pertinence des résultats."""
        try:
            if not results:
                return {}
                
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": f"Analyse la pertinence de ces résultats pour la question : '{question}'\n"
                            "Format attendu: {id: 'explication'}"
                }, {
                    "role": "user",  
                    "content": json.dumps([{
                        'id': r.get('id', 'unknown'),
                        'content': r.get('content', '')[:500],
                        'score': r.get('score', 0)
                    } for r in results])
                }],
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                self.logger.error("Format JSON invalide retourné par l'analyse")
                return {}
                
        except Exception as e:
            self.logger.error(f"Erreur analyse pertinence: {str(e)}")
            return {}
    async def extraire_dates_question(self, question: str) -> tuple:
        try:
            if not question:
                self.logger.warning("Question vide")
                return None, None
            time_detect_response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": "La question contient-elle une référence temporelle ? Réponds uniquement par true ou false."
                }, {
                    "role": "user",
                    "content": question
                }],
                temperature=0.1
            )
            if time_detect_response.choices[0].message.content.strip().lower() != "true":
                self.logger.info("Pas de référence temporelle détectée")
                return None, None
            if 'mois' in question.lower():
                month_response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "system",
                        "content": (
                            "Extrait le mois et l'année. Format STRICT JSON requis:\n"
                            "{\"debut\": \"YYYY-MM-DD\", \"fin\": \"YYYY-MM-DD\"}\n"
                            "Pour octobre 2024: {\"debut\": \"2024-10-01\", \"fin\": \"2024-10-31\"}\n"
                            "Pour le mois courant si non précisé."
                        )
                    }, {
                        "role": "user",
                        "content": question
                    }],
                    temperature=0.1
                )
                content = month_response.choices[0].message.content.strip()
                try:
                    dates = json.loads(content)
                    if not isinstance(dates, dict) or 'debut' not in dates or 'fin' not in dates:
                        raise ValueError("Format JSON invalide")
                    debut = datetime.fromisoformat(dates['debut']).replace(tzinfo=timezone.utc)
                    fin = datetime.fromisoformat(dates['fin']).replace(tzinfo=timezone.utc)
                    if debut <= fin:
                        self.logger.info(f"Dates extraites (mode mois): {debut} -> {fin}")
                        return debut, fin
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    self.logger.warning(f"Erreur extraction dates (mode mois): {str(e)}")
                    return None, None
            date_response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": (
                        "Extrait UNIQUEMENT les dates mentionnées.\n"
                        "Format JSON strict requis: {\"debut\": \"YYYY-MM-DD\", \"fin\": \"YYYY-MM-DD\"}\n"
                        "Règles:\n"
                        "1. Si une seule date mentionnée: même date pour debut et fin\n"
                        "2. Si période relative (ex: dernière semaine): calculer les dates exactes\n"
                        "3. Si pas de date claire: null pour debut et fin"
                    )
                }, {
                    "role": "user",
                    "content": question
                }],
                temperature=0.1
            )
            content = date_response.choices[0].message.content.strip()
            if not content or content == "null":
                return None, None
            try:
                dates = json.loads(content)
                if not isinstance(dates, dict):
                    return None, None
                debut = dates.get('debut')
                fin = dates.get('fin')
                if debut and fin:
                    debut = datetime.fromisoformat(debut.replace('Z', '+00:00'))
                    fin = datetime.fromisoformat(fin.replace('Z', '+00:00'))
                    if debut <= fin:
                        self.logger.info(f"Dates extraites: {debut} -> {fin}")
                        return debut, fin
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.warning(f"Erreur parsing dates: {str(e)}")
            return None, None
        except Exception as e:
            self.logger.error(f"Erreur extraction dates: {str(e)}", exc_info=True)
            return None, None

    # ==> On renomme la deuxième définition de optimiser_requete
    async def optimiser_requete_simplifiee(self, question: str, client_info: Optional[Dict] = None) -> tuple:
        """Deuxième fonction renommée (avant nommée optimiser_requete)."""
        try:
            prompt = f"Analyse et optimise cette question : {question}"
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.1
            )
            return response.choices[0].message.content, {}, 20
        except Exception as e:
            self.logger.error(f"Erreur optimisation: {str(e)}")
            return question, {}, 20

    def get_field_safe(self, payload, field, default=''):
        try:
            return payload.get(field, default) if isinstance(payload, dict) else getattr(payload, field, default)
        except Exception:
            return default

    def validate_date(self, date_input: Union[str, int, float]) -> Optional[datetime]:
        if not date_input:
            return None
        try:
            if isinstance(date_input, (int, float)):
                return datetime.fromtimestamp(date_input, tz=timezone.utc)
            if isinstance(date_input, str):
                date_str = date_input.strip()
                if date_str.isdigit():
                    return datetime.fromtimestamp(float(date_str), tz=timezone.utc)
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
                except ValueError:
                    pass
                for fmt in [
                    "%Y-%m-%d",
                    "%d/%m/%Y", 
                    "%Y/%m/%d",
                    "%d.%m.%Y",
                    "%Y%m%d"
                ]:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        return dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
            self.logger.warning(f"Format de date non reconnu: {date_input}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur validation date: {str(e)}")
            return None

    def _score_result(self, result) -> float:
        """Calcule un score pondéré pour un résultat avec des critères multiples."""
        try:
            base_score = float(getattr(result, 'score', 0.0))
            # Extraction sécurisée du score et du payload
            if isinstance(result, dict):
                base_score = float(result.get('score', 0.0))
                payload = result.get('payload', result)
            else:
                base_score = float(getattr(result, 'score', 0.0))
                payload = result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})

            if not payload:
                return 0.0

            # Le reste de la fonction reste identique
            relevance_score = base_score * 0.6
            freshness_score = 0.0
            context_score = 0.0
                            
            # Score de fraîcheur (20%)
            try:
                created_date = datetime.fromisoformat(payload.get('created', '').replace('Z', '+00:00'))
                days_old = (datetime.now(timezone.utc) - created_date).days
                if days_old <= 7:          # Très récent
                    freshness_score = 0.20
                elif days_old <= 30:       # Récent
                    freshness_score = 0.15
                elif days_old <= 90:       # Modérément récent
                    freshness_score = 0.10
                elif days_old <= 180:      # Assez ancien
                    freshness_score = 0.05
            except Exception as e:
                self.logger.debug(f"Erreur lors du calcul du score de fraîcheur: {str(e)}")
                freshness_score = 0.0
            
            # Score contextuel (20%)
            context_points = 0
            
            # Correspondance client (8%)
            if self._current_client_info and str(self._current_client_info.get("source", "")).upper() == str(payload.get("client", "")).upper():
                context_points += 0.08
                
            # Qualité des métadonnées (max 12%)
            if payload.get('assignee'):  # Ticket assigné (4%)
                context_points += 0.04
                
            # Présence de description/contenu (4%)
            if len(str(payload.get('content', ''))) > 100:
                context_points += 0.04
                
            # Status/Résolution défini (4%)
            if payload.get('resolution') or payload.get('status'):
                context_points += 0.04
                
            context_score = context_points
            
            # Pénalisations
            penalties = 0
            if not payload.get('key') or not payload.get('summary'):
                penalties += 0.1  # -10% si informations essentielles manquantes
            if len(str(payload.get('content', ''))) < 50:
                penalties += 0.05  # -5% si contenu trop court
                
            # Score final (0.0 à 1.0)
            final_score = max(0.0, min(1.0, (relevance_score + freshness_score + context_score) * (1 - penalties)))
            
            self.logger.debug(f"""
            Calcul score pour {payload.get('key', 'Unknown')}:
            Base: {relevance_score:.3f} (60%)
            Fraîcheur: {freshness_score:.3f} (20%)
            Contexte: {context_score:.3f} (20%)
            Pénalités: -{penalties:.3f}
            Score final: {final_score:.3f}
            """)
            current_client = getattr(self, '_current_client_info', {})
            if current_client and str(current_client.get("source", "")).upper() == str(payload.get("client", "")).upper():
                context_points += 0.08
            return final_score
                
        except Exception as e:
            self.logger.error(f"Erreur calcul score: {str(e)}")
            return 0.0

    def valider_resultat(self, res) -> bool:
        try:
            if not hasattr(res, 'payload')or not res.payload:
                self.logger.debug("Résultat sans payload")
                return False
            payload = res.payload if isinstance(res.payload, dict) else getattr(res.payload, '__dict__', {})
            if not payload:
                self.logger.debug("Payload invalide ou inaccessible")
                return False
            required_fields = ['id', 'summary', 'content', 'client']
            if not all(payload.get(field) for field in required_fields):
                missing = [f for f in required_fields if not payload.get(f)]
                self.logger.debug(f"Champs manquants : {missing}")
                return False
            if not hasattr(res, 'score') or res.score < 0.3:
                self.logger.debug(f"Score invalide: {getattr(res, 'score', None)}")
                return False
            return getattr(res, 'score', 0) >= 0.45
        except Exception as e:
            self.logger.error(f"Erreur validation résultat: {str(e)}")
            return False

    def recherche_similaire(self, query_vector, limit=5):
        try:
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit
            )
            return resultats
        except Exception as e:
            print(f"Erreur lors de la recherche: {str(e)}")
            return []

    def recherche_avec_filtres(self, query_vector, filtres: dict, limit=5):
        try:
            self.logger.info(f"Recherche avec filtres: {filtres}")
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=self.construire_filtre(filtres),
                limit=limit
            )
            self.logger.info(f"Résultats trouvés: {len(resultats)}")
            return [r for r in resultats if hasattr(r, 'score') and r.score >= 0.45]
        except Exception as e:
            self.logger.error(f"Erreur recherche filtrée: {str(e)}")
            return []

    def obtenir_info_collection(self):
        try:
            return self.client.get_collection(self.collection_name)
        except Exception as e:
            print(f"Erreur lors de la récupération des informations: {str(e)}")
            return None

    @staticmethod
    def remove_duplicates(clients):
        # Statique pour la manipulation de listes externes
        seen = set()
        return [c for c in clients if not (c in seen or seen.add(c))]
    def _add_date_conditions(self, conditions: List, date_debut: Optional[datetime], 
                           date_fin: Optional[datetime]):
        """Ajoute les conditions de date aux filtres."""
        if date_debut:
            conditions.append(
                FieldCondition(
                    key="created",
                    range=Range(gte=int(date_debut.timestamp()))
                )
            )
            
        if date_fin:
            conditions.append(
                FieldCondition(
                    key="created",
                    range=Range(lte=int(date_fin.timestamp()))
                )
            )

    async def _execute_search(self, vector: List[float], query_filter: Filter) -> List[Any]:
        """Exécute la recherche Qdrant avec gestion d'erreurs."""
        try:
            async with asyncio.timeout(30):
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=vector,
                    query_filter=query_filter,
                    limit=[500]
                )
                return [r for r in results if hasattr(r, 'score') and r.score >= 0.45]
        except asyncio.TimeoutError:
            self.logger.error("Timeout de la recherche Qdrant")
            return []
        except Exception as e:
            self.logger.error(f"Erreur recherche Qdrant: {str(e)}")
            return []
class DocumentQdrantSearch(BaseQdrantSearch):
    def _format_document_text(self, result, score, fiabilite):
        if not isinstance(result.payload, dict):
            payload = result.payload.__dict__
        else:
            payload = result.payload
        return f"""*{payload['source_type']}-{payload['id']}* - {payload['summary']}..."""

    def validate_json_response(self, content: str) -> Optional[dict]:
        try:
            if not content or not isinstance(content, str):
                self.logger.warning("Contenu JSON invalide ou vide")
                return None
            content = content.strip()
            if '```' in content:
                match = re.search(r'```(?:json)?(.*?)```', content, re.DOTALL)
                if match:
                    content = match.group(1).strip()
            if not (content.startswith('{') and content.endswith('}')):
                self.logger.warning("Structure JSON invalide")
                return None
            if not content or content.strip().startswith("<"):
                self.logger.warning("Réponse vide ou HTML, abandon parse")
                return None
            data = json.loads(content)
            if not isinstance(data, dict):
                self.logger.warning("Le résultat JSON n'est pas un dictionnaire")
                return None
            cleaned_data = {}
            for key, value in data.items():
                if isinstance(key, str) and isinstance(value, str):
                    cleaned_value = re.sub(r'[^\w\s.,()-]', '', value)
                    if len(cleaned_value) > 100:
                        cleaned_value = cleaned_value[:97] + "..."
                    cleaned_data[key] = cleaned_value
                elif isinstance(key, str):
                    cleaned_data[key] = str(value)
            return cleaned_data if cleaned_data else None
        except json.JSONDecodeError as e:
            self.logger.error(f"Erreur décodage JSON: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur validation JSON: {str(e)}")
            return None

class SimpleQdrantSearch(BaseQdrantSearch):
    def valider_resultats(self, resultats) -> list:
        resultats_valides = []
        scores_vus = set()
        for res in resultats:
            if not isinstance(res.payload, dict):
                continue
            score = round(res.score * 100)
            if score >= 30 and score not in scores_vus:
                scores_vus.add(score)
                resultats_valides.append(res)
        return resultats_valides[:5]

    def _format_simple_text(self, result, score, fiabilite):
        if not isinstance(result.payload, dict):
            payload = result.payload.__dict__
        else:
            payload = result.payload
        return f"""*{payload['title']}* - {fiabilite} {score}%..."""

class QdrantJiraSearch(BaseQdrantSearch):
    def __init__(self, collection_name=None):
        self.logger = logging.getLogger('ITS_HELP.qdrant.jira')
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        self._current_client_info = None
        super().__init__(collection_name)
        self._date_cache = {}
    required_fields = ['key', 'summary', 'content', 'client'] # Champs vraiment essentiels
    @lru_cache(maxsize=1000)
    def _normalize_date_cached(self, date_str: str) -> Optional[datetime]:
        return self.normalize_date(date_str)
    def valider_resultat(self, res) -> bool:
        try:
            if isinstance(res, dict):
                payload = res.get('payload', {})
                score = float(res.get('score', 0.0))
            else:
                if not hasattr(res, 'payload'):
                    self.logger.debug("Résultat sans payload")
                    return False
                payload = res.payload if isinstance(res.payload, dict) else getattr(res.payload, '__dict__', {})
                score = float(getattr(res, 'score', 0.0))
            if not all(field in payload and payload[field] is not None for field in self.required_fields):
                missing = [f for f in self.required_fields if not payload.get(f)]
                self.logger.debug(f"Champs manquants ou nuls: {missing}")
                return False
            return score >= 0.3
        except Exception as e:
            self.logger.error(f"Erreur validation résultat: {str(e)}")
            return False

    DATE_FORMAT_WITH_MS = "%Y-%m-%dT%H:%M:%S.%fZ"
    DATE_FORMAT_WITHOUT_MS = "%Y-%m-%dT%H:%M:%SZ"
    DATE_FORMATS = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ", 
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%Y/%m/%d"
    ]
    ERROR_INVALID_DATE_FORMAT = "Format de date invalide"
    ERROR_FUTURE_DATE = "La date ne peut pas être dans le futur"
    ERROR_DATE_RANGE = "La date de début doit être antérieure à la date de fin"

    

    async def post_traitement_dates(self, resultats, date_debut=None, date_fin=None, is_general_query: bool = False):
        try:
            if not resultats:
                return []

            filtered_results = []
            seen_contents = {}

            for res in resultats:
                try:
                    payload = res.payload if isinstance(res.payload, dict) else res.payload.__dict__
                    created = payload.get('created')

                    # 🔽 Application du seuil de score dynamique
                    min_score_threshold = 0.35 if is_general_query else 0.45
                    if hasattr(res, 'score') and res.score < min_score_threshold:
                        continue

                    # 🔄 Normalisation de la date
                    created_date = self.normalize_date(created)
                    if created_date:
                        if date_debut:
                            date_debut = date_debut.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                        if date_fin:
                            date_fin = date_fin.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)

                        if (date_debut and created_date < date_debut) or (date_fin and created_date > date_fin):
                            continue

                    
                    # Hachage plus robuste prenant en compte plusieurs champs pertinents
                    content = str(payload.get('content', '') or '')
                    summary = str(payload.get('summary', '') or '')
                    combined_text = f"{content[:300]}{summary[:100]}{payload.get('client', '')}"
                    dedup_key = hashlib.md5(combined_text.encode('utf-8', errors='ignore')).hexdigest()

                    # Gestion de la déduplication avec priorité au score le plus élevé
                    if dedup_key in seen_contents:
                        if res.score > seen_contents[dedup_key].score:
                            seen_contents[dedup_key] = res
                    else:
                        seen_contents[dedup_key] = res

                    filtered_results.append(res)

                except Exception as e:
                    self.logger.warning(f"⚠️ Erreur traitement d'un résultat: {str(e)}", exc_info=True)
                    continue

            # 🔄 Conversion en liste et tri des résultats
            filtered_results = list(seen_contents.values())

            if is_general_query:
                sorted_results = sorted(
                    filtered_results,
                    key=lambda x: (-x.score if hasattr(x, 'score') else 0, x.payload.get('created', '2000-01-01')),
                    reverse=True
                )
                limit = 10
            else:
                sorted_results = sorted(filtered_results, key=lambda x: -x.score if hasattr(x, 'score') else 0)
                limit = 5

            # 📢 Logging détaillé
            if is_general_query:
                self.logger.info(f"🔎 Mode requête générale: {len(sorted_results)}/{len(resultats)} résultats retenus")
            elif date_debut or date_fin:
                self.logger.info(f"📆 Filtrage temporel appliqué: {len(sorted_results)}/{len(resultats)} résultats")
                self.logger.info(f"🕒 Période filtrée: {date_debut or 'début'} → {date_fin or 'fin'}")
            else:
                self.logger.info(f"📊 Mode standard: {len(sorted_results)} résultats retenus")

            return sorted_results[:limit]

        except Exception as e:
            self.logger.error(f"❌ Erreur inattendue dans post_traitement_dates: {str(e)}", exc_info=True)
            return []

    def _extract_field(self, payload: Dict, field: str) -> str:
        """Extrait un champ avec gestion des alternatives."""
        alternatives = {
            'key': ['key', 'id', 'ticket_id'],
            'summary': ['summary', 'title', 'name'],
            'content': ['content', 'text', 'description'],
            'client': ['client', 'company_name']
        }
        
        if field in alternatives:
            for alt in alternatives[field]:
                if payload.get(alt):
                    return str(payload[alt])
        return payload.get(field, 'N/A')
    async def format_for_slack(self, result) -> Optional[Dict[str, Any]]:
        try:
            if not result or not hasattr(result, 'score') or result.score < 0.35:
                return {}

            # Extraction et normalisation du payload
            payload = result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})
            if not payload:
                self.logger.warning("Payload non trouvé")
                return {}

            # Validation stricte des champs requis
            if not all(payload.get(field) for field in ['key', 'summary', 'client']):
                self.logger.warning("Champs requis manquants")
                return {}

            # Calcul du score et de la fiabilité
            score = round(float(result.score) * 100)
            fiabilite = "🟢" if score > 80 else "🟡" if score > 60 else "🔴"

            # Formatage des dates
            created, updated = self._safe_format_dates(payload)

            # Troncature du contenu
            content = str(payload.get('content', ''))
            if len(content) > 500:
                content = content[:497] + "..."

            # Construction du message
            message = (
                f"*JIRA-{payload.get('key')}* - {payload.get('summary')}\n"
                f"Client: {payload.get('client')} - {fiabilite} {score}%\n"
                f"ERP: {payload.get('erp', 'N/A')} - Status: {payload.get('resolution', 'En cours')}\n"
                f"Assigné à: {payload.get('assignee', 'Non assigné')}\n"
                f"Créé le: {created} - Maj: {updated}\n"
                f"Description: {content}\n"
                f"URL: {payload.get('url', 'N/A')}"
            )

            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }

        except Exception as e:
            self.logger.error(f"Erreur formatage: {str(e)}")
            # Utiliser le nom de la classe pour déterminer le type de source
            source_type = self.__class__.__name__.replace("SearchClient", "").lower()
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{source_type.upper()}* - ❌ Erreur de formatage"
                }
            }



    def _sanitize(self, text: Any) -> str:
        if not isinstance(text, str):
            text = str(text)
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _validate_fields(self, data: Dict[str, Any], fields: list) -> bool:
        return all(field in data and data[field] for field in fields)

    def _extract_payload_and_score(self, result: Union[Dict[str, Any], Any]) -> Tuple[Optional[Dict[str, Any]], float]:
        if isinstance(result, dict):
            payload = result.get('payload', result) if isinstance(result.get('payload'), dict) else result
            score = float(result.get('score', 0.0))
        elif hasattr(result, 'payload'):
            payload = result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})
            score = float(getattr(result, 'score', 0.0))
        else:
            self.logger.warning("Résultat sans payload identifiable.")
            return {}   
        return payload, score

    def _safe_format_dates(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        try:
            return self._format_dates(payload)
        except ValueError as ve:
            self.logger.error(f"Erreur de valeur dans le formatage des dates: {ve}")
            return 'N/A', 'N/A'
        except KeyError as ke:
            self.logger.error(f"Clé manquante pour le formatage des dates: {ke}")
            return 'N/A', 'N/A'
        except Exception as _:
            self.logger.exception("Erreur inattendue lors du formatage des dates")
            raise

    def _truncate_content(self, content: str, max_length: int = 500) -> str:
        if len(content) > max_length:
            cutoff = content[:max_length].rfind(". ")
            if cutoff == -1:
                cutoff = content[:max_length].rfind(" ")
            if cutoff == -1:
                cutoff = max_length - 3
            return content[:cutoff] + "..."
        return content

    def _build_slack_response(self, text: str) -> Dict[str, Any]:
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text
            }
        }

    def _validate_payload(self, payload: dict) -> bool:
        if not isinstance(payload, dict):
            return False
        required_fields = ['key', 'summary', 'content', 'client']
        return all(payload.get(field) for field in required_fields)

    def _format_date(self, date_value: str) -> str:
        if not date_value:
            return 'N/A'
        try:
            if isinstance(date_value, (int, float)):
                dt = datetime.fromtimestamp(date_value, tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return date_value[:10] if date_value else 'N/A'

    def _extract_score(self, result) -> Optional[float]:
        try:
            if isinstance(result, dict):
                return float(result.get('score', 0))
            return float(getattr(result, 'score', 0))
        except (ValueError, TypeError):
            return None

    def _extract_payload(self, result) -> Optional[Dict]:
        try:
            if isinstance(result, dict):
                return result
            if not hasattr(result, 'payload'):
                return {}
            return result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', None)
        except Exception:
            return {}

    def _format_dates(self, payload: Dict) -> Tuple[str, str]:
        try:
            created = payload.get('_created_date') or payload.get('created')
            updated = payload.get('_updated_date') or payload.get('updated')

            def format_date(date_value):
                if isinstance(date_value, datetime):
                    return date_value.strftime("%Y-%m-%d")
                elif isinstance(date_value, (int, float)):
                    return datetime.fromtimestamp(date_value, tz=timezone.utc).strftime("%Y-%m-%d")
                elif isinstance(date_value, str):
                    try:
                        if 'T' in date_value:
                            return datetime.fromisoformat(date_value.replace('Z', '+00:00')).strftime("%Y-%m-%d")
                        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]:
                            try:
                                dt = datetime.strptime(date_value, fmt)
                                return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d")
                            except ValueError:
                                continue
                        return date_value[:10] if date_value else 'N/A'
                    except Exception:
                        return 'N/A'
                return 'N/A'

            return format_date(created), format_date(updated)

        except Exception as e:
            self.logger.error(f"Erreur formatage dates: {str(e)}", exc_info=True)
            return 'N/A', 'N/A'


    def _build_message(self, payload: Dict, score: int, fiabilite: str,
                       created: str, updated: str) -> Optional[str]:
        try:
            return (
                f"*JIRA-{payload.get('key')}* - {payload.get('summary')}\n"
                f"Client: {payload.get('client')} - {fiabilite} {score}%\n"
                f"ERP: {payload.get('erp', 'N/A')} - Status: {payload.get('resolution', 'En cours')}\n"
                f"Consultant: {payload.get('assignee', 'Non assigné')}\n"
                f"Créé le: {created} - Maj: {updated}\n"
                f"Description: {str(payload.get('content', 'N/A'))[:500]}\n\n"
                f"URL: {payload.get('url', 'N/A')}"
            )
        except Exception as e:
            self.logger.error(f"Erreur construction message: {str(e)}")
            return None

    def construire_filtre(self, client_value: Union[str, Dict]) -> Filter:
        if not client_value:
            return Filter()
        elif isinstance(client_value, dict):
            client_value = client_value.get("jira", client_value.get("source", ""))
        return Filter()
    def _validate_vector(self, vector: List[float]) -> bool:
        """Valide le vecteur d'embedding."""
        if not isinstance(vector, list):
            return False
        if not vector or len(vector) != 1536:  # Dimension attendue pour ADA-002
            return False
        if not all(isinstance(x, float) for x in vector):
            return False
        return True
    async def recherche_intelligente(self, question: str, client_name: Optional[Dict] = None, date_debut: Optional[datetime] = None, date_fin: Optional[datetime] = None):
        async with QdrantSessionManager(self.client) as session_manager:
            try:
                """
                Effectue une recherche intelligente dans les tickets Jira.
                """
                try:
                    vector = await self.obtenir_embedding(question)
                    if not vector:
                        self.logger.error("Échec génération vector")
                        return []
                    self._current_client_info = client_name 
                    if not question:
                        self.logger.error("Question vide")
                        return []

                    self.logger.info("=== Début recherche Jira ===")
                    self.logger.info(f"Question: {question}")
                    self.logger.info(f"Client info: {client_name}")
                    
                    # Construction des filtres avec client_name et dates
                    must_conditions = []
                    
                    if client_name and not client_name.get("ambiguous"):
                        if isinstance(client_name, dict):
                            client_value = client_name.get("source", "")
                            self.logger.info(f"Client_Value: {client_value}")
                            if client_value:
                                # Utiliser une recherche insensible à la casse
                                client_value = str(client_value).upper()
                                self.logger.info(f"Filtre client normalisé: {client_value}")
                                must_conditions.append(
                                    FieldCondition(
                                        key="client",
                                        match=MatchValue(value=client_value)
                                    )
                                )

                    # Ajout des filtres de dates
                    if date_debut:
                        must_conditions.append(
                            FieldCondition(
                                key="created",
                                range=Range(
                                    gte=int(date_debut.timestamp())
                                )
                            )
                        )
                    if date_fin:
                        must_conditions.append(
                            FieldCondition(
                                key="created",
                                range=Range(
                                    lte=int(date_fin.timestamp())
                                )
                            )
                        )

                    query_filter = Filter(must=must_conditions) if must_conditions else Filter()
                    self.logger.info(f"Filtres Qdrant: {query_filter}")
                    
                    filtres = self.validate_filters({})
                    limit = 500
                    requete_optimisee = question

                    # Optimisation de la requête
                    try:
                        requete_optimisee, nouveaux_filtres, limit = await self.optimiser_requete(question)
                        self.logger.info(f"Début recherche avec {len(filtres.get('must', []))} filtres obligatoires")
                        self.logger.info(f"Requête optimisée: {requete_optimisee}")
                    except Exception as e:
                        self.logger.error(f"Erreur optimisation requête: {str(e)}")


                    # Vérification collection
                    try:
                        collection_info = self.client.get_collection(self.collection_name)
                        self.logger.info(f"Collection {self.collection_name} trouvée: {collection_info.points_count} points")
                    except Exception as e:
                        self.logger.error(f"Erreur accès collection {self.collection_name}: {str(e)}")
                        return []

                    # Recherche principale
                    try:
                        async with asyncio.timeout(30):
                            self.logger.info(f"Lancement recherche Qdrant collection: {self.collection_name}")
                            raw_results = self.client.search(
                                collection_name=self.collection_name,
                                query_vector=vector,
                                query_filter=query_filter,
                                limit=limit
                            )

                            # Création d'une classe wrapper pour normaliser les résultats
                            class ResultWrapper:
                                def __init__(self, score: float, payload: dict):
                                    self.score = score
                                    self.payload = payload

                            # Normalisation des résultats
                            resultats = [
                                ResultWrapper(
                                    score=result.score,
                                    payload=result.payload
                                ) for result in raw_results
                            ]

                            self.logger.info(f"Résultats bruts: {len(resultats)} trouvés")

                            if resultats:
                                scores = [f"{round(res.score * 100)}%" for res in resultats[:3]]
                                self.logger.info(f"Top 3 scores: {', '.join(scores)}")
                            
                            if not resultats:
                                self.logger.info("Aucun résultat trouvé")
                                return []

                            # Filtrage par score
                            resultats = [r for r in resultats if r.score >= 0.45]
                            self.logger.info(f"Après filtrage score ≥ 45%: {len(resultats)} résultats")

                            # Validation des résultats
                            resultats_valides = []
                            for res in resultats:
                                if self.valider_resultat(res):
                                    resultats_valides.append(res)
                                else:
                                    self.logger.warning(f"Résultat invalide: {res.payload.keys() if isinstance(res.payload, dict) else 'non dict'}")

                            # Déduplication
                            seen = set()
                            resultats_dedupliques = []
                            for res in resultats_valides:
                                content = str(res.payload.get('content', ''))
                                content_hash = hashlib.md5(content.encode()).hexdigest()
                                
                                if content_hash not in seen:
                                    seen.add(content_hash)
                                    resultats_dedupliques.append(res)

                            # Tri final et limitation
                            resultats_finaux = sorted(
                                resultats_dedupliques,
                                key=lambda x: (
                                    datetime.fromisoformat(x.payload.get('created', '2000-01-01')).replace(tzinfo=timezone.utc)
                                    if isinstance(x.payload.get('created'), str)
                                    else datetime.fromtimestamp(x.payload.get('created', 0), tz=timezone.utc),
                                    x.score
                                ),
                                reverse=True
                            )[:MAX_SEARCH_RESULTS]

                            self.logger.info(f"Résultats finals: {len(resultats_finaux)} résultats")
                            return resultats_finaux

                    except asyncio.TimeoutError:
                        self.logger.error("Timeout de la recherche")
                        return []
                    except Exception as e:
                        self.logger.error(f"Erreur lors de la recherche: {str(e)}")
                        return []
                
                except Exception as e:
                    self.logger.error(f"Erreur globale: {str(e)}")
                    return []
                finally:
                    self._current_client_info = None
            finally:
                await session_manager.cleanup()
    async def interface_utilisateur(self):
        while True:
            question = input("\nPosez votre question sur JIRA (ou 'q' pour quitter) : ")
            if question.lower() == 'q':
                break
            try:
                resultats = await self.recherche_intelligente(question)
                print("\nRésultats trouvés :")
                for idx, res in enumerate(resultats, 1):
                    score = round(res.score * 100)
                    fiabilite = "🟢" if score > 80 else "🟡" if score > 60 else "🔴"
                    if not isinstance(res.payload, dict):
                        payload = res.payload.__dict__
                    else:
                        payload = res.payload
                    print(f"\n{idx}. {payload['key']} - {payload['summary']}")
                    print(f"Client: {payload['client']} - Pertinence: {fiabilite} {score}%")
                    print(f"Status: {payload['resolution'] if payload['resolution'] else 'En cours'}")
                    print(f"Assigné à: {payload['assignee'] if payload['assignee'] else 'Non assigné'}")
                    print(f"Créé le: {payload['created'][:10]}")
                    # 🟣 Correction ici (summay -> summary)
                    print(f"Résumé: {payload['summary']}")
                    print(f"Description: {payload['content'][:500]}...")
                    print(f"URL: {payload['url']}")
            except Exception as e:
                print(f"Erreur : {str(e)}")
class BaseResultValidator:
    @staticmethod
    def validate_payload_fields(payload: dict, required_fields: list) -> bool:
        """Validation générique des champs requis"""
        if not isinstance(payload, dict):
            return False
            
        return all(
            payload.get(field) is not None and 
            str(payload.get(field)).strip()
            for field in required_fields
        )

    @staticmethod
    def normalize_field(payload: dict, field: str, alternatives: list = None, default: str = '') -> str:
        """Normalisation des champs avec alternatives"""
        if alternatives:
            for alt in alternatives:
                if payload.get(alt):
                    return str(payload[alt])
        return str(payload.get(field, default))
class EmbeddingCache:
    def __init__(self, ttl: int = 3600, maxsize: int = 1000):
        self._cache = {}
        self._ttl = ttl
        self._maxsize = maxsize
        self._timestamps = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[List[float]]:
        async with self._lock:
            if key not in self._cache:
                return None
                
            if time.monotonic() - self._timestamps[key] > self._ttl:
                del self._cache[key]
                del self._timestamps[key]
                return None
                
            return self._cache[key]

    async def set(self, key: str, value: List[float]):
        async with self._lock:
            if len(self._cache) >= self._maxsize:
                oldest = min(self._timestamps.items(), key=lambda x: x[1])[0]
                del self._cache[oldest]
                del self._timestamps[oldest]
                
            self._cache[key] = value
            self._timestamps[key] = time.monotonic()