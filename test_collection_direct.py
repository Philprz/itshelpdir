#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_collection_direct.py
Script pour tester directement l'accès aux collections Qdrant sans passer par la factory.
"""

import os
import time
import asyncio
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Chargement des variables d'environnement
load_dotenv(verbose=True)
print("Variables d'environnement chargées :")
print(f"OPENAI_API_KEY: {'Définie' if os.getenv('OPENAI_API_KEY') else 'Non définie'}")
print(f"QDRANT_URL: {'Définie' if os.getenv('QDRANT_URL') else 'Non définie'}")
print(f"QDRANT_API_KEY: {'Définie' if os.getenv('QDRANT_API_KEY') else 'Non définie'}")

async def test_direct_search(collection_name, query_text="configuration"):
    """Teste directement une recherche sur une collection Qdrant."""
    print(f"\n{'=' * 80}")
    print(f"TEST DIRECT DE LA COLLECTION: {collection_name}")
    print(f"{'=' * 80}")
    
    try:
        # Initialisation du client Qdrant
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not qdrant_url:
            print("Erreur: URL Qdrant manquante!")
            return
        
        start_time = time.monotonic()
        print(f"Connexion à Qdrant: {qdrant_url}")
        client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=30
        )
        print(f"Client Qdrant initialisé en {time.monotonic() - start_time:.2f}s")
        
        # Vérification de l'existence de la collection
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if collection_name not in collection_names:
            print(f"ERREUR: La collection {collection_name} n'existe pas!")
            print(f"Collections disponibles: {collection_names}")
            return
            
        # Tentative de récupération des informations sur la collection
        try:
            collection_info = client.get_collection(collection_name)
            print(f"Informations sur la collection {collection_name}:")
            print(f"  - Vecteurs: {collection_info.vectors_count}")
            print(f"  - Dimension: {collection_info.config.params.vectors.size}")
        except Exception as e:
            print(f"Erreur lors de la récupération des informations de la collection: {str(e)}")
        
        # Fournir un vecteur fictif pour tester la recherche
        # Dans un cas réel, nous utiliserions le service d'embedding
        dummy_vector = [0.0] * 1536  # Dimension standard pour OpenAI embeddings
        
        # Effectuer une recherche de test
        search_start_time = time.monotonic()
        print(f"Recherche dans la collection {collection_name}...")
        search_results = client.search(
            collection_name=collection_name,
            query_vector=dummy_vector,
            limit=5
        )
        search_time = time.monotonic() - search_start_time
        
        # Afficher les résultats
        print(f"Recherche effectuée en {search_time:.2f}s")
        print(f"Nombre de résultats: {len(search_results)}")
        
        if search_results:
            print("\nAperçu des résultats:")
            for i, result in enumerate(search_results[:3], 1):
                print(f"Résultat #{i}:")
                print(f"  - Score: {result.score}")
                print(f"  - Payload: {list(result.payload.keys())[:5]} {'...' if len(result.payload) > 5 else ''}")
        
    except Exception as e:
        print(f"Erreur lors du test de la collection: {str(e)}")

async def main():
    """Fonction principale d'exécution."""
    collections_to_test = ["NETSUITE", "NETSUITE_DUMMIES", "SAP"]
    
    for collection in collections_to_test:
        await test_direct_search(collection)
        print("\n")

if __name__ == "__main__":
    asyncio.run(main())
