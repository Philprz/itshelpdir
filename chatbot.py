# chatbot.py 

import os
import re
import json
import asyncio
import logging
import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Importations qui seront utilisées à l'initialisation seulement
from openai import AsyncOpenAI, OpenAIError
from gestion_clients import extract_client_name

# Importation de la factory (pas de dépendance circulaire ici)
from search_factory_compat import search_factory
from configuration import global_cache
# Déplacement à l'intérieur des méthodes pour éviter les cycles
# from embedding_service import EmbeddingService
# from translation_service import TranslationService

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
        # Vérifier si c'est une clé de projet (commence par sk-proj-)
        if openai_key.startswith("sk-proj-"):
            # Initialisation pour clé de projet
            self.openai_client = AsyncOpenAI(
                api_key=openai_key,
                organization=os.getenv("OPENAI_ORG_ID", None),  # Utiliser l'ID d'organisation si disponible
                project=openai_key.split("-")[2] if len(openai_key.split("-")) > 2 else None
            )
        else:
            # Initialisation standard
            self.openai_client = AsyncOpenAI(api_key=openai_key)
            
        self.openai_key = openai_key
        self.qdrant_url = qdrant_url
        self.qdrant_api_key = qdrant_api_key
        
        # Initialisation des services avec imports locaux pour éviter les cycles
        from embedding_service_compat import EmbeddingService
        from translation_service_compat import TranslationService
        
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
        
    async def verify_openai_connection(self) -> Dict[str, Any]:
        """
        Vérifie la connexion à l'API OpenAI et retourne le statut.
        
        Returns:
            Dictionnaire contenant le statut de la connexion (success, message, etc.)
        """
        try:
            # Tester avec un appel simple à l'API
            start_time = time.monotonic()
            self.logger.info("🔍 TEST DE CONNEXION OPENAI: Vérification de la connexion à l'API OpenAI...")
            
            # Utiliser un modèle rapide et économique pour le test
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hello, this is a connection test."}],
                max_tokens=5,
                temperature=0
            )
            
            latency = time.monotonic() - start_time
            
            # Vérifier si la réponse contient du contenu valide
            if response and response.choices and len(response.choices) > 0:
                self.logger.info(f"✅ TEST DE CONNEXION OPENAI: Succès - API clé valide et opérationnelle (latence: {latency:.2f}s)")
                return {
                    "success": True,
                    "latency": latency,
                    "model": "gpt-4o-mini",
                    "message": "Connexion OpenAI établie avec succès"
                }
            else:
                self.logger.error("❌ TEST DE CONNEXION OPENAI: Échec - Réponse OpenAI vide ou invalide")
                return {
                    "success": False,
                    "message": "Réponse OpenAI vide ou invalide"
                }
                
        except OpenAIError as e:
            self.logger.error(f"❌ TEST DE CONNEXION OPENAI: Échec - Erreur API: {str(e)}")
            # Analyse d'erreurs communes
            error_message = str(e)
            if "API key" in error_message and ("invalid" in error_message.lower() or "incorrect" in error_message.lower()):
                return {
                    "success": False,
                    "message": f"Clé API OpenAI invalide ou incorrecte: {error_message}",
                    "error_type": "invalid_api_key",
                    "error": str(e)
                }
            elif "rate limit" in error_message.lower():
                return {
                    "success": False,
                    "message": f"Limite de taux OpenAI atteinte: {error_message}",
                    "error_type": "rate_limit",
                    "error": str(e)
                }
            else:
                return {
                    "success": False,
                    "message": f"Erreur de connexion OpenAI: {error_message}",
                    "error": str(e)
                }
                
        except Exception as e:
            self.logger.error(f"❌ TEST DE CONNEXION OPENAI: Échec - Exception inattendue: {str(e)}")
            return {
                "success": False,
                "message": f"Exception inattendue: {str(e)}",
                "error": str(e)
            }
            
    async def verify_qdrant_connection(self) -> Dict[str, Any]:
        """
        Vérifie la connexion à Qdrant et retourne le statut.
        
        Returns:
            Dictionnaire contenant le statut de la connexion (success, message, etc.)
        """
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.exceptions import UnexpectedResponse
            
            start_time = time.monotonic()
            self.logger.info(f"🔍 TEST DE CONNEXION QDRANT: Vérification de la connexion au serveur ({self.qdrant_url})...")
            
            # Créer un client Qdrant temporaire pour le test
            client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
                timeout=10.0  # Timeout plus long pour être plus tolérant aux latences réseau
            )
            
            # Tenter une opération simple comme lister les collections
            collections = await asyncio.to_thread(client.get_collections)
            
            latency = time.monotonic() - start_time
            
            collection_count = len(collections.collections) if hasattr(collections, 'collections') else 0
            collection_names = [coll.name for coll in collections.collections] if hasattr(collections, 'collections') else []
            
            # Vérifier que nos collections existent
            missing_collections = []
            for coll_name in self.collections.values():
                if coll_name and coll_name not in collection_names:
                    missing_collections.append(coll_name)
            
            # Succès si au moins une collection est trouvée
            if collection_count > 0:
                status_message = f"✅ TEST DE CONNEXION QDRANT: Succès - Serveur accessible avec {collection_count} collections (latence: {latency:.2f}s)"
                if missing_collections:
                    status_message += f" - ATTENTION: {len(missing_collections)} collections manquantes: {', '.join(missing_collections)}"
                    self.logger.warning(status_message)
                else:
                    self.logger.info(status_message)
                
                return {
                    "success": True,
                    "latency": latency,
                    "collection_count": collection_count,
                    "collections": collection_names,
                    "missing_collections": missing_collections,
                    "message": "Connexion Qdrant établie avec succès"
                }
            else:
                self.logger.error("❌ TEST DE CONNEXION QDRANT: Échec - Aucune collection trouvée dans le serveur")
                return {
                    "success": False,
                    "message": "Aucune collection trouvée dans le serveur"
                }
                
        except UnexpectedResponse as e:
            self.logger.error(f"❌ TEST DE CONNEXION QDRANT: Échec - Erreur de réponse: {str(e)}")
            return {
                "success": False,
                "message": f"Erreur de réponse Qdrant: {str(e)}",
                "error": str(e)
            }
            
        except Exception as e:
            self.logger.error(f"❌ TEST DE CONNEXION QDRANT: Échec - Exception inattendue: {str(e)}")
            return {
                "success": False,
                "message": f"Exception inattendue: {str(e)}",
                "error": str(e)
            }
            
    async def verify_connections(self) -> Dict[str, Any]:
        """
        Vérifie toutes les connexions nécessaires au fonctionnement du chatbot.
        
        Returns:
            Dictionnaire contenant le statut des différentes connexions
        """
        self.logger.info("🔍 VÉRIFICATION DES CONNEXIONS: Démarrage des tests de connexion pour tous les services externes...")
        
        results = {
            "all_success": True,
            "timestamp": datetime.now().isoformat(),
            "services": {}
        }
        
        # Vérifier OpenAI
        openai_status = await self.verify_openai_connection()
        results["services"]["openai"] = openai_status
        results["all_success"] = results["all_success"] and openai_status["success"]
        
        # Vérifier Qdrant
        qdrant_status = await self.verify_qdrant_connection()
        results["services"]["qdrant"] = qdrant_status
        results["all_success"] = results["all_success"] and qdrant_status["success"]
        
        # Résumé des résultats
        if results["all_success"]:
            self.logger.info("✅ VÉRIFICATION DES CONNEXIONS TERMINÉE: Tous les services externes ont été testés et sont fonctionnels")
            self.logger.info(f"   - OpenAI: Connecté (latence: {openai_status.get('latency', 0):.2f}s)")
            self.logger.info(f"   - Qdrant: Connecté (latence: {qdrant_status.get('latency', 0):.2f}s)")
        else:
            failed_services = [name for name, status in results["services"].items() if not status["success"]]
            self.logger.error(f"❌ VÉRIFICATION DES CONNEXIONS TERMINÉE: Échec de connexion pour {len(failed_services)} service(s): {', '.join(failed_services)}")
        
        return results
    
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
                    "min_score_threshold": 0.25
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
                client_name, _, _ = await extract_client_name(text)
                # Ajout d'une recherche spécifique pour les mots simples
                if not client_name and re.search(r'\b[A-Za-z]{4,}\b', text):
                    potential_clients = re.findall(r'\b[A-Za-z]{4,}\b', text)
                    for potential in potential_clients:
                        test_name, _, _ = await extract_client_name(potential)
                        if test_name:
                            client_name = test_name
                            break
            # Détection rapide des catégories
            is_config_request = any(k in text.lower() for k in ['configur', 'paramèt', 'paramet', 'workflow', 'personnalis', 'custom', 'compte client', 'compte fournisseur'])
            is_doc_request = any(k in text.lower() for k in ['documentation', 'tutoriel', 'manuel', 'comment faire'])
            is_guide_request = any(k in text.lower() for k in ['guide', 'étape par étape', 'procédure', 'explique'])
            
            # Détection spécifique pour les comptes
            is_account_config = any(k in text.lower() for k in ['compte client', 'compte fournisseur', 'paramétrer le compte', 'paramétrer un compte', 'configurer le compte', 'configurer un compte'])
            
            # Appel à OpenAI pour analyse complète
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": strict_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1
            )
            content = response.choices[0].message.content.strip()
            if not content:
                return self._fallback_analysis(text, is_config_request, is_doc_request)
                
            # Tentative de parsing JSON
            analysis = self._validate_gpt_response(content)
            if not analysis:
                return self._fallback_analysis(text, is_config_request, is_doc_request)
                
            # Ajustement en fonction de la détection rapide
            if (is_config_request or is_account_config) and analysis['type'] != 'configuration':
                analysis['type'] = 'configuration'
                if 'search_strategy' in analysis:
                    analysis['search_strategy']['priority_sources'] = ['netsuite', 'sap', 'netsuite_dummies']
            
            # Force l'utilisation des collections spécifiques pour les comptes clients
            if is_account_config:
                analysis['type'] = 'configuration'  # Force le type à configuration
                if 'search_strategy' in analysis:
                    analysis['search_strategy']['priority_sources'] = ['netsuite', 'netsuite_dummies', 'sap']
                    analysis['search_strategy']['min_score_threshold'] = 0.25  # Abaisse le seuil pour obtenir plus de résultats
            
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
                "min_score_threshold": 0.25
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
        except Exception as e:
            self.logger.warning(f"Erreur lors du parsing JSON de l'analyse: {str(e)}")
            return None
    
    def determine_collections(self, analysis: Dict) -> List[str]:
        """Détermine les collections à interroger selon l'analyse."""
        # Mapping des types de requêtes vers les collections appropriées
        collection_mapping = {
            'configuration': ['netsuite', 'netsuite_dummies', 'sap'],
            'support': ['jira', 'zendesk', 'confluence'],
            'documentation': ['confluence', 'netsuite', 'sap']
        }
        
        # Utilisation directe des sources prioritaires si définies
        if "search_strategy" in analysis and "priority_sources" in analysis["search_strategy"]:
            sources = analysis["search_strategy"]["priority_sources"]
            self.logger.info(f"Collections déterminées par priority_sources: {sources}")
            return sources
            
        # Vérification spécifique pour RONDOT
        query_text = analysis.get('query', {}).get('original','').upper()
        if "RONDOT" in query_text:
            self.logger.info("Collections déterminées par mention de 'RONDOT': ['jira', 'zendesk', 'confluence']")
            return ['jira', 'zendesk', 'confluence']
            
        # Vérification spécifique pour les tickets
        if "tickets" in analysis.get('query', {}).get('original','').lower():
            self.logger.info("Collections déterminées par mention de 'tickets': ['jira', 'zendesk', 'confluence']")
            return ['jira', 'zendesk', 'confluence']
            
        # Détermination selon le type de requête
        query_type = (analysis.get('type','') or '').lower()
        self.logger.info(f"Type de requête détecté: {query_type}")
        if query_type in collection_mapping:
            sources = collection_mapping[query_type]
            self.logger.info(f"Collections déterminées par type de requête '{query_type}': {sources}")
            return sources
            
        # Par défaut, retourner toutes les collections
        all_collections = list(self.collections.keys())
        self.logger.info(f"Collections par défaut (toutes): {all_collections}")
        return all_collections
    
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
            # Convertir le nom de collection en type de source (minuscules)
            source_type = collection.lower()
            self.logger.info(f"Demande du client pour source_type={source_type} (collection={collection})")
            
            try:
                client = await self.search_factory.get_client(source_type)
                if client:
                    # Vérifier que le client est bien un objet valide avec recherche_intelligente
                    if hasattr(client, 'recherche_intelligente'):
                        clients[source_type] = client
                        self.logger.info(f"Client récupéré pour {source_type}: {type(client).__name__}")
                    else:
                        self.logger.warning(f"Client sans méthode recherche_intelligente pour {source_type}: {type(client).__name__}")
            except Exception as e:
                self.logger.error(f"Erreur lors de la récupération du client pour {source_type}: {str(e)}")
            
        if not clients:
            self.logger.error("Aucun client de recherche disponible pour cette requête.")
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
                # Paramètres de recherche standard pour tous les clients
                search_limit = 10  # Nombre maximum de résultats par source
                score_min = 0.5    # Score minimal pour un résultat pertinent
                
                # Extraction de la valeur client appropriée du dictionnaire client_info
                client_value = None
                if client_info:
                    # Utiliser la clé correspondant au type de source si elle existe,
                    # sinon utiliser la clé 'source' ou la première valeur disponible
                    if source_type in client_info:
                        client_value = client_info[source_type]
                    elif 'source' in client_info:
                        client_value = client_info['source']
                    # Fallback: prendre la première valeur non-None
                    else:
                        for key, value in client_info.items():
                            if value is not None:
                                client_value = value
                                break
                
                self.logger.info(f"Valeur client utilisée pour {source_type}: {client_value}")
                
                results = await client.recherche_intelligente(
                    question=question,
                    client_name=client_value,
                    date_debut=date_debut,
                    date_fin=date_fin,
                    limit=search_limit
                )
                
                # Filtrage des résultats selon le score minimal
                filtered_results = []
                for result in results:
                    score = None
                    if hasattr(result, 'score'):
                        score = result.score
                    elif isinstance(result, dict) and 'score' in result:
                        score = result['score']
                    
                    if score is None or score >= score_min:
                        filtered_results.append(result)
                
                results = filtered_results
                
                # Formatage du log avec les scores des 3 premiers résultats pour debug
                scores_str = []
                for i, r in enumerate(results[:3]):
                    if hasattr(r, 'score'):
                        scores_str.append(f"{r.score:.2f}")
                    elif isinstance(r, dict) and 'score' in r:
                        scores_str.append(f"{r['score']:.2f}")
                
                elapsed = time.monotonic() - task_start_time
                self.logger.info(f"{source_type}: {len(results)} résultats en {elapsed:.2f}s (scores: {scores_str})")
                
                return (source_type, results)
            except Exception as e:
                self.logger.error(f"Erreur recherche {source_type}: {str(e)}")
                return (source_type, [])
        
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
                self.logger.info(f"Traitement des résultats de {source_type}: {len(res)} résultats")
                results_by_source[source_type] = len(res)

                # Marquage de la source dans les résultats
                for r in res:
                    # Log détaillé des résultats
                    self.logger.info(f"Résultat de {source_type}: score={getattr(r, 'score', 0)}")
                    
                    # Au lieu d'essayer d'ajouter un attribut directement à l'objet ScoredPoint,
                    # nous allons uniquement le mettre dans le payload, qui est plus flexible
                    if hasattr(r, 'payload'):
                        try:
                            if isinstance(r.payload, dict):
                                r.payload['source_type'] = source_type
                            elif hasattr(r.payload, '__dict__'):
                                r.payload.__dict__['source_type'] = source_type
                            else:
                                # Si payload n'est pas un dictionnaire ou un objet avec __dict__
                                old_payload = r.payload
                                r.payload = {'source_type': source_type, 'original_payload': old_payload}
                        except Exception as e:
                            self.logger.warning(f"Erreur lors de l'ajout du source_type au payload: {str(e)}")
                    else:
                        # Si r n'a pas d'attribut payload, essayons de le traiter comme un dictionnaire
                        try:
                            if isinstance(r, dict):
                                r['source_type'] = source_type
                                if 'payload' in r and isinstance(r['payload'], dict):
                                    r['payload']['source_type'] = source_type
                        except Exception as e:
                            self.logger.warning(f"Impossible d'ajouter source_type au résultat: {str(e)}")
                    
                    # Ajouter le résultat à la liste combinée
                    combined_results.append(r)

        # Tri des résultats par score
        self.logger.info(f"Nombre de résultats combinés avant tri et déduplication: {len(combined_results)}")
        
        if not combined_results:
            self.logger.warning("Aucun résultat trouvé dans les collections")
            return []
            
        # Tri des résultats par score (du plus élevé au plus bas)
        combined_results.sort(key=lambda x: getattr(x, 'score', 0), reverse=True)

        # Déduplication simplifiée pour éviter de perdre des résultats
        # On ne garde que les doublons exacts, basés sur des identifiants
        dedup_results = []
        seen_ids = set()
        
        for res in combined_results:
            # Extraction de l'ID unique pour déduplication
            res_id = None
            try:
                if hasattr(res, 'id'):
                    res_id = str(res.id)
                elif hasattr(res, 'payload') and isinstance(res.payload, dict) and 'id' in res.payload:
                    res_id = str(res.payload['id'])
                elif hasattr(res, 'payload') and hasattr(res.payload, 'id'):
                    res_id = str(res.payload.id)
            except Exception:
                res_id = None
                
            # Si aucun ID n'est trouvé, on utilise l'objet lui-même
            if not res_id:
                res_id = id(res)
                
            # Si cet ID n'a pas été vu, on l'ajoute aux résultats dédupliqués
            if res_id not in seen_ids:
                seen_ids.add(res_id)
                dedup_results.append(res)
                
        self.logger.info(f"Nombre de résultats après déduplication: {len(dedup_results)}")
        
        # Conversion en liste et limitation
        final_results = dedup_results
        final_results.sort(key=lambda x: getattr(x, 'score', 0), reverse=True)
        
        # Calcul du temps total d'exécution
        total_time = time.monotonic() - start_time
        self.logger.info(f"Recherche terminée en {total_time:.2f}s - Résultats par source: {results_by_source}")
        self.logger.info(f"Total dédupliqué: {len(final_results)} résultats")
        
        # Sauvegarde des résultats pour les actions ultérieures
        self._last_search_results = final_results[:5]

        # Limitation à un nombre raisonnable de résultats
        return final_results[:5]

    
    async def format_response(self, results: List[Any], question: str = None,
                       include_actions: bool = True, debug_zendesk: bool = False, progressive: bool = False) -> Dict:
        """
        Formate la réponse pour l'interface web avec blocs et actions.

        Args:
            results: Liste des résultats de recherche
            question: Question originale (optionnelle)
            include_actions: Inclure les boutons d'action (optionnel)
            debug_zendesk: Mode de débogage pour les résultats Zendesk (optionnel)
            progressive: Mode de formatage progressif des résultats (optionnel)

        Returns:
            Dictionnaire formaté pour l'interface web
        """
        # Limitation du nombre de résultats pour éviter des réponses trop longues
        max_results = 5
        if len(results) > max_results:
            self.logger.info(f"Limitation à {max_results} résultats sur {len(results)} disponibles")
            results = results[:max_results]

        # En-tête avec information sur le nombre de résultats
        header_blocks = []
        if question:
            header_text = f"*Résultats pour:* {question}\n\n"
            if len(results) > 0:
                header_text += f"J'ai trouvé {len(results)} résultats pertinents."
            else:
                header_text += "Je n'ai pas trouvé de résultats pertinents."
                
            header_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": header_text
                }
            })
            header_blocks.append({"type": "divider"})

        # Comptage des types de sources
        source_types = {}
        for r in results:
            try:
                source_type = self._detect_source_type(r)
                source_types[source_type] = source_types.get(source_type, 0) + 1
            except Exception as e:
                self.logger.error(f"Erreur comptage type source: {str(e)}")

        # Formatage des résultats individuels
        formatted_blocks = []

        # Récupération des clients de recherche appropriés
        source_clients = {}
        for source_type in source_types.keys():
            source_client = await search_factory.get_client(source_type)
            if source_client:
                source_clients[source_type] = source_client

        if not source_clients:
            self.logger.error("Aucun client de recherche disponible")
            return []

        # Fonction commune pour extraire le payload et le score d'un résultat
        def extract_result_data(result):
            """Extrait le payload et le score d'un résultat de manière standardisée."""
            try:
                payload = {}
                score = 0.0
                
                if isinstance(result, dict):
                    payload = result.get('payload', {}) if isinstance(result.get('payload'), dict) else result
                    score = float(result.get('score', 0.0))
                else:
                    if hasattr(result, 'payload'):
                        payload = result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})
                    else:
                        payload = getattr(result, '__dict__', {})
                    score = float(getattr(result, 'score', 0.0))
                
                return payload, score
            except Exception as e:
                self.logger.error(f"Erreur extraction données résultat: {str(e)}")
                return {}, 0.0

        # Mode de formatage progressif si activé
        if progressive:
            self.logger.info("Utilisation du mode de formatage progressif")
            
            # Formatage individuel pour chaque résultat avec gestion des erreurs individuelles
            for i, r in enumerate(results):
                try:
                    # Extraction standardisée du payload et du score
                    payload, score = extract_result_data(r)

                    # Détection de la source
                    source_type = self._detect_source_type(r)
                    
                    # Essayer d'utiliser le client spécialisé pour la source
                    formatted_block = None
                    try:
                        if source_type in source_clients:
                            source_client = source_clients[source_type]
                            formatted_block = await source_client.format_for_slack(r)
                            if formatted_block and isinstance(formatted_block, dict) and formatted_block.get("type"):
                                formatted_blocks.append(formatted_block)
                                formatted_blocks.append({"type": "divider"})
                                continue
                            else:
                                self.logger.warning(f"Bloc formaté invalide pour {source_type} (résultat #{i+1}), utilisation du formatage par défaut")
                    except Exception as format_error:
                        self.logger.error(f"Erreur lors du formatage spécifique pour {source_type} (résultat #{i+1}): {str(format_error)}")
                    
                    # Formatage par défaut si le client spécialisé a échoué
                    score_percent = round(score * 100)
                    fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

                    # Extraction des champs communs avec fallbacks
                    title = payload.get('summary', '') or payload.get('title', '') or "Sans titre"
                    content = str(payload.get('content', '') or payload.get('text', '') or "Pas de contenu")
                    if len(content) > 500:
                        content = content[:497] + "..."

                    # Construction d'un bloc de texte basique qui fonctionne pour tout type de source
                    basic_text = f"*{source_type.upper()}* - {fiabilite} {score_percent}%\n"

                    if source_type in ['jira', 'zendesk']:
                        id_field = payload.get('key', '') or payload.get('ticket_id', '') or payload.get('id', '')
                        client = payload.get('client', 'N/A')
                        status = payload.get('resolution', '') or payload.get('status', 'En cours')
                        assignee = payload.get('assignee', 'Non assigné')
                        created = self._format_date(payload.get('created', ''))
                        updated = self._format_date(payload.get('updated', ''))

                        basic_text += (
                            f"*ID:* {id_field} - *Client:* {client}\n"
                            f"*Titre:* {title}\n"
                            f"*Status:* {status} - *Assigné à:* {assignee}\n"
                            f"*Créé le:* {created} - *Maj:* {updated}\n"
                            f"*Description:* {content}\n"
                            f"*URL:* {payload.get('url', 'N/A')}"
                        )
                    elif source_type in ['confluence']:
                        space_id = payload.get('space_id', 'N/A')
                        client = payload.get('client', 'N/A')

                        basic_text += (
                            f"*Espace:* {space_id} - *Client:* {client}\n"
                            f"*Titre:* {title}\n"
                            f"*Contenu:* {content}\n"
                            f"*URL:* {payload.get('page_url', 'N/A')}"
                        )
                    elif source_type in ['netsuite', 'netsuite_dummies', 'sap']:
                        # Format pour les sources ERP
                        basic_text += (
                            f"*Titre:* {title}\n"
                            f"*Contenu:* {content}\n"
                        )

                        # Ajout de l'URL ou du chemin de fichier selon disponibilité
                        if payload.get('url'):
                            basic_text += f"\n*URL:* {payload.get('url')}"
                        elif payload.get('pdf_path'):
                            basic_text += f"\n*Document:* {payload.get('pdf_path')}"
                    else:
                        # Format générique pour tout autre type de source
                        basic_text += (
                            f"*Titre:* {title}\n"
                            f"*Contenu:* {content}"
                        )

                    # Création du bloc Slack
                    basic_block = {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": basic_text
                        }
                    }

                    formatted_blocks.append(basic_block)

                    # Ajout des boutons d'action si demandé
                    if include_actions:
                        # Récupération des informations du résultat
                        result_id = f"{source_type}-{payload.get('id') or payload.get('key') or payload.get('ticket_id', '')}"

                        action_elements = []

                        # Bouton de détails pour les URLs
                        url = payload.get('url') or payload.get('page_url')
                        if url:
                            action_elements.append({
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Voir détails",
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
                                    "text": "Copier",
                                    "emoji": True
                                },
                                "value": f"copy:{result_id}"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Pertinent",
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
                    self.logger.error(f"Erreur formatage résultat #{i+1}: {str(e)}")
                    # En cas d'erreur, on ajoute un bloc d'erreur
                    formatted_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Erreur de formatage pour le résultat #{i+1}"
                        }
                    })
                    formatted_blocks.append({"type": "divider"})
        else:
            # Formatage de chaque résultat en utilisant les clients de recherche
            for i, r in enumerate(results):
                try:
                    # Extraction standardisée du payload et du score
                    payload, score = extract_result_data(r)

                    # Détection de la source
                    source_type = self._detect_source_type(r)
                    
                    # Formatage via client spécialisé si disponible
                    formatted_block = None
                    try:
                        if source_type in source_clients:
                            source_client = source_clients[source_type]
                            formatted_block = await source_client.format_for_slack(r)
                            if formatted_block and isinstance(formatted_block, dict) and formatted_block.get("type"):
                                formatted_blocks.append(formatted_block)
                                formatted_blocks.append({"type": "divider"})
                                continue
                            else:
                                self.logger.warning(f"Bloc formaté invalide pour {source_type} (résultat #{i+1}), utilisation du formatage par défaut")
                    except Exception as format_error:
                        self.logger.error(f"Erreur lors du formatage spécifique pour {source_type} (résultat #{i+1}): {str(format_error)}")
                    
                    # Formatage par défaut si le client spécialisé a échoué
                    score_percent = round(score * 100)
                    fiabilite = "🟢" if score_percent > 80 else "🟡" if score_percent > 60 else "🔴"

                    # Extraction des champs communs avec fallbacks
                    title = payload.get('summary', '') or payload.get('title', '') or "Sans titre"
                    content = str(payload.get('content', '') or payload.get('text', '') or "Pas de contenu")
                    if len(content) > 500:
                        content = content[:497] + "..."

                    # Construction d'un bloc de texte basique qui fonctionne pour tout type de source
                    basic_text = f"*{source_type.upper()}* - {fiabilite} {score_percent}%\n"

                    if source_type in ['jira', 'zendesk']:
                        id_field = payload.get('key', '') or payload.get('ticket_id', '') or payload.get('id', '')
                        client = payload.get('client', 'N/A')
                        status = payload.get('resolution', '') or payload.get('status', 'En cours')
                        assignee = payload.get('assignee', 'Non assigné')
                        created = self._format_date(payload.get('created', ''))
                        updated = self._format_date(payload.get('updated', ''))

                        basic_text += (
                            f"*ID:* {id_field} - *Client:* {client}\n"
                            f"*Titre:* {title}\n"
                            f"*Status:* {status} - *Assigné à:* {assignee}\n"
                            f"*Créé le:* {created} - *Maj:* {updated}\n"
                            f"*Description:* {content}\n"
                            f"*URL:* {payload.get('url', 'N/A')}"
                        )
                    elif source_type in ['confluence']:
                        space_id = payload.get('space_id', 'N/A')
                        client = payload.get('client', 'N/A')

                        basic_text += (
                            f"*Espace:* {space_id} - *Client:* {client}\n"
                            f"*Titre:* {title}\n"
                            f"*Contenu:* {content}\n"
                            f"*URL:* {payload.get('page_url', 'N/A')}"
                        )
                    elif source_type in ['netsuite', 'netsuite_dummies', 'sap']:
                        # Format pour les sources ERP
                        basic_text += (
                            f"*Titre:* {title}\n"
                            f"*Contenu:* {content}\n"
                        )

                        # Ajout de l'URL ou du chemin de fichier selon disponibilité
                        if payload.get('url'):
                            basic_text += f"\n*URL:* {payload.get('url')}"
                        elif payload.get('pdf_path'):
                            basic_text += f"\n*Document:* {payload.get('pdf_path')}"
                    else:
                        # Format générique pour tout autre type de source
                        basic_text += (
                            f"*Titre:* {title}\n"
                            f"*Contenu:* {content}"
                        )

                    # Création du bloc Slack
                    block = {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": basic_text
                        }
                    }

                    formatted_blocks.append(block)

                    # Ajout des boutons d'action si demandé
                    if include_actions:
                        # Récupération des informations du résultat
                        result_id = f"{source_type}-{payload.get('id') or payload.get('key') or payload.get('ticket_id', '')}"

                        action_elements = []

                        # Bouton de détails pour les URLs
                        url = payload.get('url') or payload.get('page_url')
                        if url:
                            action_elements.append({
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Voir détails",
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
                                    "text": "Copier",
                                    "emoji": True
                                },
                                "value": f"copy:{result_id}"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Pertinent",
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
                    # En cas d'erreur, on ajoute un bloc d'erreur
                    formatted_blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Erreur de formatage pour un résultat"
                        }
                    })

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

        # Log final avant envoi
        self.logger.info(f"Réponse formatée avec {len(all_blocks)} blocs")

        return {
            "text": "Résultats pour: " + question if question else "Résultats de recherche",
            "blocks": all_blocks
        }

    def _format_date(self, date_value):
        """Formate une date pour l'affichage."""
        if not date_value:
            return 'N/A'
        try:
            # Si c'est déjà une chaîne formatée en YYYY-MM-DD, la retourner telle quelle
            if isinstance(date_value, str) and len(date_value) >= 10:
                if date_value[4] == '-' and date_value[7] == '-' and date_value[:10].replace('-', '').isdigit():
                    return date_value[:10]
                    
            # Traitement pour les types numériques
            if isinstance(date_value, (int, float)):
                return datetime.fromtimestamp(date_value, tz=timezone.utc).strftime("%Y-%m-%d")
                
            # Traitement pour les chaînes
            if isinstance(date_value, str):
                # Essai de conversion en timestamp si c'est un nombre
                if date_value.isdigit():
                    try:
                        return datetime.fromtimestamp(float(date_value), tz=timezone.utc).strftime("%Y-%m-%d")
                    except (ValueError, OverflowError):
                        pass
                
                # Essai de conversion depuis le format ISO
                if 'T' in date_value:
                    try:
                        date_obj = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                        return date_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                        
                # Fallback: retourner les 10 premiers caractères s'ils ressemblent à une date
                if len(date_value) >= 10:
                    return date_value[:10]
                    
            # Si c'est un objet datetime, formater directement
            if isinstance(date_value, datetime):
                return date_value.strftime("%Y-%m-%d")
                
            # Fallback final
            return str(date_value) if date_value else 'N/A'
            
        except Exception as e:
            self.logger.error(f"Erreur formatage date: {str(e)}")
            return 'N/A'
    
    def _detect_source_type(self, result) -> str:
        """Détecte le type de source d'un résultat."""
        try:
            # Tentative d'extraction directe depuis un attribut .metadata
            if hasattr(result, 'metadata') and hasattr(result.metadata, 'source'):
                return result.metadata.source.lower()
                
            # Tentative d'extraction depuis un attribut .payload.source
            if hasattr(result, 'payload'):
                if isinstance(result.payload, dict) and 'source' in result.payload:
                    return result.payload['source'].lower()
                elif hasattr(result.payload, 'source'):
                    return result.payload.source.lower()
                    
            # Tentative d'extraction depuis un dictionnaire
            if isinstance(result, dict):
                if 'metadata' in result and 'source' in result['metadata']:
                    return result['metadata']['source'].lower()
                elif 'payload' in result and isinstance(result['payload'], dict) and 'source' in result['payload']:
                    return result['payload']['source'].lower()
                elif 'source' in result:
                    return result['source'].lower()
                    
            # Détection basée sur les champs spécifiques
            payload = {}
            if isinstance(result, dict):
                payload = result.get('payload', {}) if isinstance(result.get('payload'), dict) else result
            else:
                if hasattr(result, 'payload'):
                    payload = result.payload if isinstance(result.payload, dict) else getattr(result.payload, '__dict__', {})
                else:
                    payload = getattr(result, '__dict__', {})
                    
            # Détection par champs caractéristiques
            if any(k in payload for k in ['key', 'issuetype']):
                return 'jira'
            elif any(k in payload for k in ['ticket_id']):
                return 'zendesk'
            elif any(k in payload for k in ['space_id', 'page_id']):
                return 'confluence'
            elif 'pdf_path' in payload and any(k in payload for k in ['title', 'text']):
                return 'netsuite_dummies'
            elif any(k in payload for k in ['erp_type']) and payload.get('erp_type') == 'sap':
                return 'sap'
            elif any(k in payload for k in ['erp_type']) and payload.get('erp_type') == 'netsuite':
                return 'netsuite'
                
            # Fallback: détection par URL si présente
            url = payload.get('url', '')
            if isinstance(url, str):
                if 'atlassian' in url or 'jira' in url:
                    return 'jira'
                elif 'zendesk' in url:
                    return 'zendesk'
                elif 'confluence' in url:
                    return 'confluence'
                elif 'netsuite' in url:
                    return 'netsuite'
                elif 'sap' in url:
                    return 'sap'
                    
            # Fallback par défaut
            return 'generic'
            
        except Exception as e:
            self.logger.error(f"Erreur détection source: {str(e)}")
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
    
    async def process_web_message(self, text: str, conversation: Any, user_id: str, mode: str = "detail", 
                                  debug_zendesk: bool = False, progressive: bool = False, timeout: int = 30):
        """
        Traite un message reçu de l'interface web.
        
        Args:
            text: Message à traiter
            conversation: Objet de conversation pour la persistence
            user_id: Identifiant de l'utilisateur
            mode: Mode de réponse ('detail' ou 'summary')
            debug_zendesk: Activer le mode débogage pour les résultats Zendesk
            progressive: Activer le formatage progressif des résultats
            timeout: Délai maximum d'attente en secondes
            
        Returns:
            Réponse formatée pour l'interface web
        """
        start_time = time.monotonic()
        try:
            # Si c'est une commande spéciale, traitement approprié
            if text.startswith('/'):
                return await self._process_command(text[1:], conversation, user_id)

            # Vérification si salutation
            try:
                is_greeting = await self.is_greeting(text)
                if is_greeting:
                    return {
                        "text": "Bonjour, comment puis-je vous aider ?",
                        "blocks": [{
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": "Bonjour, comment puis-je vous aider ?"}
                        }]
                    }
            except OpenAIError as e:
                self.logger.error(f"Erreur API OpenAI lors de la détection de salutation: {str(e)}")
                return {
                    "text": "Une erreur est survenue avec l'API OpenAI. Veuillez vérifier votre clé API.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "❌ **Erreur API OpenAI**: Veuillez vérifier que votre clé API est correcte et active."}
                    }]
                }
            except Exception as e:
                self.logger.error(f"Erreur détection salutation: {str(e)}")
                # Continuer malgré l'erreur de détection de salutation

            # Timeout global pour limiter le temps de traitement
            try:
                async with asyncio.timeout(timeout):  # Utilisation du timeout spécifié
                    # Analyse de la question pour déterminer le contexte et la stratégie
                    try:
                        analysis = await asyncio.wait_for(self.analyze_question(text), timeout=60)  # Augmenté à 60 secondes
                    except OpenAIError as e:
                        self.logger.error(f"Erreur API OpenAI lors de l'analyse: {str(e)}")
                        return {
                            "text": "Une erreur est survenue avec l'API OpenAI. Veuillez vérifier votre clé API.",
                            "blocks": [{
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": "❌ **Erreur API OpenAI**: Veuillez vérifier que votre clé API est correcte et active."}
                            }]
                        }
                    except Exception as e:
                        self.logger.error(f"Erreur analyse question: {str(e)}")
                        analysis = self._fallback_analysis(text)

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
                        client_name, _, _ = await extract_client_name(text)
                        # Ajout d'une recherche spécifique pour les mots simples
                        if not client_name and re.search(r'\b[A-Za-z]{4,}\b', text):
                            potential_clients = re.findall(r'\b[A-Za-z]{4,}\b', text)
                            for potential in potential_clients:
                                test_name, _, _ = await extract_client_name(potential)
                                if test_name:
                                    client_name = test_name
                                    break
                        if client_name:
                            client_info = {"source": client_name, "jira": client_name, "zendesk": client_name}
                            self.logger.info(f"Client trouvé: {client_name}")

                    # Tentative d'extraction directe du client si non trouvé par l'analyse
                    if not client_info:
                        # Vérification explicite pour RONDOT
                        if "RONDOT" in text.upper():
                            client_info = {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
                            self.logger.info("Client RONDOT détecté explicitement")
                        else:
                            # Extraction standard
                            client_name, _, _ = await extract_client_name(text)
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
                        except ValueError as e:
                            self.logger.debug(f"Erreur lors du traitement de date_debut: {str(e)}")
                            pass

                    if temporal_info.get("end_timestamp"):
                        try:
                            date_fin = datetime.fromtimestamp(temporal_info["end_timestamp"], tz=timezone.utc)
                            date_fin = date_fin.replace(hour=23, minute=59, second=59, microsecond=999999)
                        except ValueError as e:
                            self.logger.debug(f"Erreur lors du traitement de date_fin: {str(e)}")
                            pass

                    # Détermination des collections à utiliser
                    collections = self.determine_collections(analysis)
                    self.logger.info(f"Collections sélectionnées: {collections}")

                    try:
                        # Exécution des recherches coordonnées
                        resultats = await self.recherche_coordonnee(
                            collections=collections,
                            question=text,
                            client_info=client_info,
                            date_debut=date_debut,
                            date_fin=date_fin
                        )
                    except Exception as e:
                        self.logger.error(f"Erreur recherche_coordonnee: {str(e)}")
                        return {
                            "text": f"Une erreur est survenue lors de la recherche: {str(e)}",
                            "blocks": [{
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": f"❌ **Erreur de recherche**: {str(e)}\n\nVeuillez réessayer ou contacter l'administrateur si le problème persiste."}
                            }]
                        }

                    if not resultats:
                        return {
                            "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question.",
                            "blocks": [{
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question."}
                            }]
                        }
                    # Choix du format selon le mode transmis
                    if mode == "detail":
                        # Retourner directement les résultats détaillés
                        detailed_response = await self.format_response(
                            resultats, 
                            text, 
                            debug_zendesk=debug_zendesk, 
                            progressive=progressive
                        )
                        return detailed_response
                    else:
                        # Pour le mode guide, générer un résumé avec boutons d'action
                        summary = await self.generate_summary(resultats, text)
                        action_buttons = { 
                            "type": "actions",
                            "elements": [
                                {"type": "button", "text": {"type": "plain_text", "text": "Détails", "emoji": True}, "value": f"details:{text}"},
                                {"type": "button", "text": {"type": "plain_text", "text": "Guide", "emoji": True}, "value": f"guide:{text}"}
                            ]
                        }
                        return {
                            "text": summary,
                            "blocks": [
                                {"type": "section", "text": {"type": "mrkdwn", "text": f"Résumé\n\n{summary}"}},
                                action_buttons
                            ]
                        }
            except asyncio.TimeoutError:
                self.logger.error(f"Timeout lors du traitement du message: '{text}'")
                return {
                    "text": "Désolé, le traitement de votre demande a pris trop de temps. Pourriez-vous simplifier votre question ou la reformuler ?",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "Désolé, le traitement de votre demande a pris trop de temps. Pourriez-vous simplifier votre question ou la reformuler ?"}
                    }]
                }

        except Exception as e:
            self.logger.error(f"Erreur process_web_message: {str(e)}")
            elapsed_time = time.monotonic() - start_time
            self.logger.error(f"Échec après {elapsed_time:.2f}s")

            # Détection des erreurs spécifiques
            error_message = str(e)
            if "can't be used in 'await' expression" in error_message:
                return {
                    "text": "Une erreur technique est survenue. Un client de recherche n'est pas correctement configuré pour les appels asynchrones.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "⚠️ **Erreur technique**: Un client de recherche n'est pas correctement configuré pour les appels asynchrones. L'équipe technique a été informée et travaille à résoudre ce problème."}
                    }]
                }
            elif "OpenAI" in error_message and "API key" in error_message:
                return {
                    "text": "Erreur d'authentification API OpenAI. Veuillez vérifier votre clé API.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "❌ **Erreur d'authentification OpenAI**: Votre clé API semble être incorrecte ou expirée. Veuillez vérifier les paramètres de configuration."}
                    }]
                }
            else:
                return {
                    "text": f"Une erreur est survenue pendant le traitement: {str(e)}",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"❌ **Erreur de traitement**: {str(e)}\n\nVeuillez réessayer ou contacter l'administrateur si le problème persiste."}
                    }]
                }
            
   
    async def handle_action_button(self, action_type: str, action_value: str, conversation: Any, user_id: str,
                                  debug_zendesk: bool = False, progressive: bool = False):
        """
        Gère les actions des boutons cliqués par l'utilisateur.
        
        Args:
            action_type: Type d'action ('details', 'guide', etc.)
            action_value: Valeur associée (généralement la question originale)
            conversation: Contexte de conversation
            user_id: Identifiant de l'utilisateur
            debug_zendesk: Activer le mode débogage pour les résultats Zendesk
            progressive: Activer le formatage progressif des résultats
            
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
                        "text": {"type": "mrkdwn", "text": "Action non valide: paramètres manquants"}
                    }]
                }
                
            # Récupération du contexte des résultats précédents
            context = json.loads(conversation.context) if conversation.context else {}
            last_results = context.get('last_results', [])
            
            if action_type == "details":
                # Afficher les détails des résultats
                detailed_response = await self.format_response(last_results, action_value, 
                                                              debug_zendesk=debug_zendesk, 
                                                              progressive=progressive)
                return detailed_response
                
            elif action_type == "guide":
                # Générer un guide étape par étape
                guide = await self.generate_guide(last_results, action_value)
                return {
                    "text": guide,
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"Guide étape par étape\n\n{guide}"}
                    }]
                }
                
            elif action_type == "summary":
                # Regenerer un résumé
                summary = await self.generate_summary(last_results, action_value)
                
                # Préparation des boutons pour changer de mode
                action_buttons = {
                    "type": "actions",
                    "elements": [
                        {"type": "button", "text": {"type": "plain_text", "text": "Détails", "emoji": True}, "value": f"details:{action_value}"},
                        {"type": "button", "text": {"type": "plain_text", "text": "Guide", "emoji": True}, "value": f"guide:{action_value}"}
                    ]
                }
                
                return {
                    "text": summary,
                    "blocks": [
                        {"type": "section", "text": {"type": "mrkdwn", "text": f"Résumé\n\n{summary}"}},
                        action_buttons
                    ]
                }
                
            else:
                return {
                    "text": f"Action non reconnue: {action_type}",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"Action non reconnue: {action_type}"}
                    }]
                }
                
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement de l'action {action_type}: {str(e)}")
            return {
                "text": f"Erreur lors du traitement de l'action: {str(e)}",
                "blocks": [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"Erreur lors du traitement de l'action: {str(e)}"}
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
                        "text": {"type": "mrkdwn", "text": "Contexte de conversation effacé."}
                    }]
                }
            except Exception as e:
                self.logger.error(f"Erreur lors de l'effacement du contexte: {str(e)}")
                return {
                    "text": "Erreur lors de l'effacement du contexte.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "Erreur lors de l'effacement du contexte."}
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
                openai_status = "Connecté"
                try:
                    await self.openai_client.models.list()
                except Exception as e:
                    self.logger.error(f"Erreur de connexion OpenAI: {str(e)}")
                    openai_status = "Erreur de connexion"
                
                # Stats du cache
                cache_stats = await global_cache.get_stats() if hasattr(global_cache, 'get_stats') else {"items": "N/A"}
                
                # Formatage du message
                status_message = """
                    *État des services ITS Help*

                    *OpenAI:* """ + openai_status + """
                    *Cache:* """ + str(cache_stats.get('items', 'N/A')) + """ éléments

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
                        "text": {"type": "mrkdwn", "text": f"Erreur lors de la vérification du statut: {str(e)}"}
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
                        "text": {"type": "mrkdwn", "text": "Veuillez spécifier un sujet pour le guide."}
                    }]
                }
                
            # Exécution comme une requête normale avec mode guide forcé
            return await self.process_web_message(
                "guide étape par étape pour " + topic,
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
                        "text": {"type": "mrkdwn", "text": "Veuillez spécifier un nom de client."}
                    }]
                }
                
            # Vérification de l'existence du client
            client_name, _, _ = await extract_client_name(client_name)
            if not client_name:
                return {
                    "text": "Client non trouvé.",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "Client non trouvé dans la base de données."}
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
                        "text": {"type": "mrkdwn", "text": f"Client par défaut défini: *{client_name}*"}
                    }]
                }
            except Exception as e:
                return {
                    "text": f"Erreur lors du stockage du client: {str(e)}",
                    "blocks": [{
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"Erreur lors du stockage du client: {str(e)}"}
                    }]
                }
                
        else:
            # Commande inconnue
            return {
                "text": "Commande non reconnue.",
                "blocks": [{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "Commande non reconnue. Tapez `/help` pour voir les commandes disponibles."}
                }]
            }