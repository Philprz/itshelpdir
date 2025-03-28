"""
Module response_builder.py - Construction et formatage des réponses

Ce module implémente le générateur de réponses qui prend les résultats de recherche
et construit une réponse formatée et pertinente en utilisant un modèle de langage.
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field

from src.adapters.llm.factory import get_llm_adapter
from src.adapters.llm.base import LLMMessage, LLMConfig
from src.core.query_engine import QueryResult

# Configuration du logging
logger = logging.getLogger("ITS_HELP.core.response_builder")

# Prompt système par défaut pour la génération de réponses
DEFAULT_SYSTEM_PROMPT = """Tu es un assistant d'aide informatique professionnel et précis. 
Ta mission est de répondre aux questions des utilisateurs en te basant exclusivement sur les informations fournies dans le contexte.

Voici comment procéder:
1. Utilise UNIQUEMENT les informations du contexte fourni pour répondre.
2. Si le contexte ne contient pas suffisamment d'informations, indique-le clairement. Ne pas inventer de réponse.
3. Cite les sources pertinentes (avec leur URL si disponible) à la fin de ta réponse.
4. Fais des réponses concises mais complètes.
5. Présente les informations sous forme de liste à puces quand c'est pertinent.
6. Si tu détectes des étapes techniques, présente-les dans un ordre logique et numéroté.

Réponds en français, sauf si une autre langue est explicitement demandée."""

# Template pour la construction du contexte
CONTEXT_TEMPLATE = """## Contexte
{context_items}

## Question de l'utilisateur
{query}"""


class ResponseBuilder:
    """
    Constructeur de réponses intelligent utilisant un LLM
    
    Cette classe:
    1. Sélectionne et prépare les éléments de contexte pertinents
    2. Construit un prompt enrichi pour le LLM
    3. Génère une réponse cohérente et formatée
    4. Ajoute les métadonnées et citations nécessaires
    """
    
    def __init__(self):
        """Initialise le générateur de réponses"""
        self.llm_adapter = None
        self.instruction_templates = self._load_instruction_templates()
        
        # Configuration
        self.max_context_items = 15
        self.enable_custom_instructions = True
        self.system_prompt = DEFAULT_SYSTEM_PROMPT
        
        # État interne
        self._initialized = False
    
    def _load_instruction_templates(self) -> Dict[str, str]:
        """
        Charge les templates d'instructions personnalisées
        
        Returns:
            Dictionnaire de templates d'instructions
        """
        # Templates par défaut
        templates = {
            "default": DEFAULT_SYSTEM_PROMPT,
            "technical": """Tu es un expert technique précis. 
Réponds uniquement avec des informations factuelles basées sur le contexte fourni.
Présente les étapes techniques sous forme numérotée et ajoute des exemples de code si pertinent.""",
            "executive": """Tu es un assistant concis pour dirigeants pressés.
