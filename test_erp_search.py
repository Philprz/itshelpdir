#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_erp_search.py
Script pour tester directement les clients de recherche ERP (NetSuite, SAP) sans passer par le chatbot.
"""

import os
import asyncio
import time
import sys
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Fonction pour afficher les séparateurs et améliorer la lisibilité
def print_section_header(title, char='=', width=80):
    """Affiche un titre de section avec des séparateurs pour améliorer la lisibilité."""
    print("\n" + char * width)
    print(f" {title} ".center(width, char))
    print(char * width + "\n")

def print_subsection(title, char='-', width=60):
    """Affiche un titre de sous-section avec des séparateurs."""
    print(f"\n{char * width}")
    print(f" {title} ".center(width))
    print(f"{char * width}\n")

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

async def test_search_clients_initialization():
    """
    Teste l'initialisation de tous les clients de recherche disponibles.
    Vérifie que chaque client peut être correctement initialisé avec les paramètres requis.
    """
    print_section_header("TEST D'INITIALISATION DES CLIENTS DE RECHERCHE")
    
    try:
        # Import des clients de recherche
        from search.clients import (
            NetsuiteSearchClient, 
            SapSearchClient, 
            NetsuiteDummiesSearchClient,
            JiraSearchClient,
            ZendeskSearchClient,
            ConfluenceSearchClient,
            ERPSearchClient
        )
        
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
        
        # Liste des clients à initialiser avec leur collection respective
        client_configs = [
            ("NETSUITE", NetsuiteSearchClient, "NETSUITE"),
            ("NETSUITE_DUMMIES", NetsuiteDummiesSearchClient, "NETSUITE_DUMMIES"),
            ("SAP", SapSearchClient, "SAP"),
            ("JIRA", JiraSearchClient, "JIRA"),
            ("ZENDESK", ZendeskSearchClient, "ZENDESK"),
            ("CONFLUENCE", ConfluenceSearchClient, "CONFLUENCE"),
            ("ERP", ERPSearchClient, "ERP")
        ]
        
        # Vérifier si les collections existent
        print_subsection("Vérification des collections disponibles", "-")
        try:
            collections_info = qdrant_client.get_collections()
            available_collections = [col.name for col in collections_info.collections]
            print(f"Collections disponibles: {available_collections}")
        except Exception as e:
            print(f"Erreur lors de la vérification des collections: {str(e)}")
            available_collections = []
            
        # Test d'initialisation de chaque client
        successful_inits = 0
        failed_inits = 0
        
        for client_name, client_class, collection_name in client_configs:
            print_subsection(f"Initialisation du client: {client_name}", "-")
            
            # Vérifier si la collection existe
            collection_exists = collection_name in available_collections
            print(f"Collection '{collection_name}' disponible: {'Oui' if collection_exists else 'Non'}")
            
            try:
                start_time = time.monotonic()
                
                # Initialisation du client
                client = client_class(collection_name, qdrant_client, embedding_service)
                
                duration = time.monotonic() - start_time
                print(f"Client initialisé en {duration:.4f}s")
                
                # Vérification des attributs clés
                source_name = client.get_source_name()
                print(f"Source name: {source_name}")
                
                # Test de base: vérifier que le client est correctement initialisé
                is_initialized = hasattr(client, 'collection_name') and client.collection_name == collection_name
                print(f"Client correctement initialisé: {'Oui' if is_initialized else 'Non'}")
                
                if is_initialized:
                    successful_inits += 1
                else:
                    failed_inits += 1
                
            except Exception as e:
                print(f"Erreur lors de l'initialisation: {str(e)}")
                failed_inits += 1
                
        # Résumé des tests
        print_section_header(f"RÉSUMÉ: {successful_inits} clients initialisés avec succès, {failed_inits} échecs", "=")
                    
    except Exception as e:
        print(f"Erreur globale: {str(e)}")

async def test_client_search():
    """Teste directement la recherche via les clients ERP."""
    print_section_header("TEST DIRECT DES CLIENTS ERP")
    
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
        
        # Vérifier si les collections existent
        print_subsection("Vérification des collections disponibles", "-")
        try:
            collections_info = qdrant_client.get_collections()
            available_collections = [col.name for col in collections_info.collections]
            print(f"Collections disponibles: {available_collections}")
        except Exception as e:
            print(f"Erreur lors de la vérification des collections: {str(e)}")
        
        # Test des clients
        clients = [
            ("NETSUITE", NetsuiteSearchClient("NETSUITE", qdrant_client, embedding_service)),
            ("NETSUITE_DUMMIES", NetsuiteDummiesSearchClient("NETSUITE_DUMMIES", qdrant_client, embedding_service)),
            ("SAP", SapSearchClient("SAP", qdrant_client, embedding_service))
        ]
        
        for client_name, client in clients:
            print_section_header(f"Test du client: {client_name}", "=")
            
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
                
                print("\n" + "-" * 50)
                    
    except Exception as e:
        print(f"Erreur globale: {str(e)}")

if __name__ == "__main__":
    # Exécuter un test à la fois pour éviter les problèmes d'affichage
    if len(sys.argv) > 1 and sys.argv[1] == "--init-only":
        # Exécuter uniquement les tests d'initialisation
        asyncio.run(test_search_clients_initialization())
    elif len(sys.argv) > 1 and sys.argv[1] == "--search-only":
        # Exécuter uniquement les tests de recherche
        asyncio.run(test_client_search())
    else:
        # Exécuter les deux tests séquentiellement avec des séparateurs clairs
        print("\n" + "#" * 100)
        print(" DÉBUT DES TESTS ".center(100, "#"))
        print("#" * 100 + "\n")
        
        asyncio.run(test_search_clients_initialization())
        
        print("\n" + "#" * 100)
        print(" SÉPARATION ENTRE LES TESTS ".center(100, "#"))
        print("#" * 100 + "\n")
        
        asyncio.run(test_client_search())
        
        print("\n" + "#" * 100)
        print(" FIN DES TESTS ".center(100, "#"))
        print("#" * 100 + "\n")
