# test_chatbot.py
import os
import asyncio
import logging
from dotenv import load_dotenv

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)
print("Variables d'environnement chargées :")
print(f"OPENAI_API_KEY: {'Définie' if os.getenv('OPENAI_API_KEY') else 'Non définie'}")
print(f"QDRANT_URL: {'Définie' if os.getenv('QDRANT_URL') else 'Non définie'}")
print(f"QDRANT_API_KEY: {'Définie' if os.getenv('QDRANT_API_KEY') else 'Non définie'}")
print(f"LOG_LEVEL: {'Définie' if os.getenv('LOG_LEVEL') else 'Non définie'}")
print(f"ENVIRONMENT: {'Définie' if os.getenv('ENVIRONMENT') else 'Non définie'}")

# Configuration du logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_chatbot')

# NOTE: L'import suivant est intentionnellement placé ici et non en haut du fichier.
# Cette dérogation aux conventions PEP8 est nécessaire car le ChatBot a besoin 
# des variables d'environnement chargées ci-dessus pour fonctionner correctement.
# Sans ce chargement préalable, les clés API et configurations ne seraient pas accessibles.
# noqa: E402  # Désactive l'avertissement de linter pour l'import non situé en haut du fichier
from chatbot import ChatBot  # Import non situé en haut du fichier, mais nécessaire après le chargement des variables d'environnement  # noqa: E402

async def test_chatbot():
    """Fonction de test pour le chatbot"""
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
        
        # Test avec un message simple
        user_id = "test_user"
        message = "Qu'est-ce que NetSuite ?"  # Question simplifiée pour éviter le timeout
        
        # Création d'un objet conversation simulé
        conversation = {"id": "test_conversation", "user_id": user_id}
        
        logger.info(f"Envoi du message de test: {message}")
        response = await chatbot.process_web_message(
            text=message,
            conversation=conversation,
            user_id=user_id,
            mode="guide"  # Utilisation du mode guide qui est plus léger
        )
        
        logger.info(f"Réponse reçue: {response}")
        return response
    except Exception as e:
        logger.error(f"Erreur lors du test du ChatBot: {str(e)}", exc_info=True)
        return None

if __name__ == "__main__":
    try:
        response = asyncio.run(test_chatbot())
        
        if response:
            print("\n========== RÉPONSE DU CHATBOT ==========")
            if isinstance(response, dict):
                if "text" in response:
                    print(f"Texte: {response.get('text', 'N/A')}")
                elif "message" in response:
                    print(f"Message: {response.get('message', 'N/A')}")
                elif "blocks" in response:
                    print("Contenu des blocs:")
                    for block in response.get("blocks", []):
                        if "text" in block and isinstance(block["text"], dict):
                            print(f"- {block['text'].get('text', 'N/A')}")
                        else:
                            print(f"- {block}")
            else:
                print(response)
            print("=========================================\n")
        else:
            print("\nLe test a échoué. Consultez les logs pour plus de détails.")
    except Exception as e:
        print(f"Erreur lors de l'exécution du test: {str(e)}")
        import traceback
        traceback.print_exc()
