#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
list_qdrant_collections.py
Script pour lister les collections disponibles dans l'instance Qdrant.
"""

import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Chargement des variables d'environnement
load_dotenv(verbose=True)
print("Variables d'environnement chargées :")
print(f"QDRANT_URL: {'Définie' if os.getenv('QDRANT_URL') else 'Non définie'}")
print(f"QDRANT_API_KEY: {'Définie' if os.getenv('QDRANT_API_KEY') else 'Non définie'}")

def list_collections():
    """Liste toutes les collections disponibles dans l'instance Qdrant."""
    try:
        # Initialisation du client Qdrant
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not qdrant_url:
            print("Erreur: URL Qdrant manquante!")
            print("Veuillez définir la variable d'environnement QDRANT_URL dans le fichier .env")
            return
        
        client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key
        )
        
        # Récupération des collections
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        print("\n" + "=" * 80)
        print("COLLECTIONS QDRANT DISPONIBLES")
        print("=" * 80)
        
        if not collection_names:
            print("Aucune collection trouvée dans l'instance Qdrant.")
        else:
            print(f"{len(collection_names)} collections trouvées :")
            for i, name in enumerate(sorted(collection_names), 1):
                print(f"{i}. {name}")
                
            # Détail des collections
            print("\nDétails des collections :")
            for name in sorted(collection_names):
                try:
                    collection_info = client.get_collection(name)
                    print(f"Collection: {name}")
                    print(f"  - Vecteurs: {collection_info.vectors_count}")
                    print(f"  - Dimension: {collection_info.config.params.vectors.size}")
                    print("-" * 40)
                except Exception as e:
                    print(f"Erreur lors de la récupération des détails pour {name}: {str(e)}")
    
    except Exception as e:
        print(f"Erreur: {str(e)}")

if __name__ == "__main__":
    list_collections()
