#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_erp_search.py
Script pour tester directement les clients de recherche ERP (NetSuite, SAP) sans passer par le chatbot.
"""

import os
import asyncio
import time
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Chargement des variables d'environnement
load_dotenv(verbose=True)
print("Variables d'environnement chargées :")
print(f"OPENAI_API_KEY: {'Définie' if os.getenv('OPENAI_API_KEY') else 'Non définie'}")
print(f"QDRANT_URL: {'Définie' if os.getenv('QDRANT_URL') else 'Non définie'}")
print(f"QDRANT_API_KEY: {'Définie' if os.getenv('QDRANT_API_KEY') else 'Non définie'}")

# Import d'un service d'embedding minimal
class MinimalEmbeddingService:
    """Service d'embedding minimal pour les tests."""
    async def get_embedding(self, text):
        """Retourne un vecteur factice de dimension 1536."""
        print(f"Génération d'un embedding factice pour: '{text[:30]}...'")
        return [0.0] * 1536

async def test_client_search():
    """Teste directement la recherche via les clients ERP."""
    print("\n" + "=" * 80)
    print("TEST DIRECT DES CLIENTS ERP")
    print("=" * 80)
    
    try:
        # Import des clients
        from search_clients import NetsuiteSearchClient, SapSearchClient, NetsuiteDummiesSearchClient
        
        # Initialisation du client Qdrant
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not qdrant_url:
            print("Erreur: URL Qdrant manquante!")
            return
        
        print(f"Connexion à Qdrant: {qdrant_url}")
        qdrant_client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=30
        )
        print("Client Qdrant initialisé")
        
        # Création du service d'embedding minimal
        embedding_service = MinimalEmbeddingService()
        
        # Questions de test
        questions = [
            "Comment paramétrer le compte fournisseur ?",
            "Configuration du compte client dans NetSuite",
            "Procédure de création d'un compte dans SAP"
        ]
        
        # Liste des collections à vérifier
        collections = ["NETSUITE", "NETSUITE_DUMMIES", "SAP"]
        
        # Vérifier d'abord si les collections existent
        print("\nVérification des collections disponibles:")
        try:
            collections_info = qdrant_client.get_collections()
            available_collections = [col.name for col in collections_info.collections]
            print(f"Collections disponibles: {available_collections}")
            
            for collection in collections:
                if collection in available_collections:
                    print(f" Collection {collection} existe")
                else:
                    print(f" Collection {collection} n'existe PAS")
        except Exception as e:
            print(f"Erreur lors de la vérification des collections: {str(e)}")
        
        # Test des clients
        clients = [
            ("NETSUITE", NetsuiteSearchClient("NETSUITE", qdrant_client, embedding_service)),
            ("NETSUITE_DUMMIES", NetsuiteDummiesSearchClient("NETSUITE_DUMMIES", qdrant_client, embedding_service)),
            ("SAP", SapSearchClient("SAP", qdrant_client, embedding_service))
        ]
        
        for client_name, client in clients:
            print(f"\n{'=' * 40}")
            print(f"Test du client: {client_name}")
            print(f"{'=' * 40}")
            
            for question in questions:
                print(f"\nQuestion: '{question}'")
                start_time = time.monotonic()
                
                try:
                    # Recherche avec un seuil très bas pour maximiser les résultats
                    results = await client.recherche_intelligente(
                        question=question,
                        limit=10,
                        score_threshold=0.0
                    )
                    
                    duration = time.monotonic() - start_time
                    print(f"Recherche effectuée en {duration:.2f}s")
                    print(f"Nombre de résultats: {len(results)}")
                    
                    if results:
                        print("\nAperçu des résultats:")
                        for i, result in enumerate(results[:3], 1):
                            print(f"Résultat #{i}:")
                            print(f"  - Score: {getattr(result, 'score', 'N/A')}")
                            if hasattr(result, 'payload'):
                                print(f"  - Payload keys: {list(result.payload.keys())[:5]} {'...' if len(result.payload) > 5 else ''}")
                                if 'title' in result.payload:
                                    print(f"  - Titre: {result.payload['title']}")
                                if 'content' in result.payload:
                                    content = result.payload['content']
                                    print(f"  - Contenu: {content[:100]}...") if len(content) > 100 else print(f"  - Contenu: {content}")
                    else:
                        print("Aucun résultat trouvé.")
                        
                except Exception as e:
                    print(f"Erreur lors de la recherche: {str(e)}")
                
                print("-" * 30)
                    
    except Exception as e:
        print(f"Erreur globale: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_client_search())
