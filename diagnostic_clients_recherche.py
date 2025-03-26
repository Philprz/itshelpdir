"""
Diagnostic des clients de recherche

Ce script effectue une analyse détaillée de l'état d'initialisation des clients de recherche
pour identifier pourquoi la recherche coordonnée ne fonctionne pas correctement.
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
import inspect
from typing import Dict, List, Any, Optional

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("diagnostic_clients.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.diagnostic")

print("\nVariables d'environnement chargées.\n")

# Import après chargement des variables d'environnement
from gestion_clients import initialiser_base_clients  # noqa: E402
from search_factory import search_factory, SearchClientFactory  # noqa: E402

class ClientDiagnostic:
    """
    Classe pour le diagnostic des clients de recherche
    """
    
    def __init__(self):
        """Initialisation du diagnostic"""
        self.search_factory = search_factory
        self.collections = [
            "jira", "zendesk", "confluence", 
            "netsuite", "netsuite_dummies", "sap"
        ]
        self.status = {}
        self.all_clients = []
    
    async def initialiser(self):
        """Initialise les prérequis pour le diagnostic"""
        print("Initialisation de la base des clients...")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée")
        
        # Récupérer les informations sur SearchClientFactory
        self.factory_class_info()
        
        # Initialiser le statut de chaque collection
        for collection in self.collections:
            self.status[collection] = {
                "initialized": False,
                "error": None,
                "client": None
            }
    
    def factory_class_info(self):
        """Affiche des informations sur la classe SearchClientFactory"""
        try:
            print("\n📋 Informations sur SearchClientFactory:")
            
            # Vérifier le type de search_factory
            print(f"Type de search_factory: {type(search_factory)}")
            
            # Obtenir les méthodes de la classe
            methods = [method for method in dir(SearchClientFactory) 
                      if callable(getattr(SearchClientFactory, method)) and not method.startswith('_')]
            
            print(f"Méthodes disponibles: {methods}")
            
            # Vérifier si search_factory a des attributs spécifiques
            if hasattr(search_factory, "_clients_cache"):
                print(f"Cache de clients: {len(search_factory._clients_cache)} clients en cache")
            else:
                print("⚠️ Pas de cache de clients détecté")
            
            # Vérification de get_client
            if hasattr(search_factory, "get_client"):
                method = getattr(search_factory, "get_client")
                sig = inspect.signature(method)
                print(f"Signature de get_client: {sig}")
            
        except Exception as e:
            print(f"❌ Erreur lors de l'analyse de SearchClientFactory: {str(e)}")
    
    async def tester_client(self, client_type: str, collection_name: str = None):
        """Teste l'initialisation d'un client spécifique"""
        try:
            print(f"\n🔍 Test du client {client_type}" + (f" ({collection_name})" if collection_name else ""))
            
            # Tenter d'obtenir le client
            client = await self.search_factory.get_client(
                client_type=client_type, 
                collection_name=collection_name,
                fallback_enabled=True
            )
            
            if client:
                # Client obtenu avec succès
                client_info = {
                    "type": client_type,
                    "collection": collection_name,
                    "class": type(client).__name__,
                    "methods": [method for method in dir(client) if callable(getattr(client, method)) and not method.startswith('_')]
                }
                
                print(f"✅ Client {client_type} initialisé avec succès")
                print(f"  - Classe: {client_info['class']}")
                print(f"  - Méthodes: {', '.join(client_info['methods'])}")
                
                # Vérifier si le client a une méthode de recherche
                has_search = any(method in client_info['methods'] for method in 
                                ['recherche_intelligente', 'search', 'query', 'find'])
                
                if has_search:
                    print(f"  - ✅ Le client possède une méthode de recherche")
                else:
                    print(f"  - ⚠️ Le client ne semble pas avoir de méthode de recherche standard")
                
                self.all_clients.append(client_info)
                
                if collection_name in self.status:
                    self.status[collection_name]["initialized"] = True
                    self.status[collection_name]["client"] = client_info
                
                return client
            else:
                # Échec d'initialisation
                print(f"❌ Échec d'initialisation du client {client_type}")
                
                if collection_name in self.status:
                    self.status[collection_name]["error"] = "Client non initialisé"
                
                return None
                
        except Exception as e:
            # Erreur lors de l'initialisation
            print(f"❌ Erreur lors de l'initialisation du client {client_type}: {str(e)}")
            logger.error(f"Erreur lors de l'initialisation du client {client_type}", exc_info=True)
            
            if collection_name in self.status:
                self.status[collection_name]["error"] = str(e)
            
            return None
    
    async def diagnostiquer_tous_clients(self):
        """Diagnostique tous les clients de recherche"""
        print("\n🔍 Diagnostic de tous les clients de recherche...")
        
        for collection in self.collections:
            await self.tester_client(client_type=collection, collection_name=collection)
        
        print("\n📋 Résumé du diagnostic:")
        success_count = 0
        
        for collection, status in self.status.items():
            if status["initialized"]:
                print(f"✅ {collection}: Client initialisé avec succès")
                success_count += 1
            else:
                error_msg = status["error"] if status["error"] else "Raison inconnue"
                print(f"❌ {collection}: Échec d'initialisation - {error_msg}")
        
        success_rate = (success_count / len(self.collections)) * 100
        print(f"\nTaux de réussite: {success_count}/{len(self.collections)} ({success_rate:.1f}%)")
        
        return success_count == len(self.collections)
    
    async def tester_recherche_simple(self, collection: str, query: str = "test"):
        """Teste une recherche simple avec un client spécifique"""
        if collection not in self.status or not self.status[collection]["initialized"]:
            print(f"❌ Impossible de tester la recherche pour {collection}: client non initialisé")
            return None
        
        try:
            print(f"\n🔍 Test de recherche pour {collection} avec la requête '{query}'...")
            
            client = await self.search_factory.get_client(
                client_type=collection,
                collection_name=collection
            )
            
            if not client:
                print(f"❌ Impossible d'obtenir le client {collection} pour la recherche")
                return None
            
            # Vérifier si le client a une méthode de recherche_intelligente
            if hasattr(client, "recherche_intelligente") and callable(getattr(client, "recherche_intelligente")):
                print(f"Appel à recherche_intelligente...")
                results = await client.recherche_intelligente(
                    query=query,
                    limit=2
                )
                
                if results:
                    print(f"✅ {len(results)} résultats trouvés")
                    return results
                else:
                    print(f"⚠️ Aucun résultat trouvé")
                    return []
            else:
                print(f"❌ Le client {collection} n'a pas de méthode recherche_intelligente")
                return None
                
        except Exception as e:
            print(f"❌ Erreur lors de la recherche pour {collection}: {str(e)}")
            logger.error(f"Erreur lors de la recherche pour {collection}", exc_info=True)
            return None
    
    def generer_rapport(self):
        """Génère un rapport de diagnostic avec les problèmes détectés et les solutions proposées"""
        problemes = []
        solutions = []
        
        # Analyser les problèmes
        if not any(self.status[collection]["initialized"] for collection in self.collections):
            problemes.append("Aucun client de recherche n'a pu être initialisé")
            solutions.append("Vérifiez les variables d'environnement (OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY)")
        
        # Problèmes spécifiques par collection
        for collection, status in self.status.items():
            if not status["initialized"]:
                problemes.append(f"Le client {collection} n'a pas pu être initialisé: {status['error']}")
                
                if "openai" in str(status["error"]).lower():
                    solutions.append(f"Vérifiez la clé API OpenAI pour le client {collection}")
                elif "qdrant" in str(status["error"]).lower():
                    solutions.append(f"Vérifiez la configuration Qdrant pour le client {collection}")
                else:
                    solutions.append(f"Vérifiez l'initialisation du client {collection} dans search_factory.py")
        
        # Écrire le rapport
        report = """
