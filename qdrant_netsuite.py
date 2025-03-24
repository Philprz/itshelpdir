# qdrant_netsuite.py

import os
import logging
import hashlib
import asyncio
import time
import threading

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, Range
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI
from openai import AsyncOpenAI
from typing import Optional, Dict, List, Any

from qdrant_jira import BaseQdrantSearch
from base_de_donnees import QdrantSessionManager
# Niveau de log cohérent :

class SimpleQdrantSearch(BaseQdrantSearch):
    # Pour SAP & NETSUITE_DUMMIES
    pass
class SyncTranslationCache:
    def __init__(self, maxsize: int = 1000):
        self._cache = {}  # Utilisons _cache au lieu de cache pour éviter la confusion
        self.maxsize = maxsize
        self.lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        with self.lock:
            return self._cache.get(key)

    def set(self, key: str, value: str):
        with self.lock:
            if len(self._cache) >= self.maxsize:
                # Supprimer 25% des entrées les plus anciennes
                remove_count = self.maxsize // 4
                for _ in range(remove_count):
                    if self._cache:
                        self._cache.pop(next(iter(self._cache)))
            self._cache[key] = value
class TranslationMixin:
    """Mixin pour ajouter la fonctionnalité de traduction."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._translation_cache = TranslationCache(maxsize=1000, ttl=3600)
        self._sync_translation_cache = SyncTranslationCache(maxsize=1000)
    def traduire_texte_sync(self, texte: str, target_lang: str = "fr") -> str:
        """Version synchrone de traduire_texte pour les contextes non-async."""
        try:
            # Utilisation du client OpenAI synchrone pour la traduction
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Traduis en {target_lang}"},
                    {"role": "user", "content": texte}
                ],
                temperature=0.1
            )
            translation = response.choices[0].message.content.strip()
            self.logger.info(f"Traduction sync: {translation}")
            # Mise en cache de la traduction
            cache_key = f"{hashlib.md5(texte[:200].encode()).hexdigest()}_{target_lang}"
            self._sync_translation_cache.set(cache_key, translation)
            
            return translation

        except Exception as e:
            self.logger.error(f"Erreur traduction sync: {str(e)}")
            return texte
    async def traduire_texte(self, texte: str, target_lang: str = "fr") -> str:
        if not texte or not isinstance(texte, str) or len(texte.strip()) < 2:
            return ""

        # Génération d'une clé de cache
        cache_key = f"{hashlib.md5(texte[:200].encode()).hexdigest()}_{target_lang}"
        
        # Vérification du cache
        cached_translation = await self._translation_cache.get(cache_key)
        if cached_translation:
            return cached_translation

        try:
            # Traduction via OpenAI
            response = await self.openai_client_async.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Traduis en {target_lang}"}, 
                    {"role": "user", "content": texte}
                ],
                temperature=0.1
            )
            translation = response.choices[0].message.content.strip()
            
            await self._translation_cache.set(cache_key, translation)
            return translation

        except Exception as e:
            self.logger.error(f"Erreur traduction: {str(e)}")
            return texte

class QdrantNetsuiteSearch(TranslationMixin, BaseQdrantSearch):
    required_fields = ['title', 'content', 'url', 'last_updated']
    def __init__(self, collection_name=None):
        load_dotenv()
        self.logger = logging.getLogger(__name__)
        super().__init__(collection_name)
        self._cache = {}  # Ajout de l'initialisation du cache
        self._vector_cache = {}  # <-- Ajout : cache pour les vecteurs
        self._translation_cache = TranslationCache(maxsize=1000, ttl=3600)
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.openai_client_async = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.collection_name = collection_name
        self.client = QdrantClient(
            url=os.getenv('QDRANT_URL'),
            api_key=os.getenv('QDRANT_API_KEY')
        )
        self.id_counter = 202412130001  # Ajout compteur
    def generate_id(self, payload):
        """Génère un ID unique basé sur le contenu"""
        content = f"{payload.get('title', '')}{payload.get('content', '')}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    async def post_traitement_dates(self, resultats, date_debut=None, date_fin=None):
        """
        Post-traitement des résultats avec gestion simplifiée des dates.
        - Conserve tous les résultats si pas de dates spécifiées
        - Gestion souple des erreurs de parsing
        - Maintient les résultats avec dates invalides
        """
        try:
            # Si pas de dates ou pas de résultats, retourner directement triés par score
            if not resultats or (not date_debut and not date_fin):
                return sorted(resultats, key=lambda x: x.score if hasattr(x, 'score') else 0, reverse=True)

            filtered_results = []
            for res in resultats:
                try:
                    # Récupération sécurisée du payload
                    payload = res.payload if isinstance(res.payload, dict) else getattr(res.payload, '__dict__', {})
                    
                    # Récupération de la date (last_updated en priorité)
                    date_value = payload.get('last_updated') or payload.get('created')
                    if date_value is None:
                        date_value = payload.get('last_updated')

                    
                    # Si pas de date, on garde le résultat
                    if not date_value:
                        filtered_results.append(res)
                        continue

                    # Parsing simple de la date
                    try:
                        if isinstance(date_value, (int, float)):
                            date = datetime.fromtimestamp(date_value, tz=timezone.utc)
                        elif isinstance(date_value, str):
                            date = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                        else:
                            # Type de date non géré, on garde le résultat
                            filtered_results.append(res)
                            continue

                        # Filtrage par date si la date est valide
                        if ((not date_debut or date >= date_debut) and 
                            (not date_fin or date <= date_fin)):
                            filtered_results.append(res)
                    except (ValueError, TypeError):
                        # Erreur de parsing de date, on garde le résultat
                        filtered_results.append(res)

                except Exception as e:
                    # Erreur sur un résultat individuel, on le garde
                    self.logger.debug(f"Erreur traitement résultat: {str(e)}")
                    filtered_results.append(res)

            # Tri final par score
            return sorted(filtered_results, key=lambda x: x.score if hasattr(x, 'score') else 0, reverse=True)

        except Exception as e:
            self.logger.error(f"Erreur post_traitement_dates: {str(e)}")
            return sorted(resultats, key=lambda x: x.score if hasattr(x, 'score') else 0, reverse=True)
    def parse_date(self, date_value):
        if isinstance(date_value, int):
            return datetime.fromtimestamp(date_value, tz=timezone.utc)
        elif isinstance(date_value, str):
            try:
                if date_value.isdigit():
                    return datetime.fromtimestamp(float(date_value), tz=timezone.utc)
                return datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            except ValueError:
                self.logger.warning(f"Format de date invalide: {date_value}")
                return None
        return None
    def construire_filtre(self, conditions: dict) -> Filter:
        must_conditions = []
        must_not_conditions = []
        should_conditions = []

        for section, filters in conditions.items():
            if not filters:
                continue
                
            target_list = {
                "must": must_conditions,
                "must_not": must_not_conditions,
                "should": should_conditions
            }.get(section, [])

            for condition in filters:
                if "match" in condition:
                    value = condition["match"]["value"]
                    target_list.append(
                        FieldCondition(
                            key=condition["key"],
                            match=MatchValue(value=str(value or ""))
                        )
                    )

        return Filter(
            must=must_conditions if must_conditions else None,
            must_not=must_not_conditions if must_not_conditions else None,
            should=should_conditions if should_conditions else None
        )
    def _build_search_parameters(self, client_name: Optional[Dict], date_debut: Optional[datetime], date_fin: Optional[datetime]) -> Filter:
        # Initialisation du dictionnaire de conditions
        conditions = {}
        # Ajout du filtre sur le client s'il est défini et non ambigu
        if client_name and not client_name.get("ambiguous"):
            client_value = client_name.get("source", "")
            if client_value:
                conditions.setdefault("must", []).append({
                    "key": "client",
                    "match": {"value": str(client_value)}
                })
        # Ajout des filtres de date si fournis
        if date_debut or date_fin:
            date_range = {}
            if date_debut:
                date_range["gte"] = int(date_debut.timestamp())
            if date_fin:
                date_range["lte"] = int(date_fin.timestamp())
            conditions.setdefault("must", []).append({
                "key": "created",
                "range": date_range
            })
        # Utilisation de la méthode existante pour convertir le dictionnaire en Filter
        return self.construire_filtre(conditions)
    async def format_for_slack(self, result) -> dict:
        try:
            # Extraction du payload et validation des champs essentiels
            payload = self._extract_payload(result)
            if not self._validate_payload(payload):
                return None

            # Normalisation du payload
            normalized = self._normalize_payload(payload)
            if not normalized:
                return None

            # Calcul du score à partir du résultat
            score = self._calculate_score(result)

            # Exécution synchrone de la coroutine _format_message via asyncio.run
            # Cela permet de bloquer jusqu'à obtenir le message formaté
            message = await self._format_message(normalized, score)

            return {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message}
            }
        except Exception as e:
            self.logger.warning(f"Erreur de formatage pour Slack: {str(e)}")
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔸 Résultat trouvé - Erreur de formatage"
                }
            }


    # ---------------------
    # 🔹 Méthodes auxiliaires
    # ---------------------

    def _extract_payload(self, result):
        """ Récupère le payload et le convertit en dictionnaire si nécessaire. """
        if not hasattr(result, 'payload'):
            self.logger.warning("Résultat invalide ou sans payload")
            return None

        return result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})

    def _validate_payload(self, payload):
        # Liste des champs requis pour NetSuite
        required_fields = ['title', 'content', 'url', 'last_updated']
        for field in required_fields:
            if field not in payload or not payload[field]:
                self.logger.warning(f"Payload incomplet : champ manquant '{field}'")
                return False
        return True

    def _normalize_payload(self, payload):
        """ Normalise les données extraites du payload. """
        doc_id = payload.get('id') or self.generate_id(payload)
        title = payload.get('title', '') or payload.get('name', 'Sans titre')
        content = str(payload.get('content', '') or payload.get('text', '') or payload.get('description', 'Pas de contenu'))
        url = payload.get('url', 'URL non disponible')

        if not title or not content or not url:
            self.logger.warning(f"Champs manquants pour doc_id {doc_id}: title={title}, content={content}, url={url}")
            return None

        return {"id": doc_id, "title": title, "content": content, "url": url}

    def _calculate_score(self, result):
        """ Calcule et formate le score de fiabilité. """
        score = round(float(result.score) * 100)
        fiabilite = "🟢" if score > 80 else "🟡" if score > 60 else "🔴"
        return {"score": score, "fiabilite": fiabilite}

    async def _format_message(self, normalized, score_data):
        """ Formate le message Slack avec les données normalisées. """
        try:
            title_fr = await self.traduire_texte(normalized["title"], "fr") if normalized["title"] != 'Sans titre' else normalized["title"]
            content_preview = normalized["content"][:800]
            content_fr = await self.traduire_texte(content_preview, "fr")
            if len(content_fr) > 500:
                cutoff = content_fr[:500].rfind(". ") or content_fr[:500].rfind(" ") or 497
                content_fr = content_fr[:cutoff] + "..."
        except Exception as e:
            self.logger.error(f"Erreur traduction: {str(e)}")
            title_fr, content_fr = normalized["title"], normalized["content"][:500]

        return (
            f"*NETSUITE* - {score_data['fiabilite']} {score_data['score']}%\n"
            f"*Titre:* {title_fr}\n"
            f"*Contenu:* {content_fr}...\n"
            f"*URL:* {normalized['url']}"
        )

    def _format_fallback(self, result):
        """ Retourne un message simplifié en cas d'erreur. """
        try:
            minimal_title = result.payload.get('title', 'Sans titre')[:50] if hasattr(result, 'payload') else 'Sans titre'
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔸 *NETSUITE* - 🔴 Erreur\n{minimal_title}..."
                }
            }
        except Exception as e:
            self.logger.error(f"Erreur lors du formatage du résultat NETSUITE: {str(e)}")
            return {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔸 Résultat trouvé - Erreur de formatage"
                }
            }


    def valider_resultat(self, res) -> bool:
        if not isinstance(res.payload, dict):
            payload = res.payload.__dict__ if hasattr(res.payload, '__dict__') else {}
        else:
            payload = res.payload
        return all(key in payload for key in ['title', 'content', 'url'])
    async def _enrich_question(self, question: str) -> str:
        """Désactivation de la fonction pour accéler la fonction. 
        try:
            # Envelopper l'appel OpenAI avec un timeout explicite de 15s
            response = await asyncio.wait_for(
                self.openai_client_async.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Enrichis cette question avec termes techniques ERP"},
                        {"role": "user", "content": question}
                    ],
                    temperature=0.1
                ),
                timeout=5  # Timeout spécifique pour l'enrichissement
            )
            return response.choices[0].message.content.strip()
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # En cas de timeout ou d'annulation, log et renvoyer la question d'origine
            self.logger.error("Timeout lors de l'enrichissement de la question")
            return question
        except Exception as e:
            self.logger.error(f"Erreur enrichissement: {str(e)}")
            return question  # Retourner la question non enrichie en cas d'erreur"""
        return question

    async def recherche_intelligente(self, question: str, client_name: Optional[Dict] = None, 
                                     date_debut: Optional[datetime] = None, 
                                     date_fin: Optional[datetime] = None) -> List[Any]:
        # Timeout dynamique selon la complexité de la question
        timeout = 10 if any(kw in question.lower() for kw in 
                ['configuration', 'paramétrage', 'workflow']) else 15

        async with asyncio.timeout(timeout):
            async with QdrantSessionManager(self.client) as _:
                try:
                    # Mise en cache avec clé composite
                    cache_key = hashlib.md5(
                        f"{question}_{client_name}_{date_debut}_{date_fin}".encode()
                    ).hexdigest()

                    if cache_key in self._cache:
                        self.logger.info(f"Résultat trouvé en cache pour {cache_key}")
                        return self._cache[cache_key]

                    # Suppression du timeout interne redondant
                    vector = await self._get_search_vector(question)
                    if not vector:
                        self.logger.error("Échec génération vecteur")
                        return []

                    # Construction du filtre et exécution de la recherche
                    query_filter = self._build_search_parameters(client_name, date_debut, date_fin)
                    results = await self._execute_paginated_search(
                        query_vector=vector,
                        query_filter=query_filter,
                        batch_size=10,
                        max_results=50
                    )

                    # Post-traitement et mise en cache
                    processed_results = self._process_search_results(results)
                    self._cache[cache_key] = processed_results
                    return processed_results

                except asyncio.TimeoutError:
                    self.logger.error("Timeout recherche après 15s")
                    return []
                except Exception as e:
                    self.logger.error(f"Erreur recherche: {str(e)}")
                    return []

    async def _get_search_vector(self, question: str) -> Optional[List[float]]:
        """Génère le vecteur de recherche avec enrichissement si nécessaire."""
        try:
            # Enrichissement conditionnel
            if any(term in question.lower() for term in ['paramétrer', 'configurer', 'workflow']):
                question = await self._enrich_question(question)

            # Génération embedding avec cache
            vector_key = hashlib.md5(question.encode()).hexdigest()
            return await self._get_cached_vector(vector_key) or await self.obtenir_embedding(question)
        except Exception as e:
            self.logger.error(f"Erreur vecteur: {str(e)}")
            return None

    async def _execute_paginated_search(self, query_vector: List[float], query_filter: Dict,
                                        batch_size: int = 10, max_results: int = 50) -> List[Any]:
        results = []
        offset = 0

        while len(results) < max_results:
            # Exécution de la recherche dans un thread pour éviter le blocage
            batch = await asyncio.to_thread(
                self.client.search,
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=batch_size,
                offset=offset
            )

            if not batch:
                break

            results.extend(batch)
            offset += batch_size

        return results[:max_results]


    def _process_search_results(self, results: List[Any]) -> List[Any]:
        """Post-traitement: déduplication et tri des résultats."""
        seen = {}
        for result in results:
            if not hasattr(result, 'score') or result.score < 0.45:
                continue
                
            content_hash = hashlib.md5(
                str(getattr(result.payload, 'content', '')).encode()
            ).hexdigest()
            
            if content_hash not in seen or result.score > seen[content_hash].score:
                seen[content_hash] = result
                
        return sorted(seen.values(), key=lambda x: x.score, reverse=True)[:3]
    # Méthodes utilitaires à ajouter
    async def _build_query_filter(self, client_name, date_debut, date_fin):
        """Construit le filtre de requête."""
        must_conditions = []
        
        if client_name and not client_name.get("ambiguous"):
            if isinstance(client_name, dict):
                client_value = client_name.get("source", "")
                if client_value:
                    must_conditions.append(
                        FieldCondition(
                            key="client",
                            match=MatchValue(value=str(client_value))
                        )
                    )

        if date_debut or date_fin:
            date_range = Range()
            if date_debut:
                date_range.gte = int(date_debut.timestamp())
            if date_fin:
                date_range.lte = int(date_fin.timestamp())
            must_conditions.append(
                FieldCondition(key="created", range=date_range)
            )

        return Filter(must=must_conditions) if must_conditions else Filter()

    def _generate_content_hash(self, result) -> str:
        """Génère un hash unique pour la déduplication."""
        content = str(result.payload.get('content', ''))[:500]
        return hashlib.md5(content.encode('utf-8', errors='ignore')).hexdigest()

    def _get_result_score(self, result) -> float:
        """Calcule le score final d'un résultat."""
        base_score = float(result.score if hasattr(result, 'score') else 0)
        bonus = 0
        
        # Bonus pour résultats récents
        created = self._get_result_date(result)
        if created:
            days_old = (datetime.now(timezone.utc) - created).days
            if days_old <= 30:
                bonus = 0.1
            elif days_old <= 90:
                bonus = 0.05
                
        return min(1.0, base_score + bonus)

    def _get_result_date(self, result) -> Optional[datetime]:
        """Extrait la date d'un résultat."""
        try:
            payload = result.payload if isinstance(result.payload, dict) else result.payload.__dict__
            date_str = payload.get('created')
            if not date_str:
                return None
                
            if isinstance(date_str, (int, float)):
                return datetime.fromtimestamp(date_str, tz=timezone.utc)
            elif isinstance(date_str, str):
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                
            return None
        except Exception:
            return None

    async def interface_utilisateur(self):
        while True:
            question = input("\nPosez votre question sur la documentation NetSuite (ou 'q' pour quitter) : ")
            if question.lower() == 'q':
                break
                
            try:
                resultats = await self.recherche_intelligente(question)
                print("\nRésultats trouvés :")
                # Une seule boucle qui combine traduction et affichage
                for idx, res in enumerate(resultats, 1):
                    score = round(res.score * 100)  # Conversion en pourcentage
                    fiabilite = "🟢" if score > 80 else "🟡" if score > 60 else "🔴"
                    if not isinstance(res.payload, dict):  
                        payload = res.payload.__dict__
                    else:
                        payload = res.payload
                    title = await self.traduire_texte(payload['title'], "fr")  # Déplacer ici
                    content = await self.traduire_texte(payload['content'][:500], "fr")
                    
                    print(f"\n{idx}. {title} - Pertinence: {fiabilite} {score}%")
                    print(f"Dernière mise à jour: {payload['last_updated'][:10]}")
                    print(f"Contenu: {content}...")
                    print(f"URL: {payload['url']}")
                    
            except Exception as e:
                print(f"Erreur : {str(e)}")


    def recherche_avec_filtres(self, query_vector, filtres: dict, limit=5):
        conditions = [
            FieldCondition(
                key=key,
                match=MatchValue(value=value)
            )
            for key, value in filtres.items()
        ]
        
        try:
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=Filter(
                    must=conditions
                ),
                limit=limit
            )
            return resultats
        except Exception as e:
            print(f"Erreur lors de la recherche filtrée: {str(e)}")
            return []

    def obtenir_info_collection(self):
        try:
            return self.client.get_collection(self.collection_name)
        except Exception as e:
            print(f"Erreur lors de la récupération des informations: {str(e)}")
            return None
    async def _get_cached_vector(self, key: str) -> Optional[List[float]]:
        """Récupère un vecteur du cache s'il existe."""
        try:
            return self._vector_cache.get(key)
        except Exception as e:
            self.logger.error(f"Erreur accès cache vecteur: {str(e)}")
            return None
    
    async def _cache_vector(self, key: str, vector: List[float]):
        """Stocke un vecteur dans le cache."""
        try:
            self._vector_cache[key] = vector
        except Exception as e:
            self.logger.error(f"Erreur stockage cache vecteur: {str(e)}")
