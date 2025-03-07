# qdrant_zendesk.py

import json
import logging
import asyncio
import hashlib

from qdrant_client.http.models import Filter
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, Range

from qdrant_jira import BaseQdrantSearch
from configuration import logger, MAX_SEARCH_RESULTS
from base_de_donnees import SessionLocal, QdrantSessionManager
class QdrantZendeskSearch(BaseQdrantSearch):
    def __init__(self, collection_name=None):
        self.logger = logging.getLogger('ITS_HELP.qdrant.zendesk')
        self.logger.propagate = False  # Évite la duplication des logs
        self.logger.setLevel(logging.INFO)
        super().__init__(collection_name)
    required_fields = ['id', 'client', 'content']  # Champs minimaux essentiels
    optional_fields = ['ticket_id', 'erp', 'status', 'assignee', 'summary', 'url', 'created', 'updated']
    async def format_for_slack(self, result) -> dict:
        """
        Formate les données pour Slack en normalisant les champs requis,
        en validant les données et en gérant les exceptions.
        """
        try:
            # Extraction sécurisée du payload
            if isinstance(result, dict):
                payload = result.get('payload', {})
                score = float(result.get('score', 0.0))
            else:
                payload = result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})
                score = float(getattr(result, 'score', 0.0))

            # Normalisation des champs
            normalized_payload = {
                # On inverse la priorité pour s'appuyer d'abord sur ticket_id si présent
                'ticket_id': str(payload.get('ticket_id') or payload.get('id', '')),
                'client': str(payload.get('client', '')),
                'summary': str(payload.get('summary') or payload.get('title', '')),
                'content': str(payload.get('content') or payload.get('description', ''))
            }

            # Validation des champs obligatoires (exemple : on exige seulement ticket_id et content)
            mandatory_fields = ['ticket_id', 'content']
            if not all(normalized_payload[f] for f in mandatory_fields):
                missing_fields = [f for f in mandatory_fields if not normalized_payload[f]]
                self.logger.warning(f"Champs obligatoires manquants ou vides: {missing_fields}")
                return {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*ZENDESK* - Données insuffisantes pour afficher ce résultat"
                    }
                }

            # Formatage des dates
            created_str, updated_str = self._format_dates(payload)

            # Calcul du score et fiabilité
            score_percent = round(score * 100)
            fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

            # Nettoyage et troncature des contenu

            content = str(payload.get('content', ''))
            if len(content) > 800:
                content = content[:797] + "..."

            # Construction du message
            message = (
                f"*ZENDESK-{normalized_payload['ticket_id']} - {normalized_payload['summary']}\n"
                f"Client: {normalized_payload['client']} - {fiabilite} {score_percent}%\n"
                f"Status: {payload.get('status', 'En cours')}\n"
                f"Agent: {payload.get('assignee', 'Non assigné')}\n"
                f"Créé le: {created_str} - Maj: {updated_str}\n"
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



    def _validate_required_fields(self, payload: dict) -> bool:
        """Valide la présence des champs requis"""
        required_fields = ['ticket_id', 'erp','client', 'summary', 'content', 'status', 'assignee', 'url']
        missing = [f for f in required_fields if not payload.get(f)]
        if missing:
            self.logger.warning(f"Champs manquants: {missing}")
            return False
        return True

    def _validate_erp_field(self, payload: dict) -> str:
        """Valide et nettoie le champ ERP."""
        erp = payload.get('erp')
        if not erp:
            # Tentative de récupération depuis company_name
            erp = payload.get('company_name', 'N/A')
            if erp != 'N/A':
                # Si on a un company_name, on vérifie s'il contient une indication ERP
                erp_keywords = ['netsuite', 'sap']
                for keyword in erp_keywords:
                    if keyword.lower() in erp.lower():
                        return keyword.upper()
        return str(erp) if erp else 'N/A'
    def normalize_client_name(self, client_name: str) -> str:
        return client_name.strip().upper() if client_name else ""
    async def post_traitement_dates(self, resultats, date_debut=None, date_fin=None, is_general_query: bool = False):
        """
        Post-traitement des résultats avec gestion des dates et des questions générales.
        
        Args:
            resultats: Liste des résultats à traiter
            date_debut: Date de début optionnelle
            date_fin: Date de fin optionnelle
            is_general_query: Indique si la requête est générale (sans client/date spécifique)
        """
        try:
            if not resultats:
                return []
                
            filtered_results = []
            seen_contents = {}  # Pour la déduplication
            
            for res in resultats:
                try:
                    payload = res.payload if isinstance(res.payload, dict) else res.payload.__dict__
                    created = payload.get('created')
                    # Seuil de score différent selon le type de requête
                    min_score_threshold = 0.35 if is_general_query else 0.45
                    if hasattr(res, 'score') and res.score < min_score_threshold:
                        continue

                    # Gestion des dates si requête non générale
                    if not is_general_query:
                        try:
                            # Created date - Amélioration du parsing des dates
                            created = payload.get('created')
                            if isinstance(created, (int, float)):
                                created_date = datetime.fromtimestamp(created, tz=timezone.utc)

                            elif isinstance(created, str):
                                try:
                                    created_date = datetime.fromisoformat(created.replace('Z', '+00:00'))

                                except ValueError:
                                    # Tentative de parsing avec différents formats
                                    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                                        try:
                                            created_date = datetime.fromisoformat(created.replace('Z', '+00:00'))

                                            break
                                        except ValueError:
                                            continue
                                    else:
                                        self.logger.warning(f"Format de date created non reconnu: {created}")
                                        continue
                            else:
                                self.logger.warning(f"Format de date created invalide: {created}")
                                continue
                                
                            # Updated date
                            updated = payload.get('updated')
                            if isinstance(updated, (int, float)):
                                updated_date = datetime.fromtimestamp(updated, tz=timezone.utc)


                            elif isinstance(updated, str):
                                try:
                                    updated_date = datetime.fromisoformat(updated.replace('Z', '+00:00'))


                                except ValueError:
                                    updated_date = created_date
                            else:
                                updated_date = created_date

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
                            res.payload['_updated_date'] = updated_date
                            
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"Erreur conversion date: {str(e)}")
                            continue

                    # Déduplication avec gestion spécifique pour requêtes générales
                    dedup_key = hashlib.md5(
                        f"{payload.get('content', '')}{'' if is_general_query else payload.get('client', '')}".encode()
                    ).hexdigest()
                    
                    # Ajustement du score pour les requêtes générales
                    if is_general_query:
                        # Bonus pour les tickets récents en mode général
                        score_bonus = 0
                        if hasattr(res, 'score'):
                            try:
                                days_old = (datetime.now(timezone.utc) - created_date).days
                                if days_old <= 30:
                                    score_bonus = 0.1
                                elif days_old <= 90:
                                    score_bonus = 0.05
                                res.score = min(1.0, res.score + score_bonus)
                            except:
                                pass

                    # Conservation du meilleur score pour un même contenu
                    if dedup_key in seen_contents:
                        if res.score > seen_contents[dedup_key].score:
                            seen_contents[dedup_key] = res
                    else:
                        seen_contents[dedup_key] = res
                        
                except Exception as e:
                    self.logger.warning(f"Erreur traitement résultat: {str(e)}")
                    continue

            # Conversion du dictionnaire en liste et tri
            filtered_results = list(seen_contents.values())

            # Tri avec critères adaptés selon le type de requête
            if is_general_query:
                # Pour les requêtes générales, favoriser aussi la récence
                sorted_results = sorted(
                    filtered_results,
                    key=lambda x: (
                        -x.score if hasattr(x, 'score') else 0,
                        getattr(getattr(x, 'payload', {}), 'created', '2000-01-01')
                    ),
                    reverse=True
                )
                limit = 10  # Plus de résultats pour les requêtes générales
            else:
                # Tri standard par score pour les requêtes spécifiques
                sorted_results = sorted(filtered_results, 
                                    key=lambda x: (-x.score if hasattr(x, 'score') else 0))
                limit = 3

            # Logging adapté
            if is_general_query:
                self.logger.info(f"Mode requête générale: {len(sorted_results)}/{len(resultats)} résultats uniques")
            elif date_debut or date_fin:
                self.logger.info(f"Filtrage temporel: {len(sorted_results)}/{len(resultats)} résultats")
                self.logger.info(f"Période: {date_debut or 'début'} → {date_fin or 'fin'}")
            else:
                self.logger.info(f"Mode standard: {len(sorted_results)} résultats uniques")

            return sorted_results[:limit]

        except Exception as e:
            self.logger.error(f"Erreur post-traitement dates: {str(e)}")
            return sorted(resultats, key=lambda x: -x.score if hasattr(x, 'score') else 0)[:3]
    async def recherche_intelligente(self, question: str, client_name: Optional[Dict] = None, date_debut: Optional[datetime] = None, date_fin: Optional[datetime] = None):
        async with QdrantSessionManager(self.client) as session_manager:
            try:            
                try:
                    if not question:
                        self.logger.error("Question vide")
                        return []

                    self.logger.info(f"=== Début recherche Zendesk ===")
                    self.logger.info(f"Question: {question}")
                    self.logger.info(f"Client info: {client_name}")
                    
                    # Construction des filtres avec client_name et dates
                    must_conditions = []
                    
                    if client_name and not client_name.get("ambiguous"):
                        if isinstance(client_name, dict):
                            client_value = client_name.get("source", "")
                            self.logger.info(f"Client_Value: {client_value}")
                            if client_value:
                                must_conditions.append(
                                    FieldCondition(
                                        key="client",
                                        match=MatchValue(value=str(client_value))
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
                    
                    # Le reste de la fonction reste identique
                    filtres = self.validate_filters({})
                    limit = 500
                    requete_optimisee = question

                    # Optimisation de la requête
                    try:
                        requete_optimisee, nouveaux_filtres, limit = await self.optimiser_requete(question)
                        self.logger.info(f"Requête optimisée: {requete_optimisee}")
                    except Exception as e:
                        self.logger.error(f"Erreur optimisation requête: {str(e)}")

                    # Génération de l'embedding
                    try:
                        async with asyncio.timeout(30):
                            self.logger.info("Génération de l'embedding...")
                            vector = await self.obtenir_embedding(requete_optimisee)
                            self.logger.info(f"Embedding obtenu de taille: {len(vector)}")
                    except Exception as e:
                        self.logger.error(f"Erreur embedding: {str(e)}")
                        return []

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
                            resultats = self.client.search(
                                collection_name=self.collection_name,
                                query_vector=vector,
                                query_filter=query_filter,
                                limit=limit
                            )
                            self.logger.info(f"Résultats bruts: {len(resultats)} trouvés")

                            if resultats:
                                scores = [f"{round(r.score * 100)}%" for r in resultats[:3]]
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
                                payload = res.payload.__dict__ if not isinstance(res.payload, dict) else res.payload
                                content_hash = hashlib.md5(str(payload.get('content', '')).encode()).hexdigest()
                                if content_hash not in seen:
                                    seen.add(content_hash)
                                    resultats_dedupliques.append(res)

                            # Tri final et limitation
                            resultats_finaux = sorted(
                                resultats_dedupliques,
                                key=lambda x: (
                                    # Premier critère : date de création
                                    datetime.fromisoformat(x.payload.get('created', '2000-01-01')).replace(tzinfo=timezone.utc)
                                    if isinstance(x.payload.get('created'), str)
                                    else datetime.fromtimestamp(x.payload.get('created', 0), tz=timezone.utc),
                                    # Deuxième critère : score
                                    x.score if hasattr(x, 'score') else 0
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
                await session_manager.cleanup()    
    def valider_resultat(self, res) -> bool:
        """
        Valide un résultat de recherche selon des critères spécifiques :
        - Vérifie la présence des attributs 'payload' et 'score'.
        - Normalise les champs requis si nécessaire.
        - Valide les champs obligatoires dans le payload.
        - Vérifie si le score atteint un seuil minimum.
        """
        try:
            # Validation initiale des attributs essentiels
            if not res or not hasattr(res, 'payload') or not hasattr(res, 'score'):
                self.logger.debug("Résultat invalide ou sans score")
                return False

            # Extraction sécurisée du payload avec gestion des différents formats
            if isinstance(res.payload, dict):
                payload = res.payload
            else:
                payload = res.payload.__dict__ if hasattr(res.payload, '__dict__') else {}

            # Normalisation des champs avec fallbacks
            normalized_payload = {
                'id': str(payload.get('id') or payload.get('ticket_id', '')),
                'ticket_id': str(payload.get('ticket_id') or payload.get('id', '')),
                'content': str(payload.get('content') or payload.get('description', '')),
                'client': str(payload.get('client', '')),
                'status': str(payload.get('status', 'En cours')),
                'assignee': str(payload.get('assignee', 'Non assigné'))
            }

            # Validation avec seuils plus souples
            mandatory_fields = ['ticket_id', 'content']  # Utiliser ticket_id au lieu de id
            if not normalized_payload.get('ticket_id') or not normalized_payload.get('content'):
                return False  # Vérification simplifiée

            return res.score >= 0.4

        except Exception as e:
            self.logger.error(f"Erreur validation résultat: {str(e)}")
            return False




    def _format_dates(self, payload: Dict) -> Tuple[str, str]:
        """Formate les dates avec validation renforcée."""
        try:
            created = payload.get('created')
            updated = payload.get('updated')
            
            def format_date(date_value):
                if isinstance(date_value, (int, float)):
                    try:
                        return datetime.fromtimestamp(date_value, tz=timezone.utc).strftime("%Y-%m-%d")
                    except (ValueError, OSError):
                        return 'N/A'
                elif isinstance(date_value, str):
                    try:
                        dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        return date_value[:10] if date_value else 'N/A'
                return 'N/A'

            return (format_date(created), format_date(updated))
                
        except Exception as e:
            self.logger.error(f"Erreur formatage dates: {str(e)}", exc_info=True)
            return ('N/A', 'N/A')
    async def interface_utilisateur(self):
        while True:
            question = input("\nPosez votre question sur Zendesk (ou 'q' pour quitter) : ")
            if question.lower() == 'q':
                break
                
            try:
                resultats = await self.recherche_intelligente(question)
                print("\nRésultats trouvés :")
                
                for idx, res in enumerate(resultats, 1):
                    # Extraction sécurisée du payload pour le résultat courant 
                    if not isinstance(res.payload, dict): 
                        payload = res.payload.dict 
                    else: 
                        payload = res.payload
                    score = round(res.score * 100)  # Conversion en pourcentage
                    fiabilite = "🟢" if score > 80 else "🟡" if score > 60 else "🔴"
                    print(f"\n{idx}. Ticket #{payload['ticket_id']} - {payload['summary']}")
                    print(f"Client: {payload['client']} - Pertinence: {fiabilite} {score}%")
                    print(f"Status: {payload['status']}")
                    print(f"Agent: {payload['assignee']}")
                    print(f"Créé le: {payload['created'][:10]}")
                    print(f"Description: {res.payload['content'][:500]}...")
                    print(f"URL: {payload['url']}")
                    
            except Exception as e:
                print(f"Erreur : {str(e)}")

class BaseQdrantSearch:
    def validate_payload(self, payload: Dict) -> bool:
        if not isinstance(payload, dict):
            return False
            
        required_fields = self.required_fields
        if not required_fields:
            return True
            
        return all(
            field in payload and 
            payload[field] is not None and 
            str(payload[field]).strip() 
            for field in required_fields
        )
if __name__ == "__main__":
    zendesk = QdrantZendeskSearch()
    zendesk.interface_utilisateur()