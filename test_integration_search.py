#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test d'intégration pour les clients de recherche standardisés.
Vérifie que les clients fonctionnent correctement avec le chatbot.
"""

import sys
import asyncio
import logging
from dotenv import load_dotenv

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_integration")

# Charger les variables d'environnement
load_dotenv()  # noqa: E402

# Importer après le chargement des variables d'environnement
from search_factory import search_factory  # noqa: E402
from chatbot import ChatBot  # noqa: E402

async def test_search_clients():
    """
    Test d'intégration pour vérifier que les clients de recherche
    fonctionnent correctement avec le chatbot.
    """
    logger.info("=== Début du test d'intégration des clients de recherche ===")
    
    # Initialiser la factory
    logger.info("Initialisation de la factory...")
    await search_factory.initialize()
    
    # Vérifier que les clients sont correctement initialisés
    required_clients = ['jira', 'zendesk', 'confluence', 'netsuite', 'sap']
    missing_clients = []
    
    for client_type in required_clients:
        client = await search_factory.get_client(client_type)
        if client:
            logger.info(f"Client {client_type} initialisé correctement: {client.get_source_name()}")
            
            # Vérifier que le client a la méthode recherche_intelligente
            if hasattr(client, 'recherche_intelligente'):
                logger.info(f"Client {client_type} a la méthode recherche_intelligente ")
            else:
                logger.error(f"Client {client_type} n'a PAS la méthode recherche_intelligente ")
                missing_clients.append(client_type)
        else:
            logger.error(f"Client {client_type} n'a pas pu être initialisé ")
            missing_clients.append(client_type)
    
    if missing_clients:
        logger.error(f"Clients manquants ou incomplets: {missing_clients}")
        return False
    
    # Initialiser le chatbot
    logger.info("Initialisation du chatbot...")
    chatbot = ChatBot()
    
    # Tester une recherche avec le chatbot
    test_question = "Comment créer un document dans NetSuite?"
    logger.info(f"Test de recherche avec la question: {test_question}")
    
    try:
        # Utiliser directement un client pour tester la recherche
        netsuite_client = await search_factory.get_client('netsuite')
        search_results = await netsuite_client.recherche_intelligente(
            question=test_question,
            limit=3
        )
        
        if search_results:
            logger.info(f"Recherche NetSuite réussie: {len(search_results)} résultats")
            
            # Vérifier le format du premier résultat
            if len(search_results) > 0:
                result = search_results[0]
                logger.info(f"Score du premier résultat: {getattr(result, 'score', 'N/A')}")
                
                # Vérifier si on peut formater le résultat
                formatted = await netsuite_client.format_for_slack(result)
                if formatted:
                    logger.info("Formatage pour Slack réussi")
                else:
                    logger.warning("Formatage pour Slack a échoué ou a retourné None")
        else:
            logger.warning("Aucun résultat trouvé (ce n'est pas nécessairement une erreur)")
            
        # Maintenant, tester une recherche complète via le chatbot
        logger.info("Test de recherche via le chatbot...")
        
        # Simuler un message utilisateur
        message = {
            "text": test_question,
            "user": "test_user",
            "ts": "1234567890.123456",
            "client_info": {"source": "TEST_CLIENT"},
            "channel": "test_channel"
        }
        
        # Exécuter le processus de message du chatbot
        response = await chatbot.process_message(message)
        
        if response:
            logger.info("Chatbot a généré une réponse")
            if isinstance(response, dict) and 'text' in response:
                logger.info(f"Longueur de la réponse: {len(response['text'])} caractères")
            else:
                logger.info(f"Type de réponse: {type(response)}")
        else:
            logger.error("Le chatbot n'a pas généré de réponse")
            return False
        
        logger.info("=== Test d'intégration terminé avec succès ===")
        return True
        
    except Exception as e:
        logger.error(f"Erreur lors du test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Exécuter le test d'intégration
    success = asyncio.run(test_search_clients())
    
    # Sortir avec le code approprié
    sys.exit(0 if success else 1)
