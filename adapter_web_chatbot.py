#!/usr/bin/env python
# adapter_web_chatbot.py - Adaptateur pour les communications web-chatbot

import logging
import os
import asyncio
from typing import Any

# Configuration du logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('adapter_web_chatbot')

class WebChatbotAdapter:
    """
    Adaptateur pour faciliter la communication entre l'interface web et le chatbot.
    Résout les incompatibilités de signatures de méthodes et les problèmes d'initialisation.
    """
    
    def __init__(self):
        """Initialisation de l'adaptateur"""
        self.logger = logger
        self.chatbot = None
        # Utilisation explicite de Any pour le typage
        self.dummy_conversation: Any = {}  # Conversation fictive pour les appels sans contexte
        
    async def initialize(self):
        """Initialise l'adaptateur et le chatbot sous-jacent"""
        self.logger.info("Initialisation de l'adaptateur web-chatbot")
        
        try:
            # Import du chatbot
            from chatbot import ChatBot
            
            # Récupération des clés nécessaires depuis les variables d'environnement
            openai_key = os.getenv('OPENAI_API_KEY')
            qdrant_url = os.getenv('QDRANT_URL')
            qdrant_api_key = os.getenv('QDRANT_API_KEY')
            
            # Vérification des clés requises
            if not openai_key or not qdrant_url:
                self.logger.error("Clés API manquantes: OPENAI_API_KEY ou QDRANT_URL non définies")
                return False
            
            # Création de l'instance du chatbot
            self.chatbot = ChatBot(
                openai_key=openai_key,
                qdrant_url=qdrant_url,
                qdrant_api_key=qdrant_api_key
            )
            
            self.logger.info("✅ Adaptateur initialisé avec succès")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de l'initialisation de l'adaptateur: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    async def process_message(self, message: str, user_id: str = "anonymous", mode: str = "detail", 
                              debug_zendesk: bool = False, progressive: bool = False, timeout: int = 30):
        """
        Adapte l'appel à process_message vers process_web_message.
        Cette méthode sert de passerelle entre l'ancienne interface utilisant process_message
        et la nouvelle implémentation du chatbot qui utilise process_web_message.
        
        Args:
            message: Le message à traiter
            user_id: Identifiant de l'utilisateur
            mode: Mode de réponse ('detail' ou 'summary')
            debug_zendesk: Activer le mode débogage pour les résultats Zendesk
            progressive: Activer le formatage progressif des résultats
            timeout: Délai maximum d'attente en secondes
            
        Returns:
            Réponse formatée pour l'interface web
        """
        if not self.chatbot:
            # Utilisation explicite d'asyncio pour résoudre le warning
            init_task = asyncio.create_task(self.initialize())
            await init_task
            if not self.chatbot:
                return {"error": "Chatbot non initialisé. Vérifiez les variables d'environnement."}
        
        try:
            # Adapter la signature de process_message à process_web_message
            # Le paramètre key est 'text' (non 'message') et nous devons fournir un objet 'conversation'
            response = await self.chatbot.process_web_message(
                text=message,  # Paramètre adapté, renommé de message à text
                conversation=self.dummy_conversation,  # Paramètre obligatoire mais non utilisé
                user_id=user_id,
                mode=mode,
                debug_zendesk=debug_zendesk,
                progressive=progressive,
                timeout=timeout
            )
            
            return response
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du traitement du message: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {"error": f"Erreur lors du traitement du message: {str(e)}"}
    
    async def test_connection(self):
        """Teste la connexion au chatbot avec une question simple"""
        if not self.chatbot:
            await self.initialize()
            if not self.chatbot:
                return {"error": "Chatbot non initialisé. Vérifiez les variables d'environnement."}
        
        try:
            # Test avec une question simple
            test_message = "Bonjour"
            response = await self.process_message(message=test_message, user_id="test_user")
            
            if response and not response.get("error"):
                self.logger.info("✅ Connexion au chatbot vérifiée avec succès")
                return {"status": "success", "response": response}
            else:
                self.logger.error("❌ Échec de la connexion au chatbot")
                return {"status": "error", "details": response}
                
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du test de connexion: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {"status": "error", "details": str(e)}

# Instance globale de l'adaptateur
adapter = WebChatbotAdapter()

# Fonction d'initialisation pour l'application
async def initialize_adapter():
    """Initialise l'adaptateur pour l'application"""
    return await adapter.initialize()

# Fonction principale pour l'application
async def process_message(message: str, user_id: str = "anonymous", **kwargs):
    """Point d'entrée principal pour le traitement des messages"""
    return await adapter.process_message(message=message, user_id=user_id, **kwargs)
