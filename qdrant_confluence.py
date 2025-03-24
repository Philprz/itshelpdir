import re
import json
import logging
import asyncio
import hashlib

from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple

from qdrant_jira import BaseQdrantSearch
from configuration import MAX_SEARCH_RESULTS

CONFLUENCE_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%fZ",  # Format ISO avec microsecondes
    "%Y-%m-%dT%H:%M:%SZ",     # Format ISO sans microsecondes 
    "%Y-%m-%d %H:%M:%S",      # Format standard
    "%Y-%m-%d"                # Format date simple
]
class DocumentQdrantSearch(BaseQdrantSearch):
    # Pour CONFLUENCE
    pass

class QdrantConfluenceSearch(DocumentQdrantSearch):

    def __init__(self, collection="CONFLUENCE", collection_name=None):
        # Si collection_name n'est pas précisé, on le définit comme étant la même que collection
        if collection_name is None:
            collection_name = collection
        self.logger = logging.getLogger(__name__)
        super().__init__(collection_name)
        self.collection = collection
        self.logger.info("QdrantConfluenceSearch initialisé avec succès")
    required_fields = ['id', 'summary', 'content', 'page_url', 'created', 'updated', 'client', 'space_id', 'erp', 'assignee']

    def normalize_date(self, date_value) -> Optional[datetime]:
        if not date_value:
            return None
            
        try:
            if isinstance(date_value, (int, float)):
                return datetime.fromtimestamp(date_value, tz=timezone.utc)
                
            if isinstance(date_value, str):
                for fmt in CONFLUENCE_DATE_FORMATS:
                    try:
                        dt = datetime.strptime(date_value, fmt)
                        return dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                        
                self.logger.warning(f"Format de date non reconnu: {date_value}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur normalisation date: {str(e)}")
            return None
        
    def _format_dates(self, payload: Dict) -> Tuple[str, str]:
        try:
            created = payload.get('created')
            updated = payload.get('updated', created)
            
            def format_date(date_value):
                if isinstance(date_value, (int, float)):
                    return datetime.fromtimestamp(date_value, tz=timezone.utc).strftime("%Y-%m-%d")
                elif isinstance(date_value, str):
                    try:
                        return datetime.fromisoformat(date_value.replace('Z', '+00:00')).strftime("%Y-%m-%d")
                    except ValueError:
                        return date_value[:10] if date_value else 'N/A'
                return 'N/A'

            return (format_date(created), format_date(updated))
                    
        except Exception as e:
            self.logger.error(f"Erreur formatage dates: {str(e)}", exc_info=True)
            return ('N/A', 'N/A')

    def _format_date(self, date_value: str) -> str:
        if not date_value or date_value == 'N/A':
            return 'N/A'
        try:
            dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except ValueError as e:
            self.logger.debug(f"Erreur de conversion de date '{date_value}': {str(e)}")
            return date_value[:10] if date_value else 'N/A'
    async def post_traitement_dates(self, resultats, date_debut=None, date_fin=None):
        """Post-traitement des résultats avec gestion des dates."""
        try:
            if not resultats:
                return []
                
            filtered_results = []
            seen_contents = {}  # Pour la déduplication
            
            for res in resultats:
                try:
                    payload = res.payload if isinstance(res.payload, dict) else res.payload.__dict__
                    created = payload.get('created')
                    
                    # Modification ici - utilisation de normalize_date
                    created_date = self.normalize_date(created)
                    if created_date is None:
                        continue

                    # Normalisation des dates pour la comparaison
                    if date_debut:
                        date_debut = date_debut.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                    if date_fin:
                        date_fin = date_fin.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)

                    # Filtrage temporel si dates spécifiées
                    if date_debut and created_date < date_debut:
                        continue
                    if date_fin and created_date > date_fin:
                        continue
                    
                    # Stockage des dates normalisées
                    res.payload['_created_date'] = created_date
                    
                    # Déduplication avec gestion spécifique
                    content_hash = hashlib.md5(str(payload.get('content', ''))[:500].encode()).hexdigest()
                    if content_hash not in seen_contents:
                        seen_contents[content_hash] = res
                    elif res.score > seen_contents[content_hash].score:
                        seen_contents[content_hash] = res
                            
                except Exception as e:
                    self.logger.warning(f"Erreur traitement résultat: {str(e)}")
                    continue

            # Conversion du dictionnaire en liste et tri
            filtered_results = list(seen_contents.values())
            
            # Tri final par score et date
            sorted_results = sorted(
                filtered_results,
                key=lambda x: (
                    -x.score if hasattr(x, 'score') else 0,
                    getattr(x.payload, '_created_date', datetime.min.replace(tzinfo=timezone.utc))
                )
            )
            
            self.logger.info(f"Post-traitement: {len(sorted_results)} résultats uniques")
            return sorted_results

        except Exception as e:
            self.logger.error(f"Erreur post-traitement dates: {str(e)}")
            return sorted(resultats, key=lambda x: -x.score if hasattr(x, 'score') else 0)[:5]
    def valider_resultat(self, res) -> bool:
        try:
            if not res or not hasattr(res, 'payload'):
                return False

            # Extraction sécurisée du payload
            payload = res.payload if isinstance(res.payload, dict) else getattr(res.payload, '__dict__', {})

            # Normalisation adaptée à Confluence
            required_data = {
                'id': payload.get('id') or payload.get('space_id'),
                'content': payload.get('content') or payload.get('text'),
                'summary': payload.get('summary') or payload.get('title'),
                'client': payload.get('client'),
                'space_id': payload.get('space_id')
            }

            # Validation des champs essentiels
            if not all(required_data.get(field) for field in ['id', 'content']):
                return False

            return getattr(res, 'score', 0) >= 0.4

        except Exception as e:
            self.logger.error(f"Erreur validation résultat Confluence: {str(e)}")
            return False


    async def format_for_slack(self, result) -> dict:
        try:
            if isinstance(result, dict):
                payload = result.get('payload', {})
                score = float(result.get('score', 0.0))
            else:
                payload = result.payload if isinstance(result.payload, dict) else result.payload.__dict__
                score = float(getattr(result, 'score', 0.0))

            # Validation des champs requis
            if not all(k in payload for k in ['id', 'summary', 'content']):
                return {}
            # Formatage des dates
            created_str, updated_str = self._format_dates(payload)

            # Calcul score et fiabilité
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

            # Troncature du contenu
            content = str(payload.get('content', ''))
            if len(content) > 800:
                content = content[:797] + "..."

            message = (
                f"*CONFLUENCE-{payload['id']}* - {payload['summary']}\n"
                f"Client: {payload.get('client', 'N/A')} - {fiabilite} {score_percent}%\n"
                f"Créé le: {created_str} - Maj: {updated_str}\n"
                f"Description: {content}\n"
                f"URL: {payload.get('page_url', 'N/A')}"
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

    
    async def recherche_intelligente(self, question: str, client_name: Optional[Dict] = None, 
                                   date_debut: Optional[datetime] = None, 
                                   date_fin: Optional[datetime] = None) -> List:
        """Recherche optimisée dans Confluence avec gestion des erreurs et analyse de pertinence."""
        
        if not question.strip():
            self.logger.error("Question vide")
            return []

        self.logger.info("=== Début recherche Confluence ===")
        
        # Construction des filtres
        must_conditions = []
        if client_name and not client_name.get("ambiguous"):
            client_value = client_name.get("source", "")
            if client_value:
                must_conditions.append({"key": "client", "match": {"value": str(client_value)}})
                self.logger.info(f"Filtre client ajouté: {client_value}")

        if date_debut:
            must_conditions.append({"key": "created", "range": {"gte": int(date_debut.timestamp())}})
        if date_fin:
            must_conditions.append({"key": "created", "range": {"lte": int(date_fin.timestamp())}})

        query_filter = {"must": must_conditions} if must_conditions else {}

        try:
            async with asyncio.timeout(35):  # Timeout géré ici
                # Optimisation de la requête
                try:
                    requete_optimisee = await self._optimiser_requete(question)
                except Exception as e:
                    self.logger.warning(f"Erreur optimisation requête: {e}")
                    requete_optimisee = question

                # Génération de l'embedding
                try:
                    vector = await self.obtenir_embedding(requete_optimisee)
                    if not vector:
                        self.logger.error("Échec génération embedding pour Confluence")
                        return []
                except Exception as e:
                    self.logger.error(f"Erreur génération embedding: {e}")
                    return []

                # Vérification de la collection
                try:
                    collection_info = self.client.get_collection(self.collection_name)
                    self.logger.info(f"Collection trouvée: {collection_info.points_count} points")
                except Exception as e:
                    self.logger.error(f"Erreur accès collection: {e}")
                    return []

                # Exécution de la recherche
                try:
                    results = await self._execute_search(vector, query_filter)
                    if not results:
                        self.logger.info("Aucun résultat Confluence")
                        return []
                except Exception as e:
                    self.logger.error(f"Erreur recherche principale: {e}")
                    return []

                # Filtrage et déduplication
                resultats_valides = [r for r in results if r.score >= 0.45]
                seen = set()
                resultats_dedupliques = []
                for res in resultats_valides:
                    content = str(res.payload.get('content', ''))
                    content_hash = hashlib.md5(content[:500].encode('utf-8', errors='ignore')).hexdigest()
                    if content_hash not in seen:
                        seen.add(content_hash)
                        resultats_dedupliques.append(res)

                # Tri des résultats
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

                # Analyse de pertinence
                try:
                    results_for_analysis = [
                        {
                            'id': res.payload.get('id', 'N/A'),
                            'summary': res.payload.get('summary', 'N/A'),
                            'content': res.payload.get('content', '')[:500]
                        }
                        for res in resultats_finaux[:5]
                    ]
                    relevance_data = await self._analyser_pertinence(results_for_analysis, question)
                    valid_ids = set(relevance_data.keys())
                    resultats_finaux = [res for res in resultats_finaux if res.payload.get('id') in valid_ids]
                except Exception as e:
                    self.logger.warning(f"Erreur analyse pertinence: {e}")

                self.logger.info(f"Recherche terminée avec {len(resultats_finaux)} résultats")
                return resultats_finaux

        except asyncio.TimeoutError:
            self.logger.error("Timeout recherche Confluence")
            return []
        except Exception as e:
            self.logger.error(f"Erreur recherche Confluence: {str(e)}")
            return []

    async def _optimiser_requete(self, question: str) -> str:
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": "Optimise cette question pour la recherche dans Zendesk"
                }, {
                    "role": "user",
                    "content": question
                }],
                temperature=0.1
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"Erreur optimisation requête: {str(e)}")
            return question

    async def _generate_embedding_with_retry(self, text: str, max_retries: int = 3) -> Optional[List[float]]:
        for attempt in range(max_retries):
            try:
                response = self.openai_client.embeddings.create(
                    model="text-embedding-ada-002",
                    input=text
                )
                return response.data[0].embedding
            except Exception as e:
                if attempt == max_retries - 1:
                    self.logger.error(f"Échec génération embedding après {max_retries} tentatives: {str(e)}")
                    return None
                await asyncio.sleep(1)
    def _validate_json_response(self, content: str) -> Optional[dict]:
        """
        Valide et nettoie une réponse JSON avec validation renforcée et gestion d'erreurs exhaustive.
        
        Args:
            content: Le contenu JSON à valider
            
        Returns:
            Optional[dict]: Le dictionnaire JSON nettoyé ou None si invalide
        """
        try:
            # 1. Validation préliminaire
            if not content or not isinstance(content, str):
                self.logger.warning("Contenu JSON invalide ou vide", extra={"content_type": type(content).__name__})
                return None

            # 2. Nettoyage préliminaire avec logging
            content = content.strip()
            self.logger.debug(f"Contenu initial: {content[:100]}...")

            # 3. Gestion des backticks avec validation multiple
            if '```' in content:
                matches = re.findall(r'```(?:json)?(.*?)```', content, re.DOTALL)
                if matches:
                    # On prend le plus long bloc JSON potentiel
                    content = max(matches, key=len).strip()
                    self.logger.debug(f"Extrait des backticks: {content[:100]}...")

            # 4. Extraction JSON stricte avec validation progressive
            json_matches = []
            
            # Pattern pour JSON complet
            full_json = re.search(r'^\s*(\{.*\})\s*$', content, re.DOTALL)
            if full_json:
                json_matches.append(full_json.group(1))
            
            # Si pas de JSON complet, recherche dans le texte
            if not json_matches:
                json_pattern = r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
                json_matches = re.findall(json_pattern, content, re.DOTALL)

            if not json_matches:
                self.logger.warning("Aucun objet JSON valide trouvé dans le contenu")
                return None

            # 5. Tentative de parsing sur chaque match
            valid_jsons = []
            for json_str in json_matches:
                try:
                    data = json.loads(json_str)
                    if isinstance(data, dict):
                        valid_jsons.append(data)
                except json.JSONDecodeError:
                    continue

            if not valid_jsons:
                self.logger.warning("Aucun JSON valide après parsing")
                return None

            # 6. Sélection du JSON le plus pertinent
            data = max(valid_jsons, key=lambda x: len(x))

            # 7. Nettoyage et validation approfondie des valeurs
            cleaned_data = {}
            for key, value in data.items():
                # Validation de la clé
                if not isinstance(key, str):
                    self.logger.warning(f"Clé non-string ignorée: {type(key)}")
                    continue
                    
                # Nettoyage selon le type
                if isinstance(value, str):
                    # Nettoyage strict des chaînes
                    cleaned_value = re.sub(r'[^\w\s.,()-]', '', value)
                    if len(cleaned_value) > 100:
                        cleaned_value = cleaned_value[:97] + "..."
                    cleaned_data[key] = cleaned_value
                elif isinstance(value, (int, float, bool)):
                    # Conservation des valeurs numériques et booléennes
                    cleaned_data[key] = value
                elif value is None:
                    cleaned_data[key] = None
                else:
                    # Conversion en string des autres types
                    cleaned_data[key] = str(value)

            if not cleaned_data:
                self.logger.warning("Données nettoyées vides")
                return None

            self.logger.debug(f"JSON validé et nettoyé avec succès: {len(cleaned_data)} clés")
            return cleaned_data

        except json.JSONDecodeError as e:
            self.logger.warning(f"Erreur décodage JSON: {str(e)}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Erreur inattendue validation JSON: {str(e)}", exc_info=True)
            return None
    async def interface_utilisateur(self):
        while True:
            question = input("\nPosez votre question sur Confluence (ou 'q' pour quitter) : ")
            if question.lower() == 'q':
                break

            try:
                resultats = await self.recherche_intelligente(question)
                print("\nRésultats trouvés :")
                for idx, res in enumerate(resultats, 1):
                    score = round(res.score * 100)  # Conversion en pourcentage
                    fiabilite = "🟢" if score > 80 else "🟡" if score > 60 else "🔴"
                    payload = res.payload if isinstance(res.payload, dict) else res.payload.__dict__
                    print(f"\n{idx}. Page {payload['id']} - {payload['summary']}")
                    print(f"Client: {payload['client']} - Pertinence: {fiabilite} {score}%")
                    print(f"Espace: {payload['space_id']}")
                    print(f"Assigné à: {payload['assignee']}")
                    print(f"Créé le: {payload['created'][:10]}")
                    print(f"Dernière modification: {payload['updated'][:10]}")
                    print(f"Description: {payload['content'][:500]}...")
                    print(f"URL: {payload['url']}")

            except Exception as e:
                print(f"Erreur : {str(e)}")

if __name__ == "__main__":
    confluence = QdrantConfluenceSearch()
    confluence.interface_utilisateur()
    # Fournir la collection requise, par exemple "confluence_collection"
    confluence = QdrantConfluenceSearch(collection="CONFLUENCE", collection_name="CONFLUENCE")
    # Utilisation d'asyncio pour lancer la méthode asynchrone
    asyncio.run(confluence.interface_utilisateur())
