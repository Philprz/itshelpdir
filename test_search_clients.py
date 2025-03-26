
import asyncio
import logging
from dotenv import load_dotenv

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)
print("\nVariables d'environnement chargées.\n")
print("="*80 + "\n")

# Configuration du logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('ITS_HELP')

# Import des modules après chargement des variables d'environnement
from search_factory import search_factory  # noqa: E402
from gestion_clients import initialiser_base_clients  # noqa: E402

def print_section(title):
    """Affiche un titre de section formaté"""
    print("\n" + "="*50)
    print(title.upper())
    print("="*50 + "\n")

def print_subsection(title):
    """Affiche un titre de sous-section formaté"""
    print(f"\n--- {title} ---")

async def test_search_clients_initialization():
    """
    Teste l'initialisation des clients de recherche pour diagnostiquer
    les problèmes liés à l'absence de résultats.
    """
    print_section("DIAGNOSTIC DES CLIENTS DE RECHERCHE")
    
    try:
        # Étape 1: Initialisation de la base des clients
        print_subsection("Initialisation de la base des clients")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée.")
        
        # Étape 2: Initialisation manuelle du search_factory
        print_subsection("Initialisation du search_factory")
        await search_factory.initialize()
        print("✅ search_factory initialisé.")
        
        # Étape 3: Test de récupération des clients pour chaque type
        collection_types = ["jira", "zendesk", "netsuite", "netsuite_dummies", "sap", "confluence"]
        
        print_subsection("Test de récupération des clients de recherche")
        for collection_type in collection_types:
            print(f"Client {collection_type}...")
            client = await search_factory.get_client(collection_type)
            
            if client:
                # Vérifier si le client a l'interface attendue
                has_search_method = hasattr(client, 'recherche_intelligente')
                client_type = type(client).__name__
                
                if has_search_method:
                    # Vérifier si le client implémente toutes les méthodes requises
                    validation_method = hasattr(client, 'valider_resultat')
                    source_name_method = hasattr(client, 'get_source_name')
                    format_method = hasattr(client, 'format_for_message')
                    
                    if validation_method and source_name_method and format_method:
                        print(f"  ✅ Client {collection_type} implémente l'interface standardisée complète")
                        # Afficher des informations supplémentaires
                        source_name = client.get_source_name()
                        print(f"    📊 Source: {source_name}")
                        print(f"    📊 Type: {client_type}")
                    else:
                        print(f"  ⚠️ Client {collection_type} implémente partiellement l'interface standardisée")
                        missing = []
                        if not validation_method:
                            missing.append("valider_resultat")
                        if not source_name_method:
                            missing.append("get_source_name")
                        if not format_method:
                            missing.append("format_for_message")
                        print(f"    ⛔ Méthodes manquantes: {', '.join(missing)}")
                else:
                    print(f"  ❌ Client {collection_type} incompatible: pas de méthode recherche_intelligente")
            else:
                print(f"  ❌ Impossible de récupérer le client {collection_type}")
        
        # Étape 4: Test d'initialisation des services requis
        print_subsection("Test des services requis")
        
        # Vérifier l'embedding service
        embedding_service = getattr(search_factory, 'embedding_service', None)
        if embedding_service:
            print(f"✅ Service d'embedding disponible: {type(embedding_service).__name__}")
        else:
            print("❌ Service d'embedding non disponible")
            
        # Vérifier le client Qdrant
        qdrant_client = getattr(search_factory, 'qdrant_client', None)
        if qdrant_client:
            print(f"✅ Client Qdrant disponible: {type(qdrant_client).__name__}")
            
            # Vérifier les collections
            try:
                collections = await qdrant_client.get_collections()
                if collections:
                    print(f"  📊 Collections disponibles: {len(collections)}")
                    for collection in collections:
                        collection_name = collection.name if hasattr(collection, 'name') else str(collection)
                        print(f"    - {collection_name}")
                else:
                    print("  ⚠️ Aucune collection trouvée")
            except Exception as e:
                print(f"  ❌ Erreur lors de la récupération des collections: {str(e)}")
        else:
            print("❌ Client Qdrant non disponible")
        
        # Étape 5: Test minimal de recherche sur un client
        print_subsection("Test minimal de recherche")
        
        test_questions = [
            "Comment consulter un ticket?",
            "Quelles sont les étapes pour créer une facture?",
            "Comment résoudre un problème de connexion?"
        ]
        
        for collection_type in collection_types:
            client = await search_factory.get_client(collection_type)
            if client and hasattr(client, 'recherche_intelligente'):
                try:
                    print(f"Test de recherche sur {collection_type}...")
                    # Test de recherche avec plusieurs questions
                    results_by_question = {}
                    for question in test_questions:
                        results = await client.recherche_intelligente(
                            question=question,
                            client_name=None,
                            limit=3, 
                            score_threshold=0.3
                        )
                        results_by_question[question] = results
                    
                    if results_by_question:
                        total_results = sum(len(r) for r in results_by_question.values())
                        print(f"  ✅ Recherche réussie: {total_results} résultats obtenus au total")
                        
                        # Afficher un résumé des résultats par question
                        for question, results in results_by_question.items():
                            print(f"    • '{question[:30]}...' : {len(results)} résultats")
                    else:
                        print("  ⚠️ Recherche effectuée mais aucun résultat trouvé")
                    
                    # Test de formatage pour un message
                    print("  Test de formatage des résultats...")
                    for question, results in results_by_question.items():
                        if results:
                            formatted = await client.format_for_message(results[:2])
                            if formatted:
                                print(f"  ✅ Formatage réussi: {len(formatted)} caractères")
                            else:
                                print("  ⚠️ Formatage vide")
                            break
                    
                    # On s'arrête au premier client fonctionnel
                    break
                except Exception as e:
                    print(f"  ❌ Erreur lors de la recherche: {str(e)}")
        
        # Diagnostic terminé
        print_section("DIAGNOSTIC TERMINÉ")
        
    except Exception as e:
        logger.error(f"Erreur lors du diagnostic: {str(e)}", exc_info=True)
        print(f"\n❌ ERREUR CRITIQUE: {str(e)}")

if __name__ == "__main__":
    try:
        # Exécution du diagnostic
        asyncio.run(test_search_clients_initialization())
    except KeyboardInterrupt:
        print("\nDiagnostic interrompu par l'utilisateur.")
    except Exception as e:
        print(f"\nErreur lors de l'exécution du diagnostic: {str(e)}")
