# qdrant_netsuite_dummies.py

import os
import logging
import asyncio

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from dotenv import load_dotenv
from openai import OpenAI
from openai import AsyncOpenAI
import hashlib
from typing import Optional, Dict
from datetime import datetime, timezone

from qdrant_jira import BaseQdrantSearch
from qdrant_netsuite import TranslationMixin
from base_de_donnees import QdrantSessionManager
# Niveau de log cohérent :

class SimpleQdrantSearch(BaseQdrantSearch):
    # Pour SAP & NETSUITE_DUMMIES
    pass
class QdrantNetsuiteDummiesSearch(TranslationMixin, SimpleQdrantSearch):
    def __init__(self, collection_name=None):
        load_dotenv()
        self.logger = logging.getLogger(__name__)
        super().__init__(collection_name)

        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.openai_client_async = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.collection_name = collection_name
        self.client = QdrantClient(
            url=os.getenv('QDRANT_URL'),
            api_key=os.getenv('QDRANT_API_KEY')
        )
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
    async def format_for_slack(self, result) -> dict:
        try:
            if not result:
                self.logger.warning("Résultat nul")
                return {}
                
            if not hasattr(result, 'payload'):
                self.logger.warning("Résultat sans payload")
                return {}
                
            normalized_result = self._normalize_result_for_slack(result)
            if not normalized_result:
                return {}

            payload = result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})
            # Assurez-vous que payload est un dictionnaire
            if not isinstance(result.payload, dict):
                payload = getattr(result.payload, '__dict__', {})
            else:
                payload = result.payload

            # Complétez les champs manquants
            if 'id' not in payload:
                # Par exemple, vous pouvez générer un id ou utiliser une valeur par défaut
                payload['id'] = self.generate_id(payload) if hasattr(self, 'generate_id') else 'N/A'
            if 'title' not in payload:
                payload['title'] = 'Sans titre'
            # Si 'text' n'est pas présent, essayez d'utiliser 'content'
            if 'text' not in payload:
                payload['text'] = payload.get('content', 'Pas de contenu')
            # Pour 'pdf_path', fournissez un chemin par défaut si nécessaire
            if 'pdf_path' not in payload:
                payload['pdf_path'] = "data/Netsuite_Dummies/NetSuiteForDummies.pdf"

            if not result or not hasattr(result, 'score') or result.score < 0.4:
                return {}
                    
            score = round(float(result.score) * 100)
            fiabilite = "🟢" if score > 80 else "🟡" if score > 60 else "🔴"
            
            # Construction du message avec gestion robuste
            # doc_id est conservé pour compatibilité avec des développements futurs
            # et pour maintenir la structure de données cohérente avec les autres modules
            _ = payload.get('id', 'N/A')  # Anciennement doc_id, gardé en commentaire pour référence
            content = str(payload.get('text', 'Pas de contenu'))
            title = payload.get('title', 'Sans titre')
            pdf_path = "data/Netsuite_Dummies/NetSuiteForDummies.pdf"
            
            # Traduction avec gestion d'erreur
            try:
                title_fr = self.traduire_texte_sync(title, "fr")
                content_preview = content[:800]  # Augmenté pour tenir compte de la traduction qui peut être plus longue
                content_fr = self.traduire_texte_sync(content_preview, "fr")
                if len(content_fr) > 500:  # On garde une marge de sécurité
                    cutoff = content_fr[:500].rfind(". ")
                    if cutoff == -1:
                        cutoff = content_fr[:500].rfind(" ")
                    if cutoff == -1:
                        cutoff = 497
                    content_fr = content_fr[:cutoff] + "..."
            except Exception as e:
                self.logger.error(f"Erreur traduction: {str(e)}")
                title_fr = title
                content_fr = content[:500]
            
            source_prefix = "DUMMIES"
            message = (
                f"*{source_prefix}* - {fiabilite} {score}%\n"
                f"*Titre:* {title_fr}\n"
                f"*Contenu:* {content_fr}...\n"
                f"*Document:* {pdf_path}"
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
                    "text": "*{}* - ❌ Erreur de formatage".format(source_type.upper())
                }
            }

    def valider_resultat(self, res) -> bool:
        if not isinstance(res.payload, dict):
            return False
        return all(key in res.payload for key in ['id', 'title', 'text', 'pdf_path'])
    async def recherche_intelligente(self, question: str, client_name: Optional[Dict] = None, date_debut: Optional[datetime] = None, date_fin: Optional[datetime] = None):
        async with QdrantSessionManager(self.client) as session_manager:
            try:
        
                try:
                    # Ajout d'un timeout plus court pour le traitement global
                    async with asyncio.timeout(15):  
                        self.logger.debug(f"Début de la recherche: {question}")
                        
                        # Instance du client Qdrant avec la collection courante
                        qdrant_client = QdrantClient(
                            url=os.getenv('QDRANT_URL'),
                            api_key=os.getenv('QDRANT_API_KEY')
                        )

                        # Traduction de la question en anglais
                        question_originale = question
                        # Enrichissement de la question via GPT
                        try:
                            enrichment_prompt = """Tu es un expert ERP. Enrichis cette question pour la recherche vectorielle.
                            Règles:
                            1. Ajoute les termes techniques exacts en anglais
                            2. Inclus les paramètres et configurations associés
                            3. Ajoute les concepts liés essentiels
                            4. Garde la formulation claire et précise
                            Original: {question}
                            Retourne uniquement la question enrichie."""

                            response = await self.openai_client_async.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "system", "content": enrichment_prompt},
                                        {"role": "user", "content": question}],
                                temperature=0.1
                            )
                            question_enrichie = response.choices[0].message.content.strip()
                            self.logger.info(f"Question enrichie: {question_enrichie}")
                            question = question_enrichie
                        except Exception as e:
                            self.logger.warning(f"Erreur enrichissement question: {str(e)}")
                            question = question_originale
                        if not any(mot in question_originale.lower() for mot in ["select", "from", "where", "join"]):
                            question = await self.traduire_texte(question_originale, "en") if not any(mot in question_originale.lower() for mot in ["select", "from", "where", "join"]) else question_originale
                            self.logger.info(f"Question traduite: {question}")

                        
                        try:
                            question = await self.traduire_texte(question_originale, "en") if not any(mot in question_originale.lower() for mot in ["select", "from", "where", "join"]) else question_originale
                            self.logger.info(f"Question traduite: {question}")
                        except Exception as e:
                            self.logger.error(f"Erreur traduction: {str(e)}")
                            question = question_originale  # Fallback sur question originale
                        # Obtention de l'embedding
                        try:
                            vector = await self.obtenir_embedding(question)
                            self.logger.info(f"Embedding obtenu: {len(vector)} dimensions")
                        except Exception as e:
                            self.logger.error(f"Erreur embedding: {str(e)}")
                            return []

                        # Construction du filtre
                        try:
                            filtres = {"must": [], "must_not": [], "should": []}
                            query_filter = self.construire_filtre(filtres)
                        except Exception as e:
                            self.logger.error(f"Erreur construction filtre: {str(e)}")
                            query_filter = Filter()

                        # Recherche Qdrant
                        try:
                            resultats = qdrant_client.search(
                                collection_name=self.collection_name,
                                query_vector=vector,
                                query_filter=query_filter,
                                limit=3
                            )
                            # Attribution sécurisée du type de source
                            if resultats:
                                for result in resultats:
                                    self.set_source_type(result, self.collection_name)
                                    
                            self.logger.info(f"Résultats bruts: {len(resultats)}")

                        except Exception as e:
                            self.logger.error(f"Erreur recherche Qdrant: {str(e)}")
                            return []

                        # Traitement des résultats
                        try:
                            # Génération des IDs si manquants
                            for res in resultats:
                                if not isinstance(res.payload, dict):
                                    res.payload = res.payload.__dict__ if hasattr(res.payload, '__dict__') else {}
                                if 'id' not in res.payload:
                                    res.payload['id'] = self.generate_id(res.payload)

                            # Filtrage par score
                            resultats_scores = [r for r in resultats if hasattr(r, 'score') and r.score >= 0.45]
                            if not resultats_scores:
                                self.logger.info("Aucun résultat avec score suffisant")
                                return []

                            # Déduplication avec conservation du meilleur score
                            seen_contents = {}
                            for res in resultats_scores:
                                text_content = res.payload.get('text', '') or res.payload.get('content', '')
                                content_hash = hashlib.md5(str(text_content)[:500].encode()).hexdigest()
                                if content_hash not in seen_contents or res.score > seen_contents[content_hash].score:
                                    seen_contents[content_hash] = res

                            # Post-traitement des dates si nécessaire
                            if date_debut or date_fin:
                                resultats_dedupliques = await self.post_traitement_dates(list(seen_contents.values()), date_debut, date_fin)
                            else:
                                resultats_dedupliques = list(seen_contents.values())

                            # Tri final et limitation
                            resultats_tries = sorted(resultats_dedupliques, key=lambda x: x.score, reverse=True)[:5]
                            self.logger.info(f"Résultats finaux: {len(resultats_tries)}")

                            return resultats_tries

                        except Exception as e:
                            self.logger.error(f"Erreur traitement résultats: {str(e)}")
                            # En cas d'erreur, on renvoie les résultats bruts filtrés par score
                            return sorted([r for r in resultats if hasattr(r, 'score') and r.score >= 0.45], 
                                        key=lambda x: x.score, reverse=True)[:5]

                except Exception as e:
                    self.logger.error(f"Erreur globale recherche_intelligente: {str(e)}")
                    return []
            finally:
                await session_manager.cleanup()

    async def interface_utilisateur(self):
        while True:
            question = input("\nPosez votre question sur les exemples NetSuite (ou 'q' pour quitter) : ")
            if question.lower() == 'q':
                break
                
            try:
                resultats = await self.recherche_intelligente(question)
                print("\nRésultats trouvés :")
                if resultats and len(resultats) > 0:
                    premier_resultat = resultats[0]
                    if not isinstance(premier_resultat.payload, dict):
                        payload = premier_resultat.payload.__dict__
                    else:
                        payload = premier_resultat.payload
                        
                    for idx, res in enumerate(resultats, 1):
                        score = round(res.score * 100)
                        fiabilite = "🟢" if score > 65 else "🟡" if score > 45 else "🔴"
                        title = await self.traduire_texte(payload['title'], "fr")
                        text = await self.traduire_texte(payload['text'][:500], "fr")
                        print(f"\n{idx}. {title} - Pertinence: {fiabilite} {score}%")
                        print(f"ID: {payload['id']}")
                        print(f"Contenu: {text}...")
                        if payload['pdf_path']:
                            print(f"PDF: {payload['pdf_path']}")
                    
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

if __name__ == "__main__":
    netsuite_dummies = QdrantNetsuiteDummiesSearch()
    netsuite_dummies.interface_utilisateur()