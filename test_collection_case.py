#!/usr/bin/env python3
"""
Script de test pour vérifier l'accès aux collections Qdrant 
en utilisant les noms en majuscules vs minuscules.
"""

import os
import asyncio
import logging
from qdrant_client import QdrantClient

# Configuration de logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_collection_case')

async def test_collections():
    """Test l'accès aux collections avec différentes casses"""
    # Récupération des variables d'environnement
    qdrant_url = os.getenv('QDRANT_URL')
    qdrant_api_key = os.getenv('QDRANT_API_KEY')
    
    if not qdrant_url:
        logger.error("Variable d'environnement QDRANT_URL non définie")
        return False
    
    logger.info(f"Connexion à Qdrant: {qdrant_url}")
    
    try:
        # Initialisation du client Qdrant
        client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=30
        )
        
        # Liste des collections à tester (minuscules et majuscules)
        test_cases = [
            ('netsuite', 'NETSUITE'),
            ('sap', 'SAP'),
            ('netsuite_dummies', 'NETSUITE_DUMMIES'),
            ('confluence', 'CONFLUENCE'),
            ('zendesk', 'ZENDESK'),
            ('jira', 'JIRA')
        ]
        
        # Liste toutes les collections disponibles
        collections_info = client.get_collections()
        available_collections = [c.name for c in collections_info.collections]
        logger.info(f"Collections disponibles: {available_collections}")
        
        # Test de l'existence des collections
        results = []
        for lowercase, uppercase in test_cases:
            lowercase_exists = False
            uppercase_exists = False
            
            try:
                # Test avec nom en minuscules
                _ = client.get_collection(lowercase)  # Utilisation de _ pour ignorer le résultat
                lowercase_exists = True
                logger.info(f"Collection '{lowercase}' existe")
            except Exception as e:
                logger.warning(f"Collection '{lowercase}' n'existe pas: {str(e)}")
            
            try:
                # Test avec nom en majuscules
                _ = client.get_collection(uppercase)  # Utilisation de _ pour ignorer le résultat
                uppercase_exists = True
                logger.info(f"Collection '{uppercase}' existe")
            except Exception as e:
                logger.warning(f"Collection '{uppercase}' n'existe pas: {str(e)}")
            
            results.append((lowercase, lowercase_exists, uppercase, uppercase_exists))
        
        # Affichage des résultats
        logger.info("\n============ RÉSULTATS ============")
        for lowercase, lowercase_exists, uppercase, uppercase_exists in results:
            logger.info(f"'{lowercase}': {'✅' if lowercase_exists else '❌'} | '{uppercase}': {'✅' if uppercase_exists else '❌'}")
        
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors du test des collections: {str(e)}")
        return False

if __name__ == "__main__":
    asyncio.run(test_collections())
