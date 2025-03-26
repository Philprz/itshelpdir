#!/usr/bin/env python
# Script pour diagnostiquer et corriger les problèmes de communication

import os
import asyncio
import logging
from dotenv import load_dotenv

# Configuration du logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('fix_communication')

async def test_chatbot_methods():
    """Teste les méthodes disponibles dans le chatbot"""
    logger.info("Vérification des méthodes disponibles dans la classe ChatBot...")
    
    try:
        from chatbot import ChatBot
        
        # Récupération des clés nécessaires
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        chatbot = ChatBot(
            openai_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key
        )
        
        # Liste toutes les méthodes publiques
        methods = [method for method in dir(chatbot) if not method.startswith('_')]
        logger.info(f"Méthodes disponibles: {methods}")
        
        # Vérifie spécifiquement les méthodes de traitement de messages
        process_methods = [m for m in methods if 'process' in m]
        logger.info(f"Méthodes de traitement: {process_methods}")
        
        return process_methods
    except Exception as e:
        logger.error(f"Erreur lors de l'inspection du chatbot: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

async def test_web_message():
    """Teste la méthode process_web_message"""
    logger.info("Test de la méthode process_web_message...")
    
    try:
        from chatbot import ChatBot
        
        # Récupération des clés nécessaires
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        chatbot = ChatBot(
            openai_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key
        )
        
        # Test avec une question simple
        test_message = "Comment utiliser SAP?"
        logger.info(f"Envoi de la requête: '{test_message}'")
        
        response = await chatbot.process_web_message(user_id="test_user", message=test_message)
        
        if response:
            logger.info("✅ Requête traitée avec succès via process_web_message")
            logger.info(f"Réponse: {response[:100]}...")
            return True
        else:
            logger.error("❌ La requête n'a pas produit de réponse")
            return False
    except Exception as e:
        logger.error(f"❌ Erreur lors du test de process_web_message: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def check_app_process_message():
    """Vérifie comment app.py utilise la méthode process_message"""
    logger.info("Vérification de l'utilisation de process_message dans app.py...")
    
    try:
        # Analyse simple du fichier app.py pour trouver les appels à process_message
        with open('app.py', 'r', encoding='utf-8') as f:
            app_content = f.read()
        
        # Cherche les références à process_message et process_web_message
        process_message_refs = app_content.count('process_message')
        process_web_message_refs = app_content.count('process_web_message')
        
        logger.info(f"Références à process_message: {process_message_refs}")
        logger.info(f"Références à process_web_message: {process_web_message_refs}")
        
        # Recherche plus précise des appels à la méthode du chatbot
        chatbot_process_calls = app_content.count('chatbot.process_message')
        chatbot_process_web_calls = app_content.count('chatbot.process_web_message')
        
        logger.info(f"Appels à chatbot.process_message: {chatbot_process_calls}")
        logger.info(f"Appels à chatbot.process_web_message: {chatbot_process_web_calls}")
        
        return {
            'process_message_refs': process_message_refs,
            'process_web_message_refs': process_web_message_refs,
            'chatbot_process_calls': chatbot_process_calls,
            'chatbot_process_web_calls': chatbot_process_web_calls
        }
    except Exception as e:
        logger.error(f"Erreur lors de la vérification de app.py: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {}

async def check_socket_handlers():
    """Vérifie les gestionnaires de SocketIO dans app.py"""
    logger.info("Vérification des gestionnaires de SocketIO...")
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            app_content = f.read()
        
        # Cherche les gestionnaires de SocketIO
        socket_handlers = []
        if '@socketio.on' in app_content:
            lines = app_content.splitlines()
            for i, line in enumerate(lines):
                if '@socketio.on' in line:
                    # Récupère la ligne du décorateur et le nom de la fonction qui suit
                    event = line.split("'")[1] if "'" in line else line.split('"')[1] if '"' in line else 'unknown'
                    func_name = lines[i+1].strip().split('def ')[1].split('(')[0] if i+1 < len(lines) and 'def ' in lines[i+1] else 'unknown'
                    socket_handlers.append((event, func_name))
        
        logger.info(f"Gestionnaires de SocketIO trouvés: {socket_handlers}")
        return socket_handlers
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des gestionnaires SocketIO: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

async def run_diagnostic():
    """Exécute tous les diagnostics"""
    load_dotenv()  # Charger les variables d'environnement
    
    # 1. Vérifier les méthodes disponibles dans le chatbot
    process_methods = await test_chatbot_methods()
    
    # 2. Tester la méthode process_web_message
    web_message_works = await test_web_message()
    
    # 3. Vérifier comment app.py utilise les méthodes
    app_usage = await check_app_process_message()
    
    # 4. Vérifier les gestionnaires de SocketIO
    socket_handlers = await check_socket_handlers()
    
    # Analyse et recommandations
    logger.info("\n=== ANALYSE ET RECOMMANDATIONS ===")
    
    if 'process_web_message' in process_methods and web_message_works:
        logger.info("✅ La méthode process_web_message du chatbot fonctionne correctement")
    else:
        logger.error("❌ La méthode process_web_message du chatbot ne fonctionne pas correctement")
    
    if app_usage.get('chatbot_process_calls', 0) > 0 and 'process_message' not in process_methods:
        logger.error("❌ PROBLÈME DÉTECTÉ: app.py appelle chatbot.process_message qui n'existe pas")
        logger.info("   Solution: Modifier app.py pour utiliser chatbot.process_web_message à la place")
    
    if app_usage.get('chatbot_process_web_calls', 0) == 0 and 'process_web_message' in process_methods:
        logger.error("❌ PROBLÈME DÉTECTÉ: app.py n'utilise pas chatbot.process_web_message qui existe")
        logger.info("   Solution: Modifier app.py pour utiliser chatbot.process_web_message")
    
    # Recommandations finales
    logger.info("\n=== RECOMMANDATIONS FINALES ===")
    if 'process_web_message' in process_methods and not web_message_works:
        logger.info("1. Vérifier les erreurs spécifiques lors de l'appel à process_web_message")
    
    if app_usage.get('chatbot_process_calls', 0) > 0 and 'process_message' not in process_methods:
        logger.info("2. Corriger les appels dans app.py pour utiliser process_web_message au lieu de process_message")
        logger.info("   Exemple de correction: chatbot.process_message -> chatbot.process_web_message")
    
    if socket_handlers:
        logger.info(f"3. Vérifier que le gestionnaire de message SocketIO '{socket_handlers[0][0]}' utilise la bonne méthode du chatbot")
    
    # Vérification de la configuration SocketIO
    logger.info("4. Vérifier que la configuration SocketIO dans l'interface web correspond au serveur")
    logger.info("   - Assurez-vous que l'URL de connexion est correcte (localhost:8000)")
    logger.info("   - Vérifiez que les noms d'événements correspondent entre client et serveur")

if __name__ == "__main__":
    # Exécution du diagnostic
    asyncio.run(run_diagnostic())
