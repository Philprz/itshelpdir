# test_rondot_avec_mock.py
# Script de test avancé avec simulation des clients de recherche

import os
import asyncio
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("test_rondot_mock")

# Préparation des imports avec simulation
# On crée des mocks avant d'importer les modules réels
search_factory_mock = MagicMock()
qdrant_client_mock = MagicMock()

# Données simulées pour les tests
MOCK_JIRA_RESULTS = [
    {
        "id": "JIRA-1234",
        "score": 0.92,
        "payload": {
            "source_type": "jira",
            "key": "RONDOT-123",
            "summary": "Problème de configuration ERP",
            "description": "Le client RONDOT signale des problèmes avec la configuration de l'ERP",
            "created": "2025-02-10",
            "updated": "2025-02-15",
            "status": "En cours"
        }
    }
]

MOCK_ZENDESK_RESULTS = [
    {
        "id": "ZD-5678",
        "score": 0.88,
        "payload": {
            "source_type": "zendesk",
            "ticket_id": "42",
            "subject": "Support technique RONDOT",
            "description": "Demande d'assistance pour déploiement de mise à jour",
            "created": "2025-03-01",
            "updated": "2025-03-05",
            "status": "Ouvert"
        }
    }
]

# Création d'une classe ResultMock pour simuler les résultats de recherche
class ResultMock:
    def __init__(self, result_dict):
        self.id = result_dict.get("id")
        self.score = result_dict.get("score")
        self.payload = result_dict.get("payload", {})
        self.collection_name = result_dict.get("collection_name", "unknown")
        
    def __repr__(self):
        return f"ResultMock(id={self.id}, score={self.score}, source={self.payload.get('source_type', 'unknown')})"

# Classe pour simuler un client de recherche
class SearchClientMock:
    def __init__(self, name, results):
        self.name = name
        self.mock_results = [ResultMock(r) for r in results]
        logger.info(f"Client simulé {name} initialisé avec {len(self.mock_results)} résultats")
    
    async def recherche_intelligente(self, question, client_info=None, date_debut=None, date_fin=None, 
                                    max_results=5, threshold=0.1):
        logger.info(f"Recherche simulée dans {self.name} pour: '{question}'")
        if client_info and client_info.get('source') == 'RONDOT':
            logger.info(f"Client RONDOT détecté dans la recherche {self.name}")
            return self.mock_results
        return []

# Fonction pour configurer le mock de search_factory
def configure_search_factory_mock():
    # Création des clients simulés
    jira_client = SearchClientMock("jira", MOCK_JIRA_RESULTS)
    zendesk_client = SearchClientMock("zendesk", MOCK_ZENDESK_RESULTS)
    
    # Configuration du mock de get_client pour retourner nos clients simulés
    async def mock_get_client(source_type):
        if source_type == "jira":
            return jira_client
        elif source_type == "zendesk":
            return zendesk_client
        else:
            # Pour les autres types, retourner un client vide
            return SearchClientMock(source_type, [])
    
    search_factory_mock.get_client = mock_get_client
    return search_factory_mock

# Application des patches pour la simulation
patches = []

def apply_patches():
    global patches
    # Configurer le mock pour search_factory
    sf_mock = configure_search_factory_mock()
    patches.append(patch("chatbot.search_factory", sf_mock))
    
    # Appliquer tous les patches
    for p in patches:
        p.start()
    logger.info("Patches appliqués avec succès")

def remove_patches():
    global patches
    for p in patches:
        p.stop()
    patches = []
    logger.info("Patches retirés")

# Maintenant on peut importer les modules réels
apply_patches()
try:
    # Import après le patching et le chargement des variables d'environnement
    from chatbot import ChatBot
    from gestion_clients import extract_client_name
except Exception as e:
    logger.error(f"Erreur lors de l'import des modules: {e}")
    remove_patches()
    raise

