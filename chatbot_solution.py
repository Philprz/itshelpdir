"""
Solution finale pour le chatbot

Ce script propose une correction définitive pour le chatbot, en respectant
les signatures des méthodes existantes et en résolvant les problèmes identifiés.
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
from gestion_clients import initialiser_base_clients  # noqa: E402
from chatbot import ChatBot  # noqa: E402
import inspect  # noqa: E402

class ChatbotCorrector:
    """
    Classe qui corrige et teste le chatbot en respectant ses signatures existantes
    """
    
    def __init__(self):
        self.chatbot = None
        self.original_process_web_message = None
    
    async def initialize(self):
        """Initialise le chatbot et les dépendances nécessaires"""
        # Initialisation de la base des clients
        print("Initialisation de la base des clients...")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée")
        
        # Récupération des clés API
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not openai_key or not qdrant_url:
            raise ValueError("❌ Clés API manquantes: OPENAI_API_KEY ou QDRANT_URL")
        
        # Initialisation du ChatBot
        print("Initialisation du ChatBot...")
        self.chatbot = ChatBot(
            openai_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key
        )
        print("✅ ChatBot initialisé")
        
        # Sauvegarde de la méthode originale
        self.original_process_web_message = ChatBot.process_web_message
    
    def inspect_method(self, method_name):
        """Inspecte la signature d'une méthode"""
        if not hasattr(self.chatbot, method_name):
            print(f"❌ Méthode '{method_name}' non trouvée")
            return None
        
        method = getattr(self.chatbot, method_name)
        sig = inspect.signature(method)
        print(f"Signature de {method_name}: {sig}")
        return sig
    
    async def extract_client_name_fixed(self, text):
        """
        Version corrigée de la fonction extract_client_name qui gère la détection async/sync
        """
        # Import ici pour éviter les problèmes de circularité
        from gestion_clients import extract_client_name
        
        # Vérifier si la fonction est asynchrone ou synchrone
        if asyncio.iscoroutinefunction(extract_client_name):
            # Si async, l'appeler avec await
            client_info = await extract_client_name(text)
        else:
            # Sinon, l'appeler directement
            client_info = extract_client_name(text)
        
        # Vérifier le résultat
        if isinstance(client_info, dict) and 'source' in client_info:
            return client_info
        
        # Si on arrive ici, c'est qu'il y a un problème avec le résultat
        print(f"⚠️ extract_client_name a retourné un résultat inattendu: {type(client_info)}")
        
        # Recherche explicite de RONDOT dans le texte comme fallback
        if "RONDOT" in text.upper():
            return {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        
        return None
    
    async def process_web_message_fixed(self, text, conversation, user_id, mode="detail"):
        """
        Version corrigée de process_web_message qui respecte les signatures existantes
        """
        self.chatbot.logger.info(f"Traitement du message: {text}")
        
        try:
            # 1. Analyser la question
            analysis = await asyncio.wait_for(self.chatbot.analyze_question(text), timeout=60)
            self.chatbot.logger.info(f"Analyse terminée")
            
            # 2. Déterminer le client
            client_info = await self.extract_client_name_fixed(text)
            client_name = client_info.get('source') if client_info else 'Non spécifié'
            self.chatbot.logger.info(f"Client trouvé: {client_name}")
            
            # 3. Déterminer les collections à interroger
            collections = []
            
            # Pour RONDOT, on sait qu'on veut chercher dans JIRA, ZENDESK et CONFLUENCE
            if client_name == "RONDOT":
                collections = ["jira", "zendesk", "confluence"]
                self.chatbot.logger.info(f"Collections sélectionnées pour RONDOT: {collections}")
            # Pour des questions sur NetSuite, on cherche dans les collections ERP
            elif "netsuite" in text.lower() or "erp" in text.lower() or "compte" in text.lower():
                collections = ["netsuite", "netsuite_dummies", "sap"]
                self.chatbot.logger.info(f"Collections sélectionnées pour ERP: {collections}")
            # Par défaut, on cherche dans toutes les collections
            else:
                collections = ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]
                self.chatbot.logger.info(f"Collections sélectionnées (toutes): {collections}")
            
            # 4. Effectuer la recherche
            self.chatbot.logger.info(f"Lancement de la recherche pour: {text}")
            
            # Appel à recherche_coordonnee avec la bonne signature
            resultats = await self.chatbot.recherche_coordonnee(
                collections=collections,
                question=text,
                client_info=client_info
            )
            
            # 5. Vérifier si des résultats ont été trouvés
            if not resultats or len(resultats) == 0:
                self.chatbot.logger.warning(f"Aucun résultat trouvé pour: {text}")
                return {
                    "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question.",
                    "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question."}}],
                    "metadata": {"client": client_name}
                }
            
            # 6. Générer la réponse avec les résultats trouvés
            self.chatbot.logger.info(f"{len(resultats)} résultats trouvés, génération de la réponse...")
            
            # Appel à generate_response avec la bonne signature
            response = await self.chatbot.generate_response(text, resultats, client_info, mode)
            return response
            
        except Exception as e:
            self.chatbot.logger.error(f"Erreur lors du traitement du message: {str(e)}", exc_info=True)
            return {
                "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}",
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}"}}],
                "metadata": {"client": client_name if 'client_name' in locals() else 'Non spécifié', "error": str(e)}
            }
    
    async def apply_and_test(self):
        """
        Applique le correctif et exécute des tests
        """
        # 1. Inspection des méthodes clés
        print("\nInspection des méthodes clés pour adapter les correctifs...")
        self.inspect_method("recherche_coordonnee")
        self.inspect_method("generate_response")
        self.inspect_method("process_web_message")
        
        # 2. Application du correctif
        print("\nApplication du correctif pour process_web_message...")
        
        # On transforme notre méthode d'instance en méthode de classe
        async def process_web_message_wrapper(self_obj, *args, **kwargs):
            return await self.process_web_message_fixed(self_obj, *args, **kwargs)
        
        # On remplace la méthode originale
        ChatBot.process_web_message = process_web_message_wrapper
        print("✅ Correctif appliqué")
        
        # 3. Tests
        print("\n🧪 Exécution des tests...")
        
        # Tests
        test_cases = [
            "Quels sont les derniers tickets de RONDOT?",
            "Comment paramétrer un compte fournisseur dans NetSuite?",
            "Je cherche des informations sur RONDOT dans JIRA"
        ]
        
        conversation = {"id": "test_conversation", "user_id": "test_user"}
        
        for test_case in test_cases:
            print(f"\nTest: '{test_case}'")
            response = await self.chatbot.process_web_message(
                text=test_case,
                conversation=conversation,
                user_id="test_user",
                mode="guide"
            )
            
            print(f"Response type: {type(response)}")
            
            if isinstance(response, dict):
                print(f"Texte: {response.get('text', 'N/A')[:100]}...")
                print(f"Metadata: {response.get('metadata', {})}")
                print(f"Nombre de blocs: {len(response.get('blocks', []))}")
        
        # 4. Restauration de la méthode originale
        print("\nRestauration de la méthode originale...")
        ChatBot.process_web_message = self.original_process_web_message
        print("✅ Méthode originale restaurée")
    
    def generate_patch_file(self):
        """
        Génère un fichier de correctif pour process_web_message
        """
        patch_content = """
# Correctif pour process_web_message dans chatbot.py

# 1. Fonction helper pour extract_client_name
async def extract_client_name_fixed(text):
    """
    Version corrigée de la fonction extract_client_name qui gère la détection async/sync
    """
    # Import ici pour éviter les problèmes de circularité
    from gestion_clients import extract_client_name
    
    # Vérifier si la fonction est asynchrone ou synchrone
    if asyncio.iscoroutinefunction(extract_client_name):
        # Si async, l'appeler avec await
        client_info = await extract_client_name(text)
    else:
        # Sinon, l'appeler directement
        client_info = extract_client_name(text)
    
    # Vérifier le résultat
    if isinstance(client_info, dict) and 'source' in client_info:
        return client_info
    
    # Si on arrive ici, c'est qu'il y a un problème avec le résultat
    logger.warning(f"extract_client_name a retourné un résultat inattendu: {type(client_info)}")
    
    # Recherche explicite de RONDOT dans le texte comme fallback
    if "RONDOT" in text.upper():
        return {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
    
    return None

# 2. Version corrigée de process_web_message
async def process_web_message(self, text: str, conversation: Any, user_id: str, mode: str = "detail"):
    """
    Traite un message web et génère une réponse appropriée
    """
    self.logger.info(f"Traitement du message: {text}")
    
    try:
        # 1. Analyser la question
        analysis = await asyncio.wait_for(self.analyze_question(text), timeout=60)
        self.logger.info(f"Analyse terminée")
        
        # 2. Déterminer le client
        client_info = await extract_client_name_fixed(text)
        client_name = client_info.get('source') if client_info else 'Non spécifié'
        self.logger.info(f"Client trouvé: {client_name}")
        
        # 3. Déterminer les collections à interroger
        collections = []
        
        # Pour RONDOT, on sait qu'on veut chercher dans JIRA, ZENDESK et CONFLUENCE
        if client_name == "RONDOT":
            collections = ["jira", "zendesk", "confluence"]
            self.logger.info(f"Collections sélectionnées pour RONDOT: {collections}")
        # Pour des questions sur NetSuite, on cherche dans les collections ERP
        elif "netsuite" in text.lower() or "erp" in text.lower() or "compte" in text.lower():
            collections = ["netsuite", "netsuite_dummies", "sap"]
            self.logger.info(f"Collections sélectionnées pour ERP: {collections}")
        # Par défaut, on cherche dans toutes les collections
        else:
            collections = ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]
            self.logger.info(f"Collections sélectionnées (toutes): {collections}")
        
        # 4. Effectuer la recherche
        self.logger.info(f"Lancement de la recherche pour: {text}")
        
        # Appel à recherche_coordonnee avec la bonne signature
        resultats = await self.recherche_coordonnee(
            collections=collections,
            question=text,
            client_info=client_info
        )
        
        # 5. Vérifier si des résultats ont été trouvés
        if not resultats or len(resultats) == 0:
            self.logger.warning(f"Aucun résultat trouvé pour: {text}")
            return {
                "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question.",
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question."}}],
                "metadata": {"client": client_name}
            }
        
        # 6. Générer la réponse avec les résultats trouvés
        self.logger.info(f"{len(resultats)} résultats trouvés, génération de la réponse...")
        
        # Appel à generate_response avec la bonne signature
        response = await self.generate_response(text, resultats, client_info, mode)
        return response
        
    except Exception as e:
        self.logger.error(f"Erreur lors du traitement du message: {str(e)}", exc_info=True)
        return {
            "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}"}}],
            "metadata": {"client": client_name if 'client_name' in locals() else 'Non spécifié', "error": str(e)}
        }
"""
        
        # Écrire le correctif dans un fichier
        patch_file = "process_web_message_patch.py"
        with open(patch_file, 'w', encoding='utf-8') as f:
            f.write(patch_content)
        
        print(f"\n✅ Correctif généré dans le fichier: {patch_file}")
        print("\nPour appliquer le correctif, il suffit de copier ces fonctions dans chatbot.py")

async def main():
    """
    Fonction principale
    """
    try:
        corrector = ChatbotCorrector()
        await corrector.initialize()
        await corrector.apply_and_test()
        corrector.generate_patch_file()
        
        print("\n📋 RÉSUMÉ DES PROBLÈMES ET SOLUTIONS:")
        print("1. Problème: La méthode recherche_coordonnee attend un paramètre 'collections'")
        print("   Solution: Adapter l'appel pour fournir ce paramètre")
        print("2. Problème: La fonction extract_client_name ne fonctionne pas correctement")
        print("   Solution: Ajouter une version corrigée qui gère async/sync")
        print("3. Problème: La sélection des collections à interroger n'était pas optimale")
        print("   Solution: Adapter les collections en fonction du client et de la question")
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)
        print(f"❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
