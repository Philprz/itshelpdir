#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
check_vector_fields.py
Script pour vérifier les noms des champs de vecteurs dans les collections Qdrant.
"""

import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Chargement des variables d'environnement
load_dotenv(verbose=True)

def check_vector_fields():
    """Vérifie les noms des champs de vecteurs dans les collections Qdrant."""
    print("\n" + "=" * 80)
    print("VÉRIFICATION DES CHAMPS DE VECTEURS DANS QDRANT")
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
        collections_info = qdrant_client.get_collections()
        available_collections = [col.name for col in collections_info.collections]
        print(f"Collections disponibles: {available_collections}")
        
        # Inspecter chaque collection pour trouver les noms des champs de vecteurs
        for collection_name in available_collections:
            print(f"\n{'=' * 40}")
            print(f"Collection: {collection_name}")
            
            try:
                # Récupérer les informations de la collection via l'API HTTP
                response = qdrant_client.http.collections_api.get_collection(
                    collection_name=collection_name
                )
                
                # Convertir en dictionnaire pour un accès plus facile
                response_dict = response.dict() if hasattr(response, 'dict') else response
                
                # Extraire les informations sur les vecteurs
                print("Configuration des vecteurs:")
                if isinstance(response_dict, dict) and 'result' in response_dict:
                    config = response_dict['result'].get('config', {})
                    params = config.get('params', {})
                    vectors = params.get('vectors', {})
                    
                    if vectors:
                        print(f"  Champs de vecteurs trouvés: {list(vectors.keys())}")
                        for vector_name, vector_config in vectors.items():
                            print(f"  - {vector_name}: {vector_config}")
                    else:
                        print("  Aucun champ de vecteur trouvé dans la configuration")
                else:
                    print(f"  Format de réponse inattendu: {type(response_dict)}")
                    
            except Exception as e:
                print(f"Erreur lors de l'inspection de la collection {collection_name}: {str(e)}")
        
    except Exception as e:
        print(f"Erreur globale: {str(e)}")

if __name__ == "__main__":
    check_vector_fields()
