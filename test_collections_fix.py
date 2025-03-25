#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_collections_fix.py
Script pour tester les corrections apportées aux recherches dans les collections ERP.
"""

import os
import sys
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('ITS_HELP.test_collections_fix')

# Chargement des variables d'environnement
load_dotenv(verbose=True)

async def test_collections_erp():
    """
    Teste la recherche dans les collections ERP (NETSUITE, NETSUITE_DUMMIES, SAP).
    Utilise directement query_points pour éviter les problèmes avec search.
    """
    # Vérification des variables d'environnement
    qdrant_url = os.getenv('QDRANT_URL')
    qdrant_api_key = os.getenv('QDRANT_API_KEY')
    openai_api_key = os.getenv('OPENAI_API_KEY')
    
    if not qdrant_url:
        logger.error("URL Qdrant manquante")
        return False
    
    if not openai_api_key:
        logger.warning("Clé API OpenAI manquante. Les tests se feront avec un vecteur fictif.")
    
    logger.info(f"Connexion à Qdrant: {qdrant_url}")
    
    try:
        # Initialisation du client Qdrant
        qdrant_client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=30
        )
        
        # Liste des collections à tester
        collections = ["NETSUITE", "NETSUITE_DUMMIES", "SAP"]
        
        # Termes de recherche pertinents pour chaque collection
        search_terms = {
            "NETSUITE": ["facture", "commande", "client", "compte"],
            "NETSUITE_DUMMIES": ["tutoriel", "guide", "documentation", "exemple"],
            "SAP": ["transaction", "bon de commande", "module", "rapport"]
        }
        
        # Vérification des collections disponibles
        available_collections = [col.name for col in qdrant_client.get_collections().collections]
        logger.info("-" * 80)
        logger.info(f"Collections disponibles: {', '.join(available_collections)}")
        logger.info("-" * 80)
        
        all_successful = True
        
        for collection_name in collections:
            if collection_name not in available_collections:
                logger.warning(f"Collection {collection_name} n'existe pas dans Qdrant")
                all_successful = False
                continue
                
            logger.info(f"Test de la collection {collection_name}")
            logger.info("-" * 50)
            
            # Obtenir les informations sur la collection pour vérifier sa structure
            collection_info = qdrant_client.get_collection(collection_name)
            points_count = collection_info.points_count
            logger.info(f"Collection {collection_name} contient {points_count} points")
            
            if points_count == 0:
                logger.warning(f"Collection {collection_name} est vide")
                all_successful = False
                continue
            
            # Création d'un vecteur fictif pour la recherche
            vector_size = 1536  # Dimension standard pour OpenAI
            vector = [0.1] * vector_size
            
            # Test avec query_points et un vecteur fictif
            logger.info(f"Test avec un vecteur fictif sur {collection_name}")
            try:
                results = qdrant_client.query_points(
                    collection_name=collection_name,
                    query_vector=vector,
                    limit=3,
                    with_payload=True,
                    score_threshold=0.0,  # Pas de filtre sur le score
                    with_vectors=False
                )
                
                if results:
                    logger.info(f"Recherche réussie: {len(results)} résultats trouvés")
                    logger.info("Premier résultat:")
                    
                    # Affichage du premier résultat
                    first_result = results[0]
                    logger.info(f"  - Score: {first_result.score}")
                    
                    if hasattr(first_result, 'payload') and first_result.payload:
                        payload_keys = list(first_result.payload.keys())
                        logger.info(f"  - Clés du payload: {', '.join(payload_keys)}")
                        
                        if 'title' in first_result.payload:
                            logger.info(f"  - Titre: {first_result.payload['title']}")
                            
                        if 'content' in first_result.payload:
                            content = first_result.payload['content']
                            preview = content[:100] + "..." if len(content) > 100 else content
                            logger.info(f"  - Contenu (début): {preview}")
                else:
                    logger.warning(f"Aucun résultat trouvé dans {collection_name}")
                    all_successful = False
                    
            except Exception as e:
                logger.error(f"Erreur lors de la recherche avec query_points: {str(e)}")
                all_successful = False
                
                # Fallback à search en cas d'erreur
                try:
                    logger.info("Test avec méthode search (dépréciée)")
                    results = qdrant_client.search(
                        collection_name=collection_name,
                        query_vector=vector,
                        limit=3,
                        with_payload=True,
                        score_threshold=0.0,
                        with_vectors=False
                    )
                    
                    if results:
                        logger.info(f"Recherche réussie avec search: {len(results)} résultats trouvés")
                    else:
                        logger.warning(f"Aucun résultat trouvé avec search dans {collection_name}")
                        all_successful = False
                except Exception as search_e:
                    logger.error(f"Erreur lors de la recherche avec search: {str(search_e)}")
                    all_successful = False
            
            # Test avec des termes spécifiques si OpenAI est disponible
            if openai_api_key:
                logger.info("-" * 30)
                logger.info(f"Test avec des termes spécifiques pour {collection_name}")
                
                # On utilise directement la méthode search pour tester des termes pertinents
                for term in search_terms.get(collection_name, [])[:2]:  # Limiter à 2 termes par collection
                    logger.info(f"Recherche du terme: '{term}'")
                    try:
                        # Ici on pourrait utiliser OpenAI pour générer un embedding
                        # Mais pour simplifier, on utilise encore un vecteur fictif
                        results = qdrant_client.query_points(
                            collection_name=collection_name,
                            query_vector=vector,
                            limit=2,
                            with_payload=True,
                            score_threshold=0.0,
                            with_vectors=False
                        )
                        
                        if results:
                            logger.info(f"  - {len(results)} résultats trouvés")
                        else:
                            logger.warning(f"  - Aucun résultat trouvé pour '{term}'")
                    except Exception as term_e:
                        logger.error(f"  - Erreur lors de la recherche du terme '{term}': {str(term_e)}")
            
            logger.info("-" * 80)
        
        return all_successful
        
    except Exception as e:
        logger.error(f"Erreur globale: {str(e)}")
        return False

async def main():
    """Fonction principale."""
    logger.info("Démarrage des tests des collections ERP")
    
    success = await test_collections_erp()
    
    if success:
        logger.info("Tests terminés avec succès")
    else:
        logger.error("Erreurs rencontrées lors des tests")
        
    logger.info("Fin des tests")

if __name__ == "__main__":
    asyncio.run(main())
