import os
import asyncio
import logging
from dotenv import load_dotenv
import json

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)
print("\nVariables d'environnement chargées.\n")
print("="*80 + "\n")

# Configuration du logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('ITS_HELP')

# Import après chargement des variables d'environnement
from chatbot import ChatBot  # noqa: E402

async def test_chatbot_date_simulation():
    """
    Fonction de simulation complète pour le chatbot avec des requêtes impliquant des dates
    """
    try:
        # Récupération des clés API depuis les variables d'environnement
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not openai_key or not qdrant_url:
            logger.error("Clés API manquantes: OPENAI_API_KEY ou QDRANT_URL non définies")
            return None
        
        logger.info(f"Initialisation du ChatBot avec QDRANT_URL: {qdrant_url}")
        
        # Initialisation du ChatBot
        chatbot = ChatBot(
            openai_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key
        )
        
        # Test avec une question impliquant des dates
        user_id = "test_user"
        
        # Nous utilisons plusieurs questions pour tester différents clients
        questions = [
            # Test NetSuite avec mentions de dates
            "Comment puis-je consulter une facture du 15 janvier 2023 dans NetSuite ?",
            
            # Test SAP avec mentions de dates
            "Comment extraire un rapport SAP pour les ventes entre le 01/03/2023 et le 25/03/2023 ?",
            
            # Test Zendesk avec mention d'une date
            "Je cherche un ticket Zendesk créé le 2023-02-15 concernant un problème de connexion."
        ]
        
        # Création d'un objet conversation simulé
        conversation = {"id": "test_conversation", "user_id": user_id}
        
        # Traitement de chaque question
        results = []
        for i, question in enumerate(questions, 1):
            print(f"\n{'='*40}\nQUESTION {i}: {question}\n{'='*40}\n")
            logger.info(f"Envoi du message de test: {question}")
            
            response = await chatbot.process_web_message(
                text=question,
                conversation=conversation,
                user_id=user_id,
                mode="guide"  # Utilisation du mode guide qui est plus léger
            )
            
            # Affichage et enregistrement des résultats
            print(f"\n{'='*40}\nRÉPONSE {i}:\n{'='*40}\n")
            if response:
                formatted_response = json.dumps(response, ensure_ascii=False, indent=2)
                print(formatted_response)
                results.append({
                    "question": question,
                    "response": response,
                    "success": True if response else False
                })
            else:
                print("Aucune réponse reçue.")
                results.append({
                    "question": question,
                    "response": None,
                    "success": False
                })
        
        # Synthèse des résultats
        print(f"\n{'='*40}\nRÉSUMÉ DE LA SIMULATION\n{'='*40}\n")
        for i, result in enumerate(results, 1):
            status = "✅ RÉUSSI" if result["success"] else "❌ ÉCHEC"
            print(f"Question {i}: {status}")
        
        return results
        
    except Exception as e:
        logger.error(f"Erreur lors du test du ChatBot: {str(e)}", exc_info=True)
        return None

if __name__ == "__main__":
    try:
        # Exécution de la simulation complète
        print("Lancement de la simulation du ChatBot avec des questions impliquant des dates...\n")
        results = asyncio.run(test_chatbot_date_simulation())
        
        # Vérification des résultats
        if results:
            success_count = sum(1 for r in results if r["success"])
            print(f"\nSimulation terminée : {success_count}/{len(results)} tests réussis.")
        else:
            print("\nLa simulation a échoué.")
            
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur.")
    except Exception as e:
        print(f"\nErreur lors de l'exécution du test: {str(e)}")
