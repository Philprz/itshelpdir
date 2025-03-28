"""
Exemple d'optimisation de requêtes avec la nouvelle architecture

Ce script démontre comment utiliser les adaptateurs LLM, les services d'embedding
et les adaptateurs vectoriels ensemble pour optimiser les requêtes utilisateur.
"""

import asyncio
import os
import logging
import time
import argparse
from typing import Dict, List, Any, Optional

# Import de la nouvelle architecture
from src.adapters import LLMAdapterFactory, EmbeddingServiceFactory, VectorStoreFactory
from src.infrastructure.cache import IntelligentCache, get_cache_instance

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ITS_HELP.examples.query_optimization")

# Variables d'environnement nécessaires - pour l'exemple, nous définissons des valeurs par défaut
os.environ.setdefault("OPENAI_API_KEY", "sk-...")  # À remplacer avec votre clé API
os.environ.setdefault("DEFAULT_OPENAI_MODEL", "gpt-3.5-turbo")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

async def optimize_query(query: str, use_cache: bool = True) -> Dict[str, Any]:
    """
    Optimise une requête utilisateur en utilisant le LLM et les embeddings
    
    Args:
        query: Requête brute de l'utilisateur
        use_cache: Utiliser le cache intelligent
        
    Returns:
        Résultat optimisé avec requête reformulée et documents pertinents
    """
    start_time = time.time()
    
    # Étape 1: Initialiser les composants
    llm_adapter = LLMAdapterFactory.create_adapter("openai")
    embedding_service = EmbeddingServiceFactory.create_service("openai", llm_adapter=llm_adapter)
    vector_store = VectorStoreFactory.create_adapter("qdrant", embedding_service=embedding_service)
    
    # Obtenir l'instance du cache
    cache = get_cache_instance() if use_cache else None
    
    # Étape 2: Vérifier si la requête est dans le cache
    cache_key = f"query_optimization:{query}"
    if cache:
        cached_result = await cache.get(cache_key)
        if cached_result:
            logger.info(f"Résultat récupéré du cache en {time.time() - start_time:.2f}s")
            cached_result["cache_hit"] = True
            cached_result["latency"] = time.time() - start_time
            return cached_result
    
    # Étape 3: Reformuler la requête avec le LLM
    query_analysis_prompt = [
        {"role": "system", "content": """
        Vous êtes un assistant spécialisé dans l'analyse et l'optimisation de requêtes.
        Votre tâche est d'analyser la requête de l'utilisateur et de la reformuler
        pour améliorer les résultats de recherche.
        
        Fournissez une analyse structurée avec:
        1. Une reformulation claire de la requête
        2. Les mots-clés importants
        3. Le contexte probable de la requête
        4. Les sources de données pertinentes (Jira, NetSuite, SAP, Zendesk, Confluence)
        """},
        {"role": "user", "content": f"Analysez et optimisez la requête suivante: {query}"}
    ]
    
    query_analysis = await llm_adapter.complete(query_analysis_prompt)
    
    # Étape 4: Extraire les mots-clés pour la recherche vectorielle
    optimized_query = query  # Par défaut, utiliser la requête originale
    keywords = [query]
    relevant_sources = []
    
    try:
        # Analyser la réponse du LLM pour extraire les informations
        response_content = query_analysis.response
        
        # Rechercher la reformulation
        if "reformulation" in response_content.lower():
            # Extraire la partie reformulée
            lines = response_content.split("\n")
            for i, line in enumerate(lines):
                if "reformulation" in line.lower() and i+1 < len(lines):
                    optimized_query = lines[i+1].strip().strip(":.\"'-")
                    break
        
        # Rechercher les mots-clés
        if "mots-clés" in response_content.lower() or "keywords" in response_content.lower():
            # Extraire les mots-clés
            lines = response_content.split("\n")
            for i, line in enumerate(lines):
                if ("mots-clés" in line.lower() or "keywords" in line.lower()) and i+1 < len(lines):
                    keywords_line = lines[i+1].strip().strip(":.\"'-")
                    keywords = [k.strip() for k in keywords_line.split(",")]
                    break
        
        # Rechercher les sources pertinentes
        sources = ["jira", "netsuite", "sap", "zendesk", "confluence"]
        for source in sources:
            if source.lower() in response_content.lower():
                relevant_sources.append(source)
        
    except Exception as e:
        logger.warning(f"Erreur lors de l'analyse de la réponse LLM: {str(e)}")
    
    # Étape 5: Rechercher des documents pertinents dans la base vectorielle
    relevant_docs = []
    
    try:
        # Pour chaque collection pertinente, effectuer une recherche
        for source in relevant_sources:
            collection_name = f"{source}_docs"
            
            # Rechercher avec la requête optimisée
            source_docs = await vector_store.search_by_text(
                query_text=optimized_query,
                collection_name=collection_name,
                limit=3
            )
            
            # Ajouter la source aux documents
            for doc in source_docs:
                doc["source"] = source
                relevant_docs.append(doc)
        
        # Si aucune source spécifique n'a été identifiée, rechercher dans toutes les collections
        if not relevant_docs:
            collections = await vector_store.list_collections()
            
            for collection in collections:
                # Rechercher avec la requête optimisée
                collection_docs = await vector_store.search_by_text(
                    query_text=optimized_query,
                    collection_name=collection,
                    limit=2
                )
                
                # Ajouter la collection aux documents
                for doc in collection_docs:
                    doc["source"] = collection.replace("_docs", "")
                    relevant_docs.append(doc)
        
        # Trier par score
        relevant_docs.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # Limiter le nombre total de documents
        relevant_docs = relevant_docs[:5]
        
    except Exception as e:
        logger.warning(f"Erreur lors de la recherche vectorielle: {str(e)}")
    
    # Étape 6: Préparer le résultat
    result = {
        "original_query": query,
        "optimized_query": optimized_query,
        "keywords": keywords,
        "relevant_sources": relevant_sources,
        "llm_analysis": query_analysis.response,
        "relevant_docs": relevant_docs,
        "latency": time.time() - start_time,
        "cache_hit": False,
        "tokens_used": {
            "prompt": query_analysis.prompt_tokens,
            "completion": query_analysis.completion_tokens,
            "total": query_analysis.total_tokens
        }
    }
    
    # Étape 7: Mettre en cache le résultat
    if cache:
        await cache.set(
            key=cache_key,
            value=result,
            ttl=3600  # 1 heure
        )
    
    logger.info(f"Requête optimisée en {time.time() - start_time:.2f}s")
    return result

