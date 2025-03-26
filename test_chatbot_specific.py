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

async def test_chatbot_specific_questions():
    """
    Test du chatbot avec des questions spécifiques
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
        
        # Questions spécifiques à tester
        questions = [
            "Tickets de RONDOT 2025.",
            "Comment paramétrer le compte fournisseur."
        ]
        
        # Création d'un objet conversation simulé
        user_id = "test_user"
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
                mode="guide"
            )
            
            # Affichage et enregistrement des réponses complètes
            print(f"\n{'='*40}\nRÉPONSE {i}:\n{'='*40}\n")
            if response:
                formatted_response = json.dumps(response, ensure_ascii=False, indent=4)
                print(formatted_response)
                
                # Extraction et affichage du texte principal de la réponse
                if isinstance(response, list) and len(response) > 0:
                    blocks = response
                    text_content = []
                    for block in blocks:
                        if block.get("type") == "section" and "text" in block:
                            text_block = block["text"]
                            if isinstance(text_block, dict) and "text" in text_block:
                                text_content.append(text_block["text"])
                            elif isinstance(text_block, str):
                                text_content.append(text_block)
                    
                    if text_content:
                        print(f"\n{'='*40}\nCONTENU TEXTUEL PRINCIPAL:\n{'='*40}\n")
                        for text in text_content:
                            print(text)
                
                results.append({
                    "question": question,
                    "response": response,
                    "success": True
                })
            else:
                print("Aucune réponse reçue.")
                results.append({
                    "question": question,
                    "response": None,
                    "success": False
                })
        
        # Synthèse des résultats
        print(f"\n{'='*40}\nRÉSUMÉ DU TEST\n{'='*40}\n")
        for i, result in enumerate(results, 1):
            status = "✅ RÉUSSI" if result["success"] else "❌ ÉCHEC"
            print(f"Question {i}: {status}")
        
        return results
        
    except Exception as e:
        logger.error(f"Erreur lors du test du ChatBot: {str(e)}", exc_info=True)
        return None

if __name__ == "__main__":
    try:
        # Exécution du test avec les questions spécifiques
        print("Test du ChatBot avec les questions spécifiques...\n")
        results = asyncio.run(test_chatbot_specific_questions())
        
        # Vérification des résultats
        if results:
            success_count = sum(1 for r in results if r["success"])
            print(f"\nTest terminé : {success_count}/{len(results)} questions traitées avec succès.")
        else:
            print("\nLe test a échoué.")
            
    except KeyboardInterrupt:
        print("\nTest interrompu par l'utilisateur.")
    except Exception as e:
        print(f"\nErreur lors de l'exécution du test: {str(e)}")
