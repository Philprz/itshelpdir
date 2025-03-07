# À renommer en chatbot.py (remplacer le fichier existant)

import os
import re
import json
import asyncio
import logging
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from openai import AsyncOpenAI

from search_factory import search_factory
from gestion_clients import extract_client_name
from base_de_donnees import SessionLocal, Conversation
from configuration import logger, global_cache
from embedding_service import EmbeddingService
from translation_service import TranslationService

class ChatBot:
    """
    Chatbot optimisé avec gestion intelligente des recherches et des réponses.
    Version adaptée pour l'interface web, sans dépendance à Slack.
    """
    
    def __init__(self, openai_key: str, qdrant_url: str, qdrant_api_key: str = None):
        """Initialisation du chatbot avec les clés d'API nécessaires."""
        self.logger = logging.getLogger('ITS_HELP.chatbot')
        self.logger.setLevel(logging.INFO)
        
        # Vérification des clés requises
        if not all([openai_key, qdrant_url]):
            raise ValueError("Les clés OpenAI et l'URL Qdrant sont requises")
            
        # Client OpenAI
        self.openai_client = AsyncOpenAI(api_key=openai_key)
        
        # Initialisation des services
        self.embedding_service = EmbeddingService(self.openai_client, global_cache)
        self.translation_service = TranslationService(None, global_cache)
        self.translation_service.set_async_client(self.openai_client)
        
        # Initialisation du gestionnaire de recherche
        self.search_factory = search_factory
        
        # Collections par défaut
        self.collections = {
            'jira': os.getenv('QDRANT_COLLECTION_JIRA', 'JIRA'),
            'zendesk': os.getenv('QDRANT_COLLECTION_ZENDESK', 'ZENDESK'),
            'confluence': os.getenv('QDRANT_COLLECTION_CONFLUENCE', 'CONFLUENCE'),
            'netsuite': os.getenv('QDRANT_COLLECTION_NETSUITE', 'NETSUITE'),
            'netsuite_dummies': os.getenv('QDRANT_COLLECTION_NETSUITE_DUMMIES', 'NETSUITE_DUMMIES'),
            'sap': os.getenv('QDRANT_COLLECTION_SAP', 'SAP')
        }
        
        # Dictionnaire des consultants (à charger depuis une source de données)
        self.consultant_ids = {}
        
        # Liste des consultants
        self._load_consultants()
        
        self.logger.info("ChatBot initialisé avec succès")
    
    def _load_consultants(self):
        """Charge la liste des consultants depuis un fichier."""
        try:
            file_path = os.path.join(os.path.dirname(__file__), 'PrenomID.txt')
            if os.path.exists(file_path):
                import csv
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if 'Prenom' in row and 'Id_membre' in row:
                            self.consultant_ids[row['Id_membre']] = row['Prenom']
                self.logger.info(f"Total consultants chargés: {len(self.consultant_ids)}")
            else:
                self.logger.warning(f"Fichier consultants {file_path} introuvable")
        except Exception as e:
            self.logger.error(f"Erreur chargement consultants: {str(e)}")
    
    async def is_greeting(self, text: str) -> bool:
        """Détecte si le message est une salutation."""
        # Vérification du cache
        cache_key = f"greeting:{hashlib.md5(text.encode()).hexdigest()}"
        cached = await global_cache.get(cache_key, "analysis")
        if cached is not None:
            return cached == "true"
            
        try:
            resp = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Est-ce une salutation ? Réponds true ou false"},
                    {"role": "user", "content": text}
                ],
                temperature=0.1
            )
            result = resp.choices[0].message.content.strip().lower() == "true"
            await global_cache.set(cache_key, "true" if result else "false", "analysis")
            return result
        except Exception as e:
            self.logger.error(f"Erreur détection salutation: {str(e)}")
            return False
    
    async def analyze_question(self, text: str) -> Dict:
        """
        Analyse le texte de la question pour en extraire le contexte et les paramètres de recherche.
        
        Args:
            text: Texte de la question
            
        Returns:
            Dictionnaire d'analyse structuré
        """
        strict_prompt = """Tu es un expert en analyse de questions de support technique.
            Analyse cette question et retourne un JSON avec ce format précis :
            {
                "type": "support/documentation/configuration",
                "search_context": {
                    "has_client": true/false,
                    "client_name": "Nom du client si présent",
                    "has_temporal": true/false,
                    "temporal_info": {
                        "start_timestamp": timestamp_unix,
                        "end_timestamp": timestamp_unix,
                        "period_type": "exact/range/relative/none",
                        "raw_dates": {
                            "start": "YYYY-MM-DD",
                            "end": "YYYY-MM-DD"
                        }
                    }
                },
                "search_strategy": {
                    "precision_required": "high/medium/low",
                    "priority_sources": ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"],
                    "min_score_threshold": 0.45
                },
                "query": {
                    "original": "question originale",
                    "reformulated": "question reformulée si nécessaire",
                    "semantic_search": true/false
                }
            }"""
            
        try:
            # Ajout d'une analyse locale pour éviter l'erreur
            search_context = {}
            # Modifié pour mieux détecter une référence client
            if search_context.get("has_client"):
                client_name, score, client_details = await extract_client_name(text)
                # Ajout d'une recherche spécifique pour les mots simples
                if not client_name and re.search(r'\b[A-Za-z]{4,}\b', text):
                    potential_clients = re.findall(r'\b[A-Za-z]{4,}\b', text)
                    for potential in potential_clients:
                        test_name, test_score, test_details = await extract_client_name(potential)
                        if test_name:
                            client_name, score, client_details = test_name, test_score, test_details
                            break
            # Détection rapide des catégories
            is_config_request = any(k in text.lower() for k in ['configur', 'paramèt', 'workflow', 'personnalis', 'custom'])
            is_doc_request = any(k in text.lower() for k in ['documentation', 'tutoriel', 'manuel', 'comment faire'])
            is_guide_request = any(k in text.lower() for k in ['guide', 'étape par étape', 'procédure', 'explique'])
            
            # Appel à OpenAI pour analyse complète
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": strict_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                max_tokens=800
            )
            content = response.choices[0].message.content.strip()
            if not content:
                return self._fallback_analysis(text, is_config_request, is_doc_request)
                
            # Tentative de parsing JSON
            analysis = self._validate_gpt_response(content)
            if not analysis:
                return self._fallback_analysis(text, is_config_request, is_doc_request)
                
            # Ajustement en fonction de la détection rapide
            if is_config_request and analysis['type'] != 'configuration':
                analysis['type'] = 'configuration'
                if 'search_strategy' in analysis:
                    analysis['search_strategy']['priority_sources'] = ['netsuite', 'sap', 'netsuite_dummies']
            
            if is_doc_request and analysis['type'] != 'documentation':
                analysis['type'] = 'documentation'
                if 'search_strategy' in analysis:
                    analysis['search_strategy']['priority_sources'] = ['confluence', 'netsuite', 'sap']
                    
            # Définition du mode selon le type de demande
            analysis['mode'] = 'guide' if is_guide_request else 'detail'
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Erreur analyse question: {str(e)}")
            return self._fallback_analysis(text, is_config_request, is_doc_request)
    
    def _fallback_analysis(self, text: str, is_config=False, is_doc=False) -> Dict:
        """Analyse de secours si l'analyse principale échoue."""
        # Détection simple d'un potentiel nom de client
        c_name = None
        m = re.search(r'\b[A-Z0-9]+\b', text.upper())
        if m:
            c_name = m.group(0)
            
        # Définition du type selon la détection rapide
        type_value = "configuration" if is_config else ("documentation" if is_doc else "support")
        
        # Priorité des sources selon le type
        if is_config:
            priority_sources = ["netsuite", "sap", "netsuite_dummies"]
        elif is_doc:
            priority_sources = ["confluence", "netsuite", "sap"]
        else:
            priority_sources = ["jira", "zendesk", "confluence"]
            
        return {
            "type": type_value,
            "search_context": {
                "has_client": bool(c_name),
                "client_name": c_name,
                "has_temporal": False,
                "temporal_info": {
                    "start_timestamp": None,
                    "end_timestamp": None,
                    "period_type": "none",
                    "raw_dates": {"start": None, "end": None}
                }
            },
            "search_strategy": {
                "precision_required": "medium",
                "priority_sources": priority_sources,
                "min_score_threshold": 0.45
            },
            "query": {
                "original": text,
                "reformulated": text,
                "semantic_search": True
            },
            "mode": "guide" if any(k in text.lower() for k in ['guide', 'étape', 'comment', 'explique']) else "detail"
        }
    
    def _validate_gpt_response(self, content: str) -> Optional[dict]:
        """Valide et parse la réponse JSON de GPT."""
        try:
            # Nettoyage pour extraire uniquement le JSON
            content = re.sub(r'^[^{]*({.*})[^}]*$', r'\1', content.strip(), flags=re.DOTALL)
            return json.loads(content)
        except:
            return None
    
    def determine_collections(self, analysis: Dict) -> List[str]:
        """Détermine les collections à interroger selon l'analyse."""
        # Utilisation directe des sources prioritaires si définies
        if "search_strategy" in analysis and "priority_sources" in analysis["search_strategy"]:
            return analysis["search_strategy"]["priority_sources"]
            
        # Sinon, détermination selon le type de requête
        if "tickets" in analysis.get('query', {}).get('original','').lower():
            return ['jira','zendesk','confluence']
            
        t = (analysis.get('type','') or '').lower()
        if t == 'configuration':
            return ['netsuite','netsuite_dummies','sap']
        elif t == 'support':
            return ['jira','zendesk','confluence']
        elif t == 'documentation':
            return ['confluence','netsuite','netsuite_dummies']
            
        # Par défaut, retourner toutes les collections
        return list(self.collections.keys())
    
    async def recherche_coordonnee(self, collections: List[str], question: str, client_info: Optional[Dict] = None,
                           date_debut: Optional[Any] = None, date_fin: Optional[Any] = None) -> List[Any]:
        """
        Coordonne la recherche parallèle sur plusieurs collections.

        Args:
            collections: Liste des collections à interroger.
            question: Question ou texte à rechercher.
            client_info: Informations sur le client (optionnel).
            date_debut: Date de début pour filtrage (optionnel).
            date_fin: Date de fin pour filtrage (optionnel).

        Returns:
            Liste combinée des résultats pertinents.
        """
        self.logger.info(f"Début recherche coordonnée sur {len(collections)} collections")
        start_time = time.monotonic()

        collections_str = ", ".join(collections)
        self.logger.info(f"Collections ciblées: {collections_str}")
        self.logger.info(f"Question: {question[:100]}{'...' if len(question) > 100 else ''}")
        self.logger.info(f"Client info: {client_info}")
        if date_debut or date_fin:
            self.logger.info(f"Période: {date_debut} → {date_fin}")

        # Récupération des clients de recherche
        clients = {}
        for collection in collections:
            client = await search_factory.get_client(collection)
            if client:
                clients[collection] = client

        if not clients:
            self.logger.error("Aucun client de recherche disponible")
            return []

        results = []

        # Détection de la stratégie de recherche et priorisation des sources
        analysis = {}  # Analyse contextuelle (peut être alimentée dynamiquement)
        priority_sources = analysis.get('search_strategy', {}).get('priority_sources', [])

        async def execute_search_for_collection(source_type, client):
            """Exécute la recherche pour une collection spécifique."""
            task_start_time = time.monotonic()
            try:
                self.logger.info(f"Démarrage recherche {source_type}")
                results = await client.recherche_intelligente(
                    question=question,
                    client_name=client_info,
                    date_debut=date_debut,
                    date_fin=date_fin
                )

                duration = time.monotonic() - task_start_time
                scores = [f'{r.score:.2f}' for r in results[:3]] if results else []
                self.logger.info(f"{source_type}: {len(results)} résultats en {duration:.2f}s (scores: {scores})")

                return source_type, results
            except Exception as e:
                self.logger.error(f"Erreur recherche {source_type}: {str(e)}")
                return source_type, []

        # Exécution en fonction de la priorisation
        executed_sources = set()

        # Exécuter les sources prioritaires en premier
        for source_type in priority_sources:
            if source_type in clients:
                result = await execute_search_for_collection(source_type, clients[source_type])
                results.append(result)
                executed_sources.add(source_type)

        # Exécuter ensuite les autres sources non prioritaires
        for source_type, client in clients.items():
            if source_type not in executed_sources:
                result = await execute_search_for_collection(source_type, client)
                results.append(result)

        # Traitement et fusion des résultats
        combined_results = []
        results_by_source = {}

        for item in results:
            if isinstance(item, Exception):
                self.logger.error(f"Exception non gérée dans une recherche: {str(item)}")
                continue

            if isinstance(item, tuple) and len(item) == 2:
                source_type, res = item
                results_by_source[source_type] = len(res)

                # Marquage de la source dans les résultats
                for r in res:
                    if hasattr(r, 'payload'):
                        if isinstance(r.payload, dict):
                            r.payload['source_type'] = source_type
                        else:
                            # Cas où payload est un objet Python
                            try:
                                r.payload.__dict__['source_type'] = source_type
                            except (AttributeError, TypeError):
                                # Si payload n'est pas un objet avec __dict__, créer un nouveau payload
                                old_payload = r.payload
                                r.payload = {'source_type': source_type, 'original_payload': old_payload}

                    combined_results.extend(res)

        # Tri des résultats par score et déduplication
        combined_results.sort(key=lambda x: getattr(x, 'score', 0), reverse=True)

        # Déduplication basée sur le contenu
        seen = {}
        for res in combined_results:
            if not hasattr(res, 'payload'):
                continue

            # Extraction sécurisée du contenu
            try:
                if isinstance(res.payload, dict):
                    payload = res.payload
                else:
                    payload = res.payload.__dict__ if hasattr(res.payload, '__dict__') else {}

                content = str(payload.get('content', '') or payload.get('text', ''))
            except Exception:
                content = "content_extraction_failed"

            # Utilisation d'un hash du contenu pour la déduplication
            content_hash = hashlib.md5(content[:500].encode('utf-8', errors='ignore')).hexdigest()

            if content_hash not in seen or res.score > seen[content_hash].score:
                seen[content_hash] = res

        # Conversion en liste et limitation
        final_results = list(seen.values())
        final_results.sort(key=lambda x: getattr(x, 'score', 0), reverse=True)

        total_time = time.monotonic() - start_time
        self.logger.info(f"Recherche terminée en {total_time:.2f}s - Résultats par source: {results_by_source}")
        self.logger.info(f"Total dédupliqué: {len(final_results)} résultats")

        # Sauvegarde des résultats pour les actions ultérieures
        self._last_search_results = final_results[:5]

        # Limitation à un nombre raisonnable de résultats
        return final_results[:5]

    
    async def format_response(self, results: List[Any], question: str = None, 
                       include_actions: bool = True) -> Dict:
        """
        Formate la réponse pour l'interface web avec blocs et actions.
        
        Args:
            results: Liste des résultats de recherche
            question: Question originale (optionnelle)
            include_actions: Inclure les boutons d'action (optionnel)
            
        Returns:
            Dictionnaire formaté pour l'interface web
        """
        # En cas d'absence de résultats
        if not results:
            no_results_blocks = [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔍 *Aucun résultat pertinent trouvé*"
                }
            }]
            
            # Ajout de suggestions si question fournie
            if question:
                no_results_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Essayez de reformuler votre question ou d'ajouter plus de détails."
                    }
                })
                
                # Suggestions de recherches alternatives
                no_results_blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Recherche générale"
                            },
                            "value": f"search_general:{question}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Documentation"
                            },
                            "value": f"search_docs:{question}"
                        }
                    ]
                })
                    
            return {
                "text": "Aucun résultat pertinent trouvé.",
                "blocks": no_results_blocks
            }
        
        # Construction de l'en-tête des résultats
        header_blocks = [{
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Résultats de recherche ({len(results)})",
                "emoji": True
            }
        }]
        
        # Ajout d'un contexte si question fournie
        if question:
            header_blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Question:* {question}"
                    }
                ]
            })
        
        # Récupération des types de sources pour le résumé
        source_types = {}
        for r in results:
            source_type = self._detect_source_type(r)
            source_types[source_type] = source_types.get(source_type, 0) + 1
        
        # Ajout du résumé des sources
        source_summary = " | ".join([f"{count} {src.upper()}" for src, count in source_types.items()])
        header_blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Sources:* {source_summary}"
                }
            ]
        })
        
        # Séparateur avant les résultats
        header_blocks.append({"type": "divider"})
        
        # Formatage des résultats individuels
        formatted_blocks = []
        
        # Récupération des clients de recherche appropriés
        source_clients = {}
        for r in results:
            source_type = self._detect_source_type(r)
            if source_type not in source_clients:
                source_client = await search_factory.get_client(source_type)
                if source_client:
                    source_clients[source_type] = source_client
        
        # Formatage de chaque résultat avec le client approprié
        for r in results:
            try:
                source_type = self._detect_source_type(r)
                if source_type in source_clients:
                    client = source_clients[source_type]
                    block = await client.format_for_slack(r)
                    
                    if block:
                        formatted_blocks.append(block)
                        
                        # Ajout des boutons d'action si demandé
                        if include_actions:
                            # Récupération des informations du résultat
                            payload = r.payload if isinstance(r.payload, dict) else r.payload.__dict__
                            result_id = f"{source_type}-{payload.get('id') or payload.get('key') or payload.get('ticket_id')}"
                            
                            action_elements = []
                            
                            # Bouton de détails pour les URLs
                            url = payload.get('url') or payload.get('page_url')
                            if url:
                                action_elements.append({
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🔍 Voir détails",
                                        "emoji": True
                                    },
                                    "url": url,
                                    "value": f"view:{result_id}"
                                })
                            
                            # Autres boutons communs
                            action_elements.extend([
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "📋 Copier",
                                        "emoji": True
                                    },
                                    "value": f"copy:{result_id}"
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "👍 Pertinent",
                                        "emoji": True
                                    },
                                    "value": f"relevant:{result_id}"
                                }
                            ])
                            
                            # Ajout du bloc d'actions
                            if action_elements:
                                formatted_blocks.append({
                                    "type": "actions",
                                    "elements": action_elements
                                })
                        
                        # Ajout d'un séparateur
                        formatted_blocks.append({"type": "divider"})
                        
            except Exception as e:
                self.logger.error(f"Erreur formatage résultat: {str(e)}")
        
        # Si aucun résultat formaté
        if not formatted_blocks:
            return {
                "text": "Impossible de formater les résultats.",
                "blocks": [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "Impossible d'afficher les résultats. Veuillez réessayer."}
                }]
            }
        
        # Actions complémentaires globales
        footer_blocks = []
        if include_actions and question:
            footer_blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Générer un guide",
                            "emoji": True
                        },
                        "value": f"guide:{question}"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Afficher plus",
                            "emoji": True
                        },
                        "value": f"more:{question}"
                    }
                ]
            })
        
        # Assemblage final
        all_blocks = header_blocks + formatted_blocks + footer_blocks
        
        return {
            "text": f"Résultats pour: {question}" if question else "Résultats de recherche",
            "blocks": all_blocks
        }
    
    def _detect_source_type(self, result) -> str:
        """Détecte le type de source d'un résultat."""
        try:
            if isinstance(result, dict):
                p = result
            else:
                p = result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})
                
            if 'source_type' in p:
                return p['source_type']
                
            # Détection basée sur les champs présents
            if 'key' in p: return 'jira'
            if 'ticket_id' in p: return 'zendesk'
            if 'space_id' in p: return 'confluence'
            if 'pdf_path' in p:
                return 'netsuite_dummies' if 'dummy' in str(p.get('title','')).lower() else 'sap'
            if 'url' in p and 'content' in p:
                return 'netsuite'
            if 'title' in p and 'text' in p:
                return 'sap'
                
            return 'unknown'
            
        except:
            return 'unknown'
    
    async def generate_guide(self, results: List[Any], question: str) -> str:
        """
        Génère un guide étape par étape à partir des résultats.
        
        Args:
            results: Liste des résultats pertinents
            question: Question originale
            
        Returns:
            Guide étape par étape formaté
        """
        if not results:
            return "Impossible de générer un guide, aucun résultat trouvé."
            
        # Extraction des contenus pertinents
        formatted = []
        for r in results[:3]:  # Limite à 3 résultats pour le guide
            try:
                # Extraction du payload
                p = getattr(r, 'payload', {}) or {}
                if not isinstance(p, dict):
                    p = getattr(p, '__dict__', {})
                
                # Récupération des contenus
                content = p.get('content', '') or p.get('text', '')
                title = p.get('title', '') or p.get('summary', '')
                source_type = p.get('source_type', self._detect_source_type(r))
                
                if content or title:
                    formatted.append({
                        'content': content[:1000] if content else title[:1000],
                        'title': title[:200],
                        'source_type': source_type
                    })
                    
            except Exception as e:
                self.logger.warning(f"Erreur formatage pour guide: {str(e)}")
        
        if not formatted:
            return "Impossible de générer un guide à partir des résultats."
        
        # Prompt optimisé pour le guide
        prompt = (
            f"Génère un guide détaillé pour : '{question}'\n"
            "Format : introduction, prérequis, étapes numérotées (max 10), conclusion.\n"
            "Étapes courtes et explicites. Respecte la structure."
        )
        
        try:
            resp = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(formatted)}
                ],
                temperature=0.1
            )
            guide = resp.choices[0].message.content.strip()
            return guide
            
        except Exception as e:
            self.logger.error(f"Erreur génération guide: {str(e)}")
            return "Erreur lors de la génération du guide."
    
    async def generate_summary(self, results: List[Any], question: str) -> str:
        """
        Génère un résumé concis des résultats.
        
        Args:
            results: Liste des résultats pertinents
            question: Question originale
            
        Returns:
            Résumé formaté
        """
        if not results:
            return "Aucun résultat à résumer."
            
        # Extraction des contenus pertinents
        contents = []
        for r in results[:3]:
            try:
                p = getattr(r, 'payload', {}) or {}
                if not isinstance(p, dict):
                    p = getattr(p, '__dict__', {})
                    
                content = p.get('content') or p.get('text') or p.get('title', '')
                if content:
                    contents.append(content[:1000])
                    
            except Exception as e:
                self.logger.warning(f"Erreur extraction contenu pour résumé: {str(e)}")
        
        if not contents:
            return "Impossible d'extraire du contenu à résumer."
            
        # Prompt optimisé pour le résumé
        prompt = (
            f"Voici des extraits de résultats liés à la question : '{question}'.\n"
            "Réalise un résumé des points essentiels en quelques phrases claires et concises."
        )
        
        try:
            resp = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "\n---\n".join(contents)}
                ],
                temperature=0.1,
                max_tokens=300
            )
            return resp.choices[0].message.content.strip()
            
        except Exception as e:
            self.logger.error(f"Erreur génération résumé: {str(e)}")
            return "Erreur lors de la génération du résumé."
    
    async def process_web_message(self, text: str, conversation: Any, user_id: str) -> Dict:
        start_time = time.monotonic()
        try:
            # Si c'est une commande spéciale, traitement approprié
            if text.startswith('/'):
                return await self._process_command(text[1:], conversation, user_id)

            # Vérification si salutation
            if await self.is_greeting(text):
                return {
                    "text": f"Bonjour, comment puis-je vous aider ?",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "Bonjour, comment puis-je vous aider ?"}
                    }]
                }

            # Timeout global pour limiter le temps de traitement
            async with asyncio.timeout(45):  # 45 secondes max pour le traitement complet
                # Analyse de la question pour déterminer le contexte et la stratégie
                analysis = await asyncio.wait_for(self.analyze_question(text), timeout=45)

                if not analysis or not isinstance(analysis, dict):
                    return {
                        "text": "Je n'ai pas pu analyser votre question. Pourriez-vous la reformuler ?",
                        "blocks": [{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "Je n'ai pas pu analyser votre question. Pourriez-vous la reformuler ?"}
                        }]
                    }

                # Extraction du client
                client_info = None
                search_context = analysis.get("search_context", {})
                if search_context.get("has_client"):
                    client_name, score, client_details = await extract_client_name(text)
                    if client_details and client_details.get("ambiguous"):
                        possibilities = client_details.get("possibilities", [])
                        return {
                            "text": f"Plusieurs clients possibles : {', '.join(possibilities)}. Pouvez-vous préciser ?",
                            "blocks": [{
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": f"Plusieurs clients possibles : {', '.join(possibilities)}. Pouvez-vous préciser ?"}
                            }]
                        }
                    if client_name:
                        client_info = {"source": client_name, "jira": client_name, "zendesk": client_name}
                        self.logger.info(f"Client trouvé: {client_name}")

                # Tentative d'extraction directe du client si non trouvé par l'analyse
                if not client_info:
                    client_name, score, client_details = await extract_client_name(text)
                    if client_name:
                        client_info = {"source": client_name, "jira": client_name, "zendesk": client_name}
                        self.logger.info(f"Client trouvé (méthode directe): {client_name}")
                    else:
                        self.logger.info("Aucun client identifié pour cette requête")

                # Gestion des dates
                date_debut, date_fin = None, None
                temporal_info = search_context.get("temporal_info", {})

                if temporal_info.get("start_timestamp"):
                    try:
                        date_debut = datetime.fromtimestamp(temporal_info["start_timestamp"], tz=timezone.utc)
                    except:
                        pass

                if temporal_info.get("end_timestamp"):
                    try:
                        date_fin = datetime.fromtimestamp(temporal_info["end_timestamp"], tz=timezone.utc)
                        date_fin = date_fin.replace(hour=23, minute=59, second=59, microsecond=999999)
                    except:
                        pass

                # Détermination des collections à utiliser
                collections = self.determine_collections(analysis)
                self.logger.info(f"Collections sélectionnées: {collections}")

                # Exécution des recherches coordonnées
                resultats = await self.recherche_coordonnee(
                    collections=collections,
                    question=text,
                    client_info=client_info,
                    date_debut=date_debut,
                    date_fin=date_fin
                )

                if not resultats:
                    return {
                        "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question.",
                        "blocks": [{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question."}
                        }]
                    }

                # Génération d'un résumé concis
                summary = await self.generate_summary(resultats, text)

                # Préparation des boutons pour changer de mode
                action_buttons = {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🔍 Détails",
                                "emoji": True
                            },
                            "value": f"details:{text}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📋 Guide",
                                "emoji": True
                            },
                            "value": f"guide:{text}"
                        }
                    ]
                }

                # Création de la réponse formatée avec le résumé et les boutons
                return {
                    "text": summary,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"🔍 *Résumé*\n\n{summary}"}
                        },
                        action_buttons
                    ]
                }

        except Exception as e:
            self.logger.error(f"Erreur process_web_message: {str(e)}")
            elapsed_time = time.monotonic() - start_time
            self.logger.error(f"Échec après {elapsed_time:.2f}s")

            return {
                "text": f"Une erreur est survenue pendant le traitement: {str(e)}",
                "blocks": [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"Une erreur est survenue pendant le traitement: {str(e)}"}
                }]
            }

            
   
    async def handle_action_button(self, action_type: str, action_value: str, conversation: Any, user_id: str) -> Dict:
        """
        Gère les actions des boutons cliqués par l'utilisateur.
        
        Args:
            action_type: Type d'action ('details', 'guide', etc.)
            action_value: Valeur associée (généralement la question originale)
            conversation: Contexte de conversation
            user_id: Identifiant de l'utilisateur
            
        Returns:
            Réponse formatée selon l'action demandée
        """
        try:
            # Récupération de la question originale
            if not action_value:
                return {
                    "text": "Action non valide: paramètres manquants",
                    "blocks": [{
                        "type": "section", 
                        "text": {"type": "mrkdwn", "text": "❌ Action non valide: paramètres manquants"}
                    }]
                }
                
            # Récupération du contexte des résultats précédents
            context = json.loads(conversation.context) if conversation.context else {}
            last_results = context.get('last_results', [])
            
            if action_type == "details":
                # Afficher les détails des résultats
                detailed_response = await self.format_response(last_results, action_value)
                return detailed_response
                
            elif action_type == "guide":
                # Générer un guide étape par étape
                guide = await self.generate_guide(last_results, action_value)
                return {
                    "text": guide,
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"🔍 *Guide étape par étape*\n\n{guide}"}
                    }]
                }
                
            elif action_type == "summary":
                # Regenerer un résumé
                summary = await self.generate_summary(last_results, action_value)
                
                # Préparation des boutons pour changer de mode
                action_buttons = {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🔍 Détails",
                                "emoji": True
                            },
                            "value": f"details:{action_value}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📋 Guide",
                                "emoji": True
                            },
                            "value": f"guide:{action_value}"
                        }
                    ]
                }
                
                return {
                    "text": summary,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"🔍 *Résumé*\n\n{summary}"}
                        },
                        action_buttons
                    ]
                }
                
            else:
                return {
                    "text": f"Action non reconnue: {action_type}",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"❓ Action non reconnue: {action_type}"}
                    }]
                }
                
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'action {action_type}: {str(e)}")
            return {
                "text": f"Erreur lors du traitement de l'action: {str(e)}",
                "blocks": [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"❌ Erreur lors du traitement de l'action: {str(e)}"}
                }]
            }
    async def _process_command(self, command: str, conversation: Any, user_id: str) -> Dict:    
        """
        Traite une commande spéciale commençant par '/'.
        
        Args:
            command: Commande sans le slash initial
            conversation: Contexte de conversation
            user_id: Identifiant de l'utilisateur
            
        Returns:
            Réponse formatée pour l'interface web
        """
        command = command.strip().lower()
        
        if command == 'help':
            # Commande d'aide
            help_text = """
                *Commandes disponibles:*
                • `/help` - Affiche cette aide
                • `/clear` - Efface le contexte de conversation
                • `/status` - Affiche l'état de la connectivité des sources
                • `/guide <sujet>` - Génère un guide sur le sujet spécifié
                • `/client <nom>` - Définit le client par défaut pour les prochaines requêtes
                            """
            return {
                "text": "Aide ITS Help",
                "blocks": [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": help_text}
                }]
            }
            
        elif command == 'clear':
            # Commande pour effacer le contexte
            try:
                if hasattr(conversation, 'context'):
                    conversation.context = '{}'
                return {
                    "text": "Contexte de conversation effacé.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "✅ Contexte de conversation effacé."}
                    }]
                }
            except:
                return {
                    "text": "Erreur lors de l'effacement du contexte.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "❌ Erreur lors de l'effacement du contexte."}
                    }]
                }
                
        elif command == 'status':
            # Commande pour vérifier l'état des services
            try:
                # Initialiser le factory si nécessaire
                if not search_factory.initialized:
                    await search_factory.initialize()
                    
                # Vérifier les collections disponibles
                collections = search_factory.qdrant_client.get_collections()
                collection_info = {c.name: c.points_count for c in collections.collections}
                
                # Vérifier la connectivité OpenAI
                openai_status = "✅ Connecté"
                try:
                    await self.openai_client.models.list()
                except:
                    openai_status = "❌ Erreur de connexion"
                
                # Stats du cache
                cache_stats = await global_cache.get_stats() if hasattr(global_cache, 'get_stats') else {"items": "N/A"}
                
                # Formatage du message
                status_message = f"""
                    *État des services ITS Help*

                    *OpenAI:* {openai_status}
                    *Cache:* {cache_stats.get('items', 'N/A')} éléments

                    *Collections Qdrant:*
                    """
                for name, count in collection_info.items():
                    status_message += f"• {name}: {count} documents\n"
                
                return {
                    "text": "État des services ITS Help",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": status_message}
                    }]
                }
                
            except Exception as e:
                return {
                    "text": f"Erreur lors de la vérification du statut: {str(e)}",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"❌ Erreur lors de la vérification du statut: {str(e)}"}
                    }]
                }
                
        elif command.startswith('guide '):
            # Commande pour générer directement un guide
            topic = command[6:].strip()
            if not topic:
                return {
                    "text": "Veuillez spécifier un sujet pour le guide.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "⚠️ Veuillez spécifier un sujet pour le guide."}
                    }]
                }
                
            # Exécution comme une requête normale avec mode guide forcé
            return await self.process_web_message(
                f"guide étape par étape pour {topic}",
                conversation,
                user_id
            )
            
        elif command.startswith('client '):
            # Commande pour définir le client par défaut
            client_name = command[7:].strip()
            if not client_name:
                return {
                    "text": "Veuillez spécifier un nom de client.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "⚠️ Veuillez spécifier un nom de client."}
                    }]
                }
                
            # Vérification de l'existence du client
            client_name, score, client_details = await extract_client_name(client_name)
            if not client_name:
                return {
                    "text": "Client non trouvé.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "❌ Client non trouvé dans la base de données."}
                    }]
                }
                
            # Stockage dans le contexte de conversation
            try:
                context = json.loads(conversation.context) if conversation.context else {}
                context['default_client'] = client_name
                conversation.context = json.dumps(context)
                return {
                    "text": f"Client par défaut défini: {client_name}",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"✅ Client par défaut défini: *{client_name}*"}
                    }]
                }
            except Exception as e:
                return {
                    "text": f"Erreur lors du stockage du client: {str(e)}",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"❌ Erreur lors du stockage du client: {str(e)}"}
                    }]
                }
                
        else:
            # Commande inconnue
            return {
                "text": "Commande non reconnue.",
                "blocks": [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "⚠️ Commande non reconnue. Tapez `/help` pour voir les commandes disponibles."}
                }]
            }