async def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(description="Exemple d'optimisation de requêtes")
    parser.add_argument("query", type=str, help="Requête à optimiser")
    parser.add_argument("--no-cache", action="store_true", help="Désactiver le cache")
    args = parser.parse_args()
    
    # Optimiser la requête
    result = await optimize_query(args.query, not args.no_cache)
    
    # Afficher le résultat
    print("\n" + "=" * 80)
    print(f"Requête originale: {result['original_query']}")
    print(f"Requête optimisée: {result['optimized_query']}")
    print(f"Mots-clés: {', '.join(result['keywords'])}")
    print(f"Sources pertinentes: {', '.join(result['relevant_sources'])}")
    print("\nAnalyse LLM:")
    print("-" * 40)
    print(result['llm_analysis'])
    print("\nDocuments pertinents:")
    print("-" * 40)
    
    for i, doc in enumerate(result['relevant_docs']):
        print(f"{i+1}. [{doc['source']}] {doc.get('payload', {}).get('title', 'Sans titre')}")
        print(f"   Score: {doc.get('score', 0):.4f}")
        print(f"   {doc.get('payload', {}).get('text', '')[:100]}...")
        print()
    
    print("\nStatistiques:")
    print("-" * 40)
    print(f"Latence: {result['latency']:.2f}s")
    print(f"Cache hit: {result['cache_hit']}")
    print(f"Tokens utilisés: {result['tokens_used']['total']} (prompt: {result['tokens_used']['prompt']}, completion: {result['tokens_used']['completion']})")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
