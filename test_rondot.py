
# Script de test pour valider la détection des tickets RONDOT
import os
import asyncio
import logging
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("test_rondot")

# Import après chargement des variables d'environnement
from chatbot import ChatBot
from gestion_clients import extract_client_name

async def test_extract_client():
    print("\n---- Test de extract_client_name ----")
    queries = [
        "Quels sont les derniers tickets RONDOT?",
        "J'ai besoin d'info sur les tickets RONDOT",
        "RONDOT a des problèmes",
        "Cherche les tickets du client RONDOT",
        "Recherche tickets rondot" # en minuscule
    ]
    
    for query in queries:
        client_name, score, metadata = await extract_client_name(query)
        print(f"Query: '{query}'")
        print(f"  → Client: {client_name}, Score: {score}, Metadata: {metadata}\n")

async def test_chatbot():
    print("\n---- Test du chatbot ----")
    # Initialisation du chatbot
    chatbot = ChatBot(
        openai_key=os.getenv('OPENAI_API_KEY'),
        qdrant_url=os.getenv('QDRANT_URL'),
        qdrant_api_key=os.getenv('QDRANT_API_KEY')
    )
    
    # Test de determine_collections (analyse seule)
    print("\n1. Test de determine_collections:")
    test_analysis = {
        "type": "support",
        "query": {
            "original": "Tickets récents pour RONDOT"
        }
    }
    collections = chatbot.determine_collections(test_analysis)
    print(f"Collections sélectionnées: {collections}")
    
    # Test avec une requête RONDOT
    query = "Je cherche les derniers tickets de RONDOT"
    print(f"\n2. Test avec la requête: '{query}'")
    
    try:
        response = await chatbot.process_web_message(
            text=query,
            conversation={"id": "test", "user_id": "test"},
            user_id="test_user",
            mode="guide"
        )
        
        print(f"Réponse reçue:")
        print(f"  → Text: {response.get('text', '')[:150]}...")
        print(f"  → Metadata: {response.get('metadata', {})}")
        
    except Exception as e:
        print(f"Erreur lors du test du chatbot: {str(e)}")

async def main():
    try:
        # Test de la fonction extract_client_name
        await test_extract_client()
        
        # Test du chatbot
        await test_chatbot()
        
    except Exception as e:
        print(f"Erreur globale: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
