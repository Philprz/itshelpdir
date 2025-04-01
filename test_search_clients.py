#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test des clients de recherche pour vérifier que la recherche de RONDOT fonctionne.
"""

import asyncio
import logging
import json
from search_clients import AbstractSearchClient, JiraSearchClient, ZendeskSearchClient, ConfluenceSearchClient

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_search_clients')

async def test_search_client(client, question, client_name):
    """Test d'un client de recherche spécifique."""
    logger.info(f"Test de {client.__class__.__name__} pour '{question}' et client '{client_name}'")
    results = await client.recherche_intelligente(question, client_name)
    
    if results:
        logger.info(f"✅ {len(results)} résultats trouvés")
        # Afficher un exemple de résultat
        logger.info(f"Premier résultat: {json.dumps(results[0], indent=2, ensure_ascii=False)}")
    else:
        logger.warning(f"❌ Aucun résultat trouvé")
    
    return results

async def main():
    """Fonction principale de test."""
    # Création des clients
    jira_client = JiraSearchClient()
    zendesk_client = ZendeskSearchClient()
    confluence_client = ConfluenceSearchClient()
    
    question = "Problèmes techniques"
    client_name = "RONDOT"
    
    # Test de chaque client
    jira_results = await test_search_client(jira_client, question, client_name)
    zendesk_results = await test_search_client(zendesk_client, question, client_name)
    confluence_results = await test_search_client(confluence_client, question, client_name)
    
    # Vérifier les résultats combinés
    all_results = jira_results + zendesk_results + confluence_results
    
    if all_results:
        logger.info(f"✅ Total: {len(all_results)} résultats trouvés pour RONDOT")
        
        # Trier par score décroissant
        sorted_results = sorted(all_results, key=lambda x: x.get("score", 0), reverse=True)
        
        # Afficher les sources distinctes
        sources = set()
        for result in all_results:
            if "payload" in result:
                if "key" in result["payload"]:
                    sources.add("JIRA")
                elif "ticket_id" in result["payload"]:
                    sources.add("ZENDESK")
                elif "title" in result["payload"] and "space" in result["payload"]:
                    sources.add("CONFLUENCE")
        
        logger.info(f"Sources trouvées: {', '.join(sources)}")
    else:
        logger.error("❌ Aucun résultat global trouvé pour RONDOT!")

if __name__ == "__main__":
    asyncio.run(main())