# Rapport de diagnostic des clients de recherche

## Problèmes détectés
"""
        
        for i, probleme in enumerate(problemes, 1):
            report += f"{i}. {probleme}\n"
        
        report += """
## Solutions proposées
"""
        
        for i, solution in enumerate(solutions, 1):
            report += f"{i}. {solution}\n"
        
        report += """
## Correctifs recommandés

1. Vérifiez que les variables d'environnement sont correctement chargées avant d'initialiser les clients
2. Assurez-vous que la fonction get_client dans search_factory.py gère correctement les erreurs
3. Utilisez un mécanisme de fallback pour les clients de recherche défaillants
4. Ajoutez plus de logs pour suivre l'initialisation des clients
5. Vérifiez que les collections Qdrant existent et sont accessibles
"""
        
        # Écrire dans un fichier
        with open("rapport_diagnostic.md", "w", encoding="utf-8") as f:
            f.write(report)
        
        print("\n✅ Rapport de diagnostic généré dans rapport_diagnostic.md")

async def main():
    """Fonction principale"""
    try:
        # Initialiser le diagnostic
        diagnostic = ClientDiagnostic()
        await diagnostic.initialiser()
        
        # Diagnostiquer tous les clients
        tous_ok = await diagnostic.diagnostiquer_tous_clients()
        
        # Si au moins un client est initialisé, tester la recherche
        if any(diagnostic.status[collection]["initialized"] for collection in diagnostic.collections):
            for collection in diagnostic.collections:
                if diagnostic.status[collection]["initialized"]:
                    await diagnostic.tester_recherche_simple(collection, "test")
                    break
        
        # Générer un rapport
        diagnostic.generer_rapport()
        
        # Afficher les recommandations
        print("\n📋 CONCLUSION:")
        if tous_ok:
            print("✅ Tous les clients de recherche sont correctement initialisés")
            print("➡️ Vérifiez maintenant l'implémentation de process_web_message et recherche_coordonnee")
        else:
            print("⚠️ Certains clients de recherche n'ont pas pu être initialisés")
            print("➡️ Corrigez d'abord les problèmes d'initialisation avant de modifier process_web_message")
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)
        print(f"❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
