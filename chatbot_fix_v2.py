"""
Script de correction pour le chatbot - Version 2

Ce script corrige les problèmes identifiés dans le chatbot en s'adaptant à la signature
des fonctions existantes.
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('ITS_HELP')

print("\nVariables d'environnement chargées.\n")

# Import après chargement des variables d'environnement
from gestion_clients import initialiser_base_clients, extract_client_name  # noqa: E402
from chatbot import ChatBot  # noqa: E402

# Fonction pour inspecter les signatures des méthodes
def inspect_method_signature(obj, method_name):
    """Inspecte la signature d'une méthode pour comprendre ses paramètres"""
    import inspect
    
    if hasattr(obj, method_name):
        method = getattr(obj, method_name)
        sig = inspect.signature(method)
        print(f"Signature de {method_name}: {sig}")
        return sig
    else:
        print(f"La méthode {method_name} n'existe pas dans l'objet")
        return None

# Correctif pour extract_client_name
async def extract_client_name_fixed(text: str) -> Optional[Dict[str, str]]:
    """
    Version corrigée de extract_client_name qui gère correctement les appels async/await
    """
    # Si la fonction originale est déjà async, on l'utilise directement
    if asyncio.iscoroutinefunction(extract_client_name):
        return await extract_client_name(text)
    
    # Sinon, on utilise la version synchrone
    return extract_client_name(text)

# Correctif pour process_web_message
async def process_web_message_fixed(self, text: str, conversation: Any, user_id: str, mode: str = "detail"):
    """
    Version corrigée de process_web_message qui s'adapte aux signatures existantes
    """
    self.logger.info(f"Traitement du message: {text}")
    
    try:
        # 1. Analyser la question
        analysis = await asyncio.wait_for(self.analyze_question(text), timeout=60)
        self.logger.info(f"Analyse terminée pour: {text}")
        
        # 2. Déterminer le client explicitement
        client_info = None
        client_name = 'Non spécifié'
        
        try:
            # Utiliser la fonction corrigée
            client_info = await extract_client_name_fixed(text)
            if client_info and isinstance(client_info, dict) and 'source' in client_info:
                client_name = client_info.get('source')
                self.logger.info(f"Client trouvé: {client_name}")
            else:
                self.logger.warning(f"Aucun client trouvé dans: {text}")
        except Exception as e:
            self.logger.error(f"Erreur lors de la détection du client: {str(e)}")
            client_info = None
        
        # 3. Effectuer la recherche avec le client détecté
        # On utilise les paramètres existants sans context_limit
        self.logger.info(f"Lancement de la recherche pour: {text}")
        
        # Vérifions la signature de recherche_coordonnee d'abord
        import inspect
        sig = inspect.signature(self.recherche_coordonnee)
        param_names = list(sig.parameters.keys())
        
        # On adapte les paramètres à la signature existante
        search_params = {"question": text}
        if "client_info" in param_names:
            search_params["client_info"] = client_info
        if "top_k_zendesk" in param_names:
            search_params["top_k_zendesk"] = 5
        
        resultats = await self.recherche_coordonnee(**search_params)
        
        # 4. Vérifier si des résultats ont été trouvés
        if not resultats or len(resultats) == 0:
            self.logger.warning(f"Aucun résultat trouvé pour: {text}")
            return {
                "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question.",
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question."}}],
                "metadata": {"client": client_name}
            }
        
        # 5. Générer la réponse avec les résultats trouvés
        self.logger.info(f"{len(resultats)} résultats trouvés, génération de la réponse...")
        
        # Pour le mode et les autres paramètres, on respecte la signature existante
        if hasattr(self, 'generate_response'):
            # Vérifions la signature de generate_response
            sig_gen = inspect.signature(self.generate_response)
            gen_param_names = list(sig_gen.parameters.keys())
            
            gen_params = {"question": text, "resultats": resultats}
            if "client_info" in gen_param_names:
                gen_params["client_info"] = client_info
            if "mode" in gen_param_names:
                gen_params["mode"] = mode
            
            response = await self.generate_response(**gen_params)
            return response
        else:
            # Fallback simple si generate_response n'existe pas
            return {
                "text": f"J'ai trouvé {len(resultats)} résultats pour votre question.",
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"J'ai trouvé {len(resultats)} résultats pour votre question."}}],
                "metadata": {"client": client_name}
            }
    
    except Exception as e:
        self.logger.error(f"Erreur lors du traitement du message: {str(e)}", exc_info=True)
        return {
            "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}"}}],
            "metadata": {"client": client_name if 'client_name' in locals() else 'Non spécifié', "error": str(e)}
        }

async def main():
    """
    Fonction principale qui applique les correctifs adaptés et exécute des tests
    """
    try:
        print("⚙️ Application des correctifs au chatbot...")
        
        # 1. Initialisation de la base des clients
        print("Initialisation de la base des clients...")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée")
        
        # 2. Récupération des clés API
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not openai_key or not qdrant_url:
            print("❌ Clés API manquantes: OPENAI_API_KEY ou QDRANT_URL")
            return
        
        # 3. Initialisation du ChatBot
        print("Initialisation du ChatBot...")
        chatbot = ChatBot(
            openai_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key
        )
        print("✅ ChatBot initialisé")
        
        # 4. Inspection des méthodes clés
        print("\nInspection des méthodes clés pour adapter les correctifs...")
        inspect_method_signature(chatbot, "recherche_coordonnee")
        inspect_method_signature(chatbot, "generate_response")
        inspect_method_signature(chatbot, "process_web_message")
        
        # 5. Application du correctif pour process_web_message
        print("\nApplication du correctif pour process_web_message...")
        original_process_web_message = ChatBot.process_web_message
        ChatBot.process_web_message = process_web_message_fixed
        print("✅ Correctif appliqué")
        
        # 6. Test avec une question impliquant RONDOT
        print("\n🧪 Test avec une question impliquant RONDOT...")
        conversation = {"id": "test_conversation", "user_id": "test_user"}
        
        response = await chatbot.process_web_message(
            text="Quels sont les derniers tickets de RONDOT?",
            conversation=conversation,
            user_id="test_user",
            mode="guide"
        )
        
        print("✅ Test terminé")
        print(f"Réponse: {response.get('text')[:100]}..." if len(response.get('text', '')) > 100 else f"Réponse: {response.get('text')}")
        print(f"Metadata: {response.get('metadata')}")
        
        # 7. Restauration de la méthode originale
        print("\nRestauration de la méthode originale...")
        ChatBot.process_web_message = original_process_web_message
        print("✅ Méthode originale restaurée")
        
        # 8. Instructions pour corriger définitivement le code
        print("\n📋 Pour corriger définitivement le chatbot.py, suivez ces instructions:")
        print("1. Corrigez la fonction extract_client_name pour qu'elle soit synchrone ou utilisez awaits correctement")
        print("2. Assurez-vous que process_web_message utilise la bonne signature pour recherche_coordonnee")
        print("3. Ajoutez une gestion appropriée des résultats vides")
        print("4. Vérifiez que la détection de client fonctionne correctement")
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)
        print(f"❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