class TranslationCache:
    def __init__(self, maxsize: int = 1000, ttl: int = 3600):
        self._cache = {}
        self._maxsize = maxsize
        self._ttl = ttl
        self._access_times = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            if key not in self._cache:
                return None
            if time.monotonic() - self._access_times[key] > self._ttl:
                del self._cache[key]
                del self._access_times[key]
                return None
            return self._cache[key]

    async def set(self, key: str, value: str):
        async with self._lock:
            if len(self._cache) >= self._maxsize:
                oldest = min(self._access_times.items(), key=lambda x: x[1])[0]
                del self._cache[oldest]
                del self._access_times[oldest]
            self._cache[key] = value
            self._access_times[key] = time.monotonic()

    def _is_expired(self, key: str) -> bool:
        return time.monotonic() - self._access_times.get(key, 0) > self._ttl

    async def _evict_old_entries(self):
        current_time = time.monotonic()
        expired = [k for k, t in self._access_times.items() 
                  if current_time - t > self._ttl]
        for key in expired:
            del self._cache[key]
            del self._access_times[key]

        if len(self._cache) >= self._maxsize:
            sorted_keys = sorted(self._access_times.items(), key=lambda x: x[1])
            to_remove = sorted_keys[:len(self._cache) // 4]
            for key, _ in to_remove:
                del self._cache[key]
                del self._access_times[key]


if __name__ == "__main__":
    netsuite = QdrantNetsuiteSearch()
    netsuite.interface_utilisateur()