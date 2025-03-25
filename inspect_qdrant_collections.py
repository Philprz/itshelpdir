#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
inspect_qdrant_collections.py
Script pour inspecter en détail les collections Qdrant existantes et leur contenu.
"""

import os
import time
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models  # noqa: F401

# Chargement des variables d'environnement
load_dotenv(verbose=True)
print("Variables d'environnement chargées :")
print(f"OPENAI_API_KEY: {'Définie' if os.getenv('OPENAI_API_KEY') else 'Non définie'}")
print(f"QDRANT_URL: {'Définie' if os.getenv('QDRANT_URL') else 'Non définie'}")
print(f"QDRANT_API_KEY: {'Définie' if os.getenv('QDRANT_API_KEY') else 'Non définie'}")

def inspect_collections():
    """Inspecte en détail les collections Qdrant existantes."""
    print("\n" + "=" * 80)
    print("INSPECTION DES COLLECTIONS QDRANT")
    print("=" * 80)
    
    try:
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
        
        # Liste des collections à inspecter
        erp_collections = ["NETSUITE", "NETSUITE_DUMMIES", "SAP"]
        
        # Récupérer toutes les collections disponibles
        print("\nCollections disponibles:")
        try:
            collections_info = qdrant_client.get_collections()
            available_collections = [col.name for col in collections_info.collections]
            print(f"{available_collections}")
            
            # Inspection détaillée de chaque collection ERP
            for collection_name in erp_collections:
                print(f"\n{'=' * 40}")
                print(f"Inspection de la collection: {collection_name}")
                print(f"{'=' * 40}")
                
                if collection_name not in available_collections:
                    print(f"❌ Collection {collection_name} n'existe PAS")
                    continue
                
                # 1. Obtenir les informations détaillées sur la collection
                try:
                    collection_info = qdrant_client.get_collection(collection_name=collection_name)
                    print("\nInformations sur la collection:")
                    print(f"  - Vecteurs: {collection_info.config.params.vectors}")
                    print(f"  - Points: {collection_info.points_count}")
                    print(f"  - Segments: {collection_info.segments_count}")
                    
                    # Dimension des vecteurs
                    vector_size = None
                    if hasattr(collection_info.config.params, 'vectors'):
                        vectors_config = collection_info.config.params.vectors
                        if hasattr(vectors_config, 'dict'):
                            try:
                                for vector_name, vector_config in vectors_config.dict().items():
                                    vector_size = vector_config.get('size')
                                    print(f"  - Vecteur '{vector_name}': Dimension {vector_size}")
                            except Exception as e:
                                print(f"  - Erreur lors de l'accès aux configurations de vecteurs: {str(e)}")
                                # Fallback: utiliser une dimension standard de 1536 pour OpenAI
                                vector_size = 1536
                                print("  - Utilisation d'une dimension par défaut: 1536")
                        else:
                            print("  - Configuration des vecteurs présente mais format inattendu")
                            vector_size = 1536
                    else:
                        print("  - Pas de configuration de vecteurs trouvée")
                        vector_size = 1536
                except Exception as e:
                    print(f"Erreur lors de la récupération des informations de collection: {str(e)}")
                    continue
                
                # 2. Obtenir un échantillon de points pour analyser la structure
                try:
                    print("\nÉchantillon de points:")
                    # Utiliser scroll pour récupérer quelques points
                    start_time = time.time()
                    sample_points = qdrant_client.scroll(
                        collection_name=collection_name,
                        limit=3,
                        with_payload=True,
                        with_vectors=False  # Pour éviter de récupérer les vecteurs complets
                    )
                    end_time = time.time()
                    print(f"Temps de récupération: {end_time - start_time:.2f}s")
                    
                    if sample_points and sample_points[0]:
                        for i, point in enumerate(sample_points[0]):
                            print(f"Point #{i+1} (ID: {point.id}):")
                            if hasattr(point, 'payload') and point.payload:
                                payload_keys = list(point.payload.keys())
                                print(f"  - Payload keys: {payload_keys}")
                                
                                # Afficher des informations clés du payload
                                for key in ['title', 'content', 'client', 'url', 'date', 'updated', 'created']:
                                    if key in point.payload:
                                        value = point.payload[key]
                                        if isinstance(value, str) and len(value) > 100:
                                            value = value[:100] + "..."
                                        print(f"  - {key}: {value}")
                            else:
                                print("  - Pas de payload ou payload vide")
                    else:
                        print("  Aucun point trouvé dans la collection.")
                except Exception as e:
                    print(f"Erreur lors de la récupération des points: {str(e)}")
                
                # 3. Effectuer une recherche de base pour tester
                try:
                    print("\nTest de recherche basique (sans filtre):")
                    # Créer un vecteur aléatoire de la bonne dimension
                    random_vector = [0.1] * (vector_size if vector_size else 1536)
                    start_time = time.time()
                    search_results = qdrant_client.search(
                        collection_name=collection_name,
                        query_vector=random_vector,
                        limit=3,
                        with_payload=True,
                        score_threshold=0.0  # Aucun seuil pour maximiser les résultats
                    )
                    end_time = time.time()
                    print(f"Temps de recherche: {end_time - start_time:.2f}s")
                    
                    print(f"Nombre de résultats: {len(search_results)}")
                    if search_results:
                        for i, result in enumerate(search_results):
                            print(f"Résultat #{i+1}:")
                            print(f"  - Score: {result.score}")
                            if hasattr(result, 'payload') and result.payload:
                                print(f"  - Payload keys: {list(result.payload.keys())}")
                                if 'title' in result.payload:
                                    print(f"  - Titre: {result.payload['title']}")
                            else:
                                print("  - Pas de payload")
                    else:
                        print("  Aucun résultat trouvé même sans filtre!")
                except Exception as e:
                    print(f"Erreur lors de la recherche: {str(e)}")
                    
        except Exception as e:
            print(f"Erreur lors de la récupération des collections: {str(e)}")
                    
    except Exception as e:
        print(f"Erreur globale: {str(e)}")

if __name__ == "__main__":
    inspect_collections()
