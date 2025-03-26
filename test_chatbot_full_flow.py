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
from gestion_clients import initialiser_base_clients  # noqa: E402

async def test_chatbot_full_flow():
    """
    Fonction de simulation complète pour le chatbot testant à la fois
    le formatage des dates et la détection des clients
    """
    try:
        # Initialisation de la base des clients
        print("Initialisation de la base des clients...")
        await initialiser_base_clients()
        print("Base des clients initialisée.\n")
        
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
        
        # Nous utilisons plusieurs questions pour tester différents scénarios
        questions = [
            # Tests de détection de clients
            "Tickets de RONDOT 2025.",
            "Je voudrais voir les tickets ADVIGO de janvier",
            "Problèmes chez AZERGO depuis le 15 février",
            
            # Tests du formatage des dates
            "Comment puis-je consulter une facture du 15 janvier 2023 dans NetSuite ?",
            "Comment extraire un rapport SAP pour les ventes entre le 01/03/2023 et le 25/03/2023 ?",
            "Je cherche un ticket Zendesk créé le 2023-02-15 concernant un problème de connexion.",
            
            # Tests combinés (clients + dates)
            "Tickets ouverts chez RONDOT entre le 01/01/2025 et le 01/03/2025",
            "Derniers tickets de AXA FRANCE créés depuis le 15-02-2023"
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
                # Extraction de la partie spécifique de la réponse concernant le client détecté
                client_info = ""
                if isinstance(response, dict) and "metadata" in response:
                    metadata = response.get("metadata", {})
                    client = metadata.get("client")
                    client_info = f"Client détecté: {client}" if client else "Aucun client détecté dans les métadonnées"
                
                formatted_response = json.dumps(response, ensure_ascii=False, indent=2)
                print(client_info)
                print(formatted_response)
                results.append({
                    "question": question,
                    "client_detected": client_info,
                    "response": response,
                    "success": True if response else False
                })
            else:
                print("Aucune réponse reçue.")
                results.append({
                    "question": question,
                    "client_detected": "Non disponible (pas de réponse)",
                    "response": None,
                    "success": False
                })
        
        # Synthèse des résultats
        print(f"\n{'='*40}\nRÉSUMÉ DE LA SIMULATION\n{'='*40}\n")
        for i, result in enumerate(results, 1):
            status = "✅ RÉUSSI" if result["success"] else "❌ ÉCHEC"
            client_info = result.get("client_detected", "Non disponible")
            print(f"Question {i}: {status} - {client_info}")
        
        return results
        
    except Exception as e:
        logger.error(f"Erreur lors du test du ChatBot: {str(e)}", exc_info=True)
        return None

if __name__ == "__main__":
    try:
        # Exécution de la simulation complète
        print("Lancement de la simulation du ChatBot (flux complet)...\n")
        results = asyncio.run(test_chatbot_full_flow())
        
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
