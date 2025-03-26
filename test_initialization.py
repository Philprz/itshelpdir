#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script de test d'initialisation des services et clients.
Vérifie que le système d'adaptation des interfaces fonctionne correctement.
"""

import sys
import os
import asyncio
import logging
from dotenv import load_dotenv

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_init")

# Charger les variables d'environnement
load_dotenv()  # noqa: E402

# Importer après le chargement des variables d'environnement
from search_factory import search_factory  # noqa: E402
from chatbot import ChatBot  # noqa: E402


async def test_initialization():
    """
    Vérifie l'initialisation correcte des clients de recherche avec le nouveau système d'adaptation.
    """
    logger.info("=== Début du test d'initialisation ===")
    
    # Initialiser la factory
    logger.info("Initialisation de la factory...")
    await search_factory.initialize()
    
    # Liste des clients à tester
    client_types = [
        'jira', 'zendesk', 'confluence', 'netsuite', 
        'netsuite_dummies', 'sap', 'erp'
    ]
    
    # Résultats du test
    results = {
        "success": [],
        "failure": [],
        "adaptable": [],
        "needs_adaptation": []
    }
    
    # Vérifier chaque client
    for client_type in client_types:
        logger.info(f"Test client {client_type}...")
        try:
            client = await search_factory.get_client(client_type)
            
            if not client:
                logger.error(f"❌ Client {client_type} non disponible")
                results["failure"].append(client_type)
                continue
                
            # Vérifier que le client a bien la méthode recherche_intelligente
            if hasattr(client, 'recherche_intelligente'):
                logger.info(f"✓ Client {client_type} a la méthode recherche_intelligente")
                
                # Tester si c'est un client adapté ou natif
                is_adapter = hasattr(client, 'client') and hasattr(client.client, 'recherche_similaire')
                status = "adaptable" if is_adapter else "success"
                results[status].append(client_type)
                
                # Afficher les détails du client
                source_name = client.get_source_name() if hasattr(client, 'get_source_name') else "UNKNOWN"
                logger.info(f"  - Source: {source_name}")
                logger.info(f"  - Type: {'Adapté' if is_adapter else 'Natif'}")
                
                # Tester les méthodes essentielles
                methods = [
                    'recherche_intelligente', 'valider_resultat', 'get_source_name', 
                    'format_for_slack'
                ]
                for method in methods:
                    if hasattr(client, method):
                        logger.info(f"  - ✓ Méthode {method} disponible")
                    else:
                        logger.warning(f"  - ❌ Méthode {method} manquante")
            else:
                logger.error(f"❌ Client {client_type} n'a pas la méthode recherche_intelligente")
                results["needs_adaptation"].append(client_type)
                
        except Exception as e:
            logger.error(f"❌ Erreur lors du test du client {client_type}: {str(e)}")
            results["failure"].append(client_type)
    
    # Résumé des résultats
    logger.info("=== Résumé des tests ===")
    logger.info(f"Clients fonctionnels: {len(results['success'])}")
    logger.info(f"Clients adaptés: {len(results['adaptable'])}")
    logger.info(f"Clients incompatibles: {len(results['needs_adaptation'])}")
    logger.info(f"Clients en échec: {len(results['failure'])}")
    
    # Détails par catégorie
    for category, clients in results.items():
        if clients:
            logger.info(f"{category.capitalize()}: {', '.join(clients)}")
    
    # Test d'une requête simple
    test_question = "Comment créer un ticket dans Jira?"
    logger.info(f"\nTest de recherche avec question: {test_question}")
    
    # Récupérer les clés nécessaires pour initialiser le chatbot
    openai_key = os.getenv('OPENAI_API_KEY')
    qdrant_url = os.getenv('QDRANT_URL')
    qdrant_api_key = os.getenv('QDRANT_API_KEY')
    
    if not openai_key or not qdrant_url:
        logger.error("❌ Variables d'environnement manquantes pour initialiser le chatbot")
        logger.error(f"OPENAI_API_KEY: {'Présent' if openai_key else 'Manquant'}")
        logger.error(f"QDRANT_URL: {'Présent' if qdrant_url else 'Manquant'}")
        return False
    
    # Créer un chatbot avec les paramètres requis
    chatbot = ChatBot(
        openai_key=openai_key,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key
    )
    
    try:
        # Exécuter la recherche via le chatbot
        response = await chatbot.process_web_message(
            text=test_question,
            conversation=None,
            user_id="test_user",
            mode="detail"
        )
        
        if response:
            logger.info("✓ Recherche réussie via le chatbot")
            logger.info(f"Taille de la réponse: {len(response) if isinstance(response, str) else 'Non-texte'}")
        else:
            logger.error("❌ Échec de la recherche via le chatbot")
            
    except Exception as e:
        logger.error(f"❌ Erreur lors du test de recherche: {str(e)}")
        
    logger.info("=== Fin du test d'initialisation ===")
    
    # Retourner True si aucun client n'est dans la catégorie "needs_adaptation"
    return len(results["needs_adaptation"]) == 0


if __name__ == "__main__":
    # Exécuter le test d'initialisation
    success = asyncio.run(test_initialization())
    
    # Sortir avec le code approprié
    sys.exit(0 if success else 1)
