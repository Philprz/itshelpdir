import os
import asyncio
import logging
from dotenv import load_dotenv
import json
import sys

# Désactiver temporairement les logs pour avoir une sortie propre
logging.disable(logging.CRITICAL)

# Rediriger stdout temporairement pour capturer les logs non désactivés
class CaptureOutput:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = self._redirected = open(os.devnull, 'w')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout

# Chargement des variables d'environnement silencieusement
with CaptureOutput():
    load_dotenv(verbose=False)

# Import après chargement des variables d'environnement
from chatbot import ChatBot  # noqa: E402

async def test_specific_questions_with_clear_output():
    """
    Test du chatbot avec des questions spécifiques et affichage clair des résultats
    """
    # Questions spécifiques à tester
    questions = [
        "Tickets de RONDOT 2025.",
        "Comment paramétrer le compte fournisseur."
    ]
    
    try:
        # Récupération des clés API depuis les variables d'environnement
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not openai_key or not qdrant_url:
            print("❌ Erreur: Clés API manquantes (OPENAI_API_KEY ou QDRANT_URL)")
            return None
        
        print("🔄 Initialisation du ChatBot...\n")
        
        # Initialisation du ChatBot silencieusement
        with CaptureOutput():
            chatbot = ChatBot(
                openai_key=openai_key,
                qdrant_url=qdrant_url,
                qdrant_api_key=qdrant_api_key
            )
        
        # Création d'un objet conversation simulé
        user_id = "test_user"
        conversation = {"id": "test_conversation", "user_id": user_id}
        
        # Traitement de chaque question
        for i, question in enumerate(questions, 1):
            print(f"\n{'='*80}")
            print(f"📝 QUESTION {i}: {question}")
            print(f"{'='*80}\n")
            
            # Traitement de la question silencieusement
            with CaptureOutput():
                response = await chatbot.process_web_message(
                    text=question,
                    conversation=conversation,
                    user_id=user_id,
                    mode="guide"
                )
            
            # Affichage de la réponse
            print(f"🔹 RÉPONSE {i}:\n")
            
            if response:
                # Extraction du texte principal des blocs de réponse
                extracted_text = []
                
                if isinstance(response, list):
                    for block in response:
                        if block.get("type") == "section" and "text" in block:
                            text_block = block["text"]
                            if isinstance(text_block, dict) and "text" in text_block:
                                extracted_text.append(text_block["text"])
                            elif isinstance(text_block, str):
                                extracted_text.append(text_block)
                
                if extracted_text:
                    for text in extracted_text:
                        print(f"{text}\n")
                else:
                    # Si nous n'avons pas pu extraire le texte, afficher la réponse brute
                    print(json.dumps(response, ensure_ascii=False, indent=2))
            else:
                print("❌ Aucune réponse reçue.")
            
            # Mettre en pause entre les questions pour permettre la lecture
            if i < len(questions):
                input("\n🔍 Appuyez sur Entrée pour continuer vers la question suivante...\n")
        
        print(f"\n{'='*80}")
        print("✅ Test terminé avec succès!")
        print(f"{'='*80}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Erreur: {str(e)}")
        return False

if __name__ == "__main__":
    try:
        print("\n🚀 DÉMARRAGE DU TEST DU CHATBOT\n")
        asyncio.run(test_specific_questions_with_clear_output())
    except KeyboardInterrupt:
        print("\n🛑 Test interrompu par l'utilisateur.")
    except Exception as e:
        print(f"\n❌ Erreur fatale: {str(e)}")