async def test_extract_client():
    print("\n---- Test de extract_client_name ----")
    queries = [
        "Quels sont les derniers tickets RONDOT?",
        "J'ai besoin d'info sur les tickets RONDOT",
        "RONDOT a des problèmes",
        "Cherche les tickets du client RONDOT",
        "Recherche tickets rondot",  # en minuscule
        "Ticket ERP RONDOT",  # combinaison avec ERP
        "RONDOT"  # juste le nom
    ]
    
    for query in queries:
        client_name, score, metadata = await extract_client_name(query)
        print(f"Query: '{query}'")
        print(f"  → Client: {client_name}, Score: {score}, Metadata: {metadata}\n")

class MockConversation:
    def __init__(self):
        self.id = "test_conv_id"
        self.user_id = "test_user"
        self.context = "{}"

async def test_determine_collections():
    print("\n---- Test de determine_collections ----")
    chatbot = ChatBot(
        openai_key=os.getenv('OPENAI_API_KEY', "mock_key"),
        qdrant_url=os.getenv('QDRANT_URL', "mock_url"),
        qdrant_api_key=os.getenv('QDRANT_API_KEY', "mock_api_key")
    )
    
    test_analyses = [
        {
            "type": "support",
            "query": {
                "original": "Tickets récents pour RONDOT"
            }
        },
        {
            "type": "configuration",
            "query": {
                "original": "Problème ERP avec RONDOT"
            }
        },
        {
            "type": "documentation",
            "query": {
                "original": "Documentation pour client RONDOT"
            }
        },
        {
            "type": "support",
            "query": {
                "original": "Tickets récents non RONDOT"
            }
        }
    ]
    
    for i, analysis in enumerate(test_analyses):
        collections = chatbot.determine_collections(analysis)
        print(f"Analyse {i+1}: '{analysis['query']['original']}'")
        print(f"  → Collections: {collections}\n")

async def test_process_web_message():
    print("\n---- Test de process_web_message ----")
    chatbot = ChatBot(
        openai_key=os.getenv('OPENAI_API_KEY', "mock_key"),
        qdrant_url=os.getenv('QDRANT_URL', "mock_url"),
        qdrant_api_key=os.getenv('QDRANT_API_KEY', "mock_api_key")
    )
    
    # Simuler la méthode analyze_question
    original_analyze = chatbot.analyze_question
    async def mock_analyze_question(text):
        return {
            "type": "support",
            "search_context": {
                "has_client": True
            },
            "query": {
                "original": text,
                "reformulated": text
            }
        }
    chatbot.analyze_question = mock_analyze_question
    
    test_messages = [
        "Je cherche les derniers tickets de RONDOT",
        "Problèmes récents pour le client RONDOT",
        "Ticket ERP RONDOT numéro 123",
        "Support technique RONDOT urgent"
    ]
    
    mock_conversation = MockConversation()
    
    try:
        for message in test_messages:
            print(f"\nTest avec message: '{message}'")
            response = await chatbot.process_web_message(
                text=message,
                conversation=mock_conversation,
                user_id="test_user",
                mode="detail"
            )
            
            # Extraction des informations clés de la réponse pour vérification
            if isinstance(response, dict):
                print(f"Type de réponse: dict")
                if "text" in response:
                    # Limiter la taille du texte pour l'affichage
                    preview = response["text"][:150] + "..." if len(response["text"]) > 150 else response["text"]
                    print(f"Texte de réponse: {preview}")
                
                if "blocks" in response:
                    print(f"Nombre de blocs: {len(response['blocks'])}")
            else:
                print(f"Type de réponse inattendu: {type(response)}")
    
    finally:
        # Restaurer la méthode originale
        chatbot.analyze_question = original_analyze

async def main():
    try:
        print("🧪 Test du correctif RONDOT avec simulation des clients")
        print("====================================================\n")
        
        # Test de la fonction extract_client_name
        await test_extract_client()
        
        # Test de determine_collections
        await test_determine_collections()
        
        # Test de process_web_message
        await test_process_web_message()
        
        print("\n✅ Tests terminés avec succès!")
        
    except Exception as e:
        print(f"\n❌ Erreur pendant les tests: {str(e)}")
    
    finally:
        # Nettoyer les patches
        remove_patches()

if __name__ == "__main__":
    asyncio.run(main())
