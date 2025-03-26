import os
import asyncio
import logging
import json
from dotenv import load_dotenv
import sys
from datetime import datetime

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)

# Configuration du logging - IMPORTANT : redirection vers un fichier
log_file = "chatbot_test.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w'),  # Écraser le fichier à chaque exécution
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('ITS_HELP')

# Supprime les handlers du root logger pour éviter la duplication
root_logger = logging.getLogger()
if root_logger.handlers:
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)

print("\nVariables d'environnement chargées et logging configuré.\n")
print("="*80 + "\n")

# Import après chargement des variables d'environnement
from chatbot import ChatBot  # noqa: E402
from gestion_clients import initialiser_base_clients  # noqa: E402

async def test_query(chatbot, question, user_id, conversation, mode="guide"):
    """
    Exécute une requête sur le chatbot et capture la réponse
    """
    print(f"\n{'='*60}")
    print(f"QUESTION: {question}")
    print(f"{'='*60}")
    
    start_time = datetime.now()
    
    try:
        response = await chatbot.process_web_message(
            text=question,
            conversation=conversation,
            user_id=user_id,
            mode=mode
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"✅ Réponse reçue en {duration:.2f} secondes")
        
        # Extraction des métadonnées importantes
        if isinstance(response, dict):
            # Extraire le client détecté
            metadata = response.get("metadata", {})
            client = metadata.get("client", "Non spécifié")
            print(f"Client détecté: {client}")
            
            # Extraire le texte de la réponse
            text = response.get("text", "Pas de texte disponible")
            print(f"\nRéponse: {text[:150]}..." if len(text) > 150 else f"\nRéponse: {text}")
            
            # Extraire les blocs Slack
            blocks = response.get("blocks", [])
            if blocks:
                print(f"\nNombre de blocs dans la réponse: {len(blocks)}")
        else:
            print("⚠️ Format de réponse inattendu")
        
        return response
    
    except Exception as e:
        print(f"❌ Erreur lors du traitement de la question: {str(e)}")
        return None

async def test_chatbot_structured():
    """
    Test structuré du chatbot avec capture propre des résultats
    """
    try:
        # Initialisation de la base des clients
        print("Initialisation de la base des clients...")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée\n")
        
        # Récupération des clés API depuis les variables d'environnement
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not openai_key or not qdrant_url:
            print("❌ Clés API manquantes: OPENAI_API_KEY ou QDRANT_URL non définies")
            return None
        
        print(f"Initialisation du ChatBot avec QDRANT_URL: {qdrant_url}")
        
        # Initialisation du ChatBot
        chatbot = ChatBot(
            openai_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key
        )
        print("✅ ChatBot initialisé\n")
        
        # Test avec plusieurs questions ciblées
        user_id = "test_user"
        conversation = {"id": "test_conversation", "user_id": user_id}
        
        # Questions à tester
        questions = [
            # Test RONDOT (client spécifique)
            "Quels sont les derniers tickets de RONDOT?",
            
            # Test ERP (requête sur NETSUITE)
            "Comment paramétrer un compte fournisseur dans NetSuite?",
            
            # Test avec date
            "Tickets ouverts chez RONDOT entre le 01/01/2025 et le 01/03/2025",
            
            # Test sans client spécifique (devrait chercher dans toutes les sources)
            "Comment résoudre un problème de connexion VPN?"
        ]
        
        # Exécuter chaque question et collecter les résultats
        results = []
        for question in questions:
            response = await test_query(chatbot, question, user_id, conversation)
            results.append({
                "question": question,
                "response": response,
                "success": response is not None
            })
            
            # Pause entre les requêtes pour éviter de surcharger le système
            await asyncio.sleep(1)
        
        # Rapport de test
        print("\n" + "="*60)
        print("RAPPORT DE TEST")
        print("="*60)
        
        success_count = sum(1 for r in results if r["success"])
        print(f"Tests réussis: {success_count}/{len(results)}\n")
        
        for i, result in enumerate(results, 1):
            status = "✅ RÉUSSI" if result["success"] else "❌ ÉCHEC"
            print(f"Test {i}: {status} - {result['question']}")
        
        print("\nLes logs détaillés ont été écrits dans le fichier:", log_file)
        
        return results
        
    except Exception as e:
        print(f"❌ Erreur critique lors du test du ChatBot: {str(e)}")
        return None

if __name__ == "__main__":
    try:
        # Exécution du test structuré
        print("Lancement du test structuré du ChatBot...\n")
        results = asyncio.run(test_chatbot_structured())
        
        if results:
            print("\nTest terminé avec succès.")
        else:
            print("\nLe test a échoué.")
            
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur.")
    except Exception as e:
        print(f"\nErreur lors de l'exécution du test: {str(e)}")