Réponds de manière directe et synthétique en 3-4 phrases maximum.
Mets en avant les points clés et les impacts business."""
        }
        
        # TODO: Charger depuis une configuration externe si disponible
        
        return templates
    
    async def initialize(self, max_context_items: int = 15, 
                      enable_custom_instructions: bool = True):
        """
        Initialise le générateur de réponses et ses dépendances
        
        Args:
            max_context_items: Nombre max d'éléments de contexte à inclure
            enable_custom_instructions: Activer les instructions personnalisées
        """
        if self._initialized:
            logger.debug("ResponseBuilder déjà initialisé, ignoré")
            return
            
        logger.info("Initialisation du ResponseBuilder...")
        start_time = time.time()
        
        # Mise à jour de la configuration
        self.max_context_items = max_context_items
        self.enable_custom_instructions = enable_custom_instructions
        
        # Initialisation de l'adaptateur LLM
        self.llm_adapter = await get_llm_adapter()
        
        # Vérification de la disponibilité du modèle
        health = await self.llm_adapter.health_check()
        if not health.get("available", False):
            logger.warning(f"LLM non disponible: {health.get('message', 'Raison inconnue')}")
        
        self._initialized = True
        duration = time.time() - start_time
        logger.info(f"ResponseBuilder initialisé en {duration:.2f}s")
    
    async def build_response(self, query: str, query_result: QueryResult,
                          user_id: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Construit une réponse basée sur les résultats de recherche
        
        Args:
            query: Texte de la requête originale
            query_result: Résultats de la recherche
            user_id: Identifiant de l'utilisateur (pour personnalisation)
            metadata: Métadonnées additionnelles
            
        Returns:
            Réponse formatée avec tous les détails
        """
        metadata = metadata or {}
        user_type = metadata.get("user_type", "default")
        
        if not self._initialized:
            await self.initialize()
        
        # Début du timing
        start_time = time.time()
        
        # 1. Sélection des éléments de contexte pertinents
        context_items = self._select_context_items(query_result)
        
        # 2. Construction du prompt pour le LLM
        system_prompt = self._get_system_prompt(user_type)
        user_prompt = self._build_context_prompt(query, context_items)
        
        # 3. Génération de la réponse via LLM
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]
        
        llm_config = LLMConfig(
            model="gpt-4-turbo-preview",  # Par défaut, peut être configuré
            temperature=0.7,
            top_p=1.0,
            max_tokens=1500
        )
        
        try:
            llm_response = await self.llm_adapter.complete(messages, llm_config)
            response_text = llm_response.content
            token_usage = llm_response.usage
        except Exception as e:
            logger.error(f"Erreur lors de la génération de la réponse: {str(e)}")
            response_text = "Désolé, je n'ai pas pu générer une réponse. Veuillez réessayer ou contacter le support."
            token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        # 4. Construction du résultat final
        citations = self._extract_citations(context_items)
        
        result = {
            "query": query,
            "response": response_text,
            "citations": citations,
            "metadata": {
                "processing_time": time.time() - start_time,
                "token_usage": token_usage,
                "context_items": len(context_items),
                "sources": query_result.sources,
                "query_execution_time": query_result.execution_time
            }
        }
        
        # Ajouter les métadonnées utilisateur si disponibles
        if user_id:
            result["metadata"]["user_id"] = user_id
            
        if metadata:
            for key, value in metadata.items():
                if key not in result["metadata"]:
                    result["metadata"][key] = value
        
        return result
    
    def _select_context_items(self, query_result: QueryResult) -> List[Dict[str, Any]]:
        """
        Sélectionne les éléments de contexte les plus pertinents
        
        Args:
            query_result: Résultats de la recherche
            
        Returns:
            Liste des éléments de contexte sélectionnés
        """
        all_items = []
        
        # Collecte de tous les résultats avec leur source
        for source, results in query_result.results.items():
            for result in results:
                # S'assurer que la source est présente dans le résultat
                if "source" not in result:
                    result["source"] = source
                    
                all_items.append(result)
        
        # Tri par score de pertinence décroissant
        sorted_items = sorted(all_items, key=lambda x: float(x.get("score", 0)), reverse=True)
        
        # Limitation au nombre maximum d'éléments
        selected_items = sorted_items[:self.max_context_items]
        
        # S'assurer de la diversité des sources (au moins un élément de chaque source si possible)
        if len(selected_items) < len(query_result.sources):
            source_present = {source: False for source in query_result.sources}
            
            # Vérifier les sources déjà présentes
            for item in selected_items:
                source_present[item.get("source", "")] = True
            
            # Ajouter des éléments de sources manquantes
            for source, present in source_present.items():
                if not present and source in query_result.results:
                    if query_result.results[source]:
                        best_item = max(query_result.results[source], key=lambda x: float(x.get("score", 0)))
                        if best_item not in selected_items:
                            selected_items.append(best_item)
            
            # Re-trier et limiter si nécessaire
            selected_items = sorted(selected_items, key=lambda x: float(x.get("score", 0)), reverse=True)
            selected_items = selected_items[:self.max_context_items]
        
        return selected_items
    
    def _get_system_prompt(self, user_type: str = "default") -> str:
        """
        Récupère le prompt système approprié selon le type d'utilisateur
        
        Args:
            user_type: Type d'utilisateur (default, technical, executive, etc.)
            
        Returns:
            Prompt système
        """
        if not self.enable_custom_instructions:
            return DEFAULT_SYSTEM_PROMPT
            
        if user_type in self.instruction_templates:
            return self.instruction_templates[user_type]
            
        return DEFAULT_SYSTEM_PROMPT
    
    def _build_context_prompt(self, query: str, context_items: List[Dict[str, Any]]) -> str:
        """
        Construit le prompt de contexte pour le LLM
        
        Args:
            query: Texte de la requête
            context_items: Éléments de contexte sélectionnés
            
        Returns:
            Prompt formaté avec contexte
        """
        # Construction des éléments de contexte
        context_texts = []
        
        for i, item in enumerate(context_items, 1):
            # Extraction des informations pertinentes
            content = item.get("content", {})
            metadata = item.get("metadata", {})
            source = item.get("source", "inconnu")
            
            # Extraction du texte principal
            main_text = content.get("text", "")
            if not main_text:
                # Recherche alternative du texte principal
                for field in ["content", "description", "body", "message"]:
                    if field in content and content[field]:
                        main_text = str(content[field])
                        break
            
            # Extraction du titre
            title_fields = ["title", "subject", "name", "key", "id"]
            title = None
            for field in title_fields:
                if field in content and content[field]:
                    title = content[field]
                    break
                elif field in metadata and metadata[field]:
                    title = metadata[field]
                    break
            
            # Extraction de l'URL
            url = None
            url_fields = ["url", "link", "href"]
            for field in url_fields:
                if field in content and content[field]:
                    url = content[field]
                    break
                elif field in metadata and metadata[field]:
                    url = metadata[field]
                    break
            
            # Construction du texte de contexte
            context_text = f"### Source {i}: {source.upper()}"
            
            if title:
                context_text += f"\n**Titre:** {title}"
                
            if url:
                context_text += f"\n**URL:** {url}"
            
            if main_text:
                # Limitation de la taille du texte pour éviter les dépassements de contexte
                max_text_length = 1000
                if len(main_text) > max_text_length:
                    main_text = main_text[:max_text_length] + "..."
                
                context_text += f"\n\n{main_text}"
            
            context_texts.append(context_text)
        
        # Construction du prompt final avec le template
        context_items_text = "\n\n".join(context_texts)
        final_prompt = CONTEXT_TEMPLATE.format(
            context_items=context_items_text,
            query=query
        )
        
        return final_prompt
    
    def _extract_citations(self, context_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extrait les informations de citation des éléments de contexte
        
        Args:
            context_items: Éléments de contexte
            
        Returns:
            Liste des citations formatées
        """
        citations = []
        
        for item in context_items:
            content = item.get("content", {})
            metadata = item.get("metadata", {})
            source = item.get("source", "inconnu")
            
            citation = {
                "source": source,
                "score": float(item.get("score", 0))
            }
            
            # Extraction du titre
            title_fields = ["title", "subject", "name", "key", "id"]
            for field in title_fields:
                if field in content and content[field]:
                    citation["title"] = content[field]
                    break
                elif field in metadata and metadata[field]:
                    citation["title"] = metadata[field]
                    break
            
            # Extraction de l'URL
            url_fields = ["url", "link", "href"]
            for field in url_fields:
                if field in content and content[field]:
                    citation["url"] = content[field]
                    break
                elif field in metadata and metadata[field]:
                    citation["url"] = metadata[field]
                    break
            
            # Extraction de la date si disponible
            date_fields = ["date", "created_at", "updated_at", "timestamp"]
            for field in date_fields:
                if field in content and content[field]:
                    citation["date"] = content[field]
                    break
                elif field in metadata and metadata[field]:
                    citation["date"] = metadata[field]
                    break
            
            citations.append(citation)
        
        return citations
    
    def get_status(self) -> Dict[str, Any]:
        """
        Renvoie l'état actuel du générateur de réponses
        
        Returns:
            Dictionnaire avec les informations d'état
        """
        status = {
            "initialized": self._initialized,
            "max_context_items": self.max_context_items,
            "enable_custom_instructions": self.enable_custom_instructions,
            "llm_available": self.llm_adapter is not None,
            "instruction_templates": list(self.instruction_templates.keys())
        }
        
        # Ajouter les informations sur le modèle si disponible
        if self.llm_adapter:
            status["llm_provider"] = self.llm_adapter.provider_name
            status["available_models"] = self.llm_adapter.available_models
        
        return status
    
    async def shutdown(self):
        """Arrête proprement le générateur de réponses et ses ressources"""
        logger.info("Arrêt du ResponseBuilder...")
        logger.info("ResponseBuilder arrêté avec succès")
