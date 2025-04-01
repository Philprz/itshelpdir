"""
Test simplifié pour valider la correction de l'erreur de sérialisation JSON
"""

import json
import asyncio
import logging
from embedding_service_compat import SafeCacheProxy, JSONSerializableEncoder
from search_clients import AbstractSearchClient

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_safe_cache_proxy_serialization():
    """Test de sérialisation du SafeCacheProxy"""
    # Créer un mock cache simple
    class MockCache:
        async def get(self, key, namespace=None):
            return [0.1, 0.2, 0.3]
    
    # Créer un proxy sécurisé
    proxy = SafeCacheProxy(MockCache())
    
    # Tester la conversion en JSON
    proxy_dict = proxy.to_json()
    logger.info("Proxy to_json: {}".format(proxy_dict))
    
    # Tester la sérialisation JSON complète
    try:
        json_str = json.dumps({"proxy": proxy_dict})
        logger.info("Sérialisation JSON réussie: {}".format(json_str))
        return True
    except Exception as e:
        logger.error("Erreur de sérialisation: {}".format(e))
        return False

async def test_search_client_serialization():
    """Test de sérialisation du AbstractSearchClient"""
    # Créer un client de recherche
    client = AbstractSearchClient(
        collection_name="test",
        client=None,
        embedding_service=None
    )
    
    # Tester la conversion en JSON
    client_dict = client.to_json()
    logger.info("Client to_json: {}".format(client_dict))
    
    # Tester la sérialisation JSON complète
    try:
        json_str = json.dumps({"client": client_dict})
        logger.info("Sérialisation JSON réussie: {}".format(json_str))
        return True
    except Exception as e:
        logger.error("Erreur de sérialisation: {}".format(e))
        return False

async def test_combined_serialization():
    """Test de sérialisation avec SafeCacheProxy et AbstractSearchClient ensemble"""
    # Créer un proxy sécurisé
    proxy = SafeCacheProxy(None)
    
    # Créer un client de recherche qui utilise le proxy
    client = AbstractSearchClient(
        collection_name="test",
        client=None,
        embedding_service=None
    )
    
    # Simuler l'objet complet à sérialiser
    combined = {
        "proxy": proxy,
        "client": client
    }
    
    # Tester la sérialisation avec JSONSerializableEncoder
    try:
        json_str = json.dumps(combined, cls=JSONSerializableEncoder)
        logger.info("Sérialisation combinée réussie: {}".format(json_str))
        return True
    except Exception as e:
        logger.error("Erreur de sérialisation combinée: {}".format(e))
        return False

async def main():
    """Fonction principale pour exécuter les tests"""
    logger.info("=== TESTS DE SÉRIALISATION JSON ===")
    
    # Test 1: SafeCacheProxy
    logger.info("Test 1: SafeCacheProxy")
    test1 = await test_safe_cache_proxy_serialization()
    logger.info("Test 1: {}".format('SUCCÈS ✅' if test1 else 'ÉCHEC ❌'))
    
    # Test 2: AbstractSearchClient
    logger.info("Test 2: AbstractSearchClient")
    test2 = await test_search_client_serialization()
    logger.info("Test 2: {}".format('SUCCÈS ✅' if test2 else 'ÉCHEC ❌'))
    
    # Test 3: Combined
    logger.info("Test 3: Sérialisation combinée")
    test3 = await test_combined_serialization()
    logger.info("Test 3: {}".format('SUCCÈS ✅' if test3 else 'ÉCHEC ❌'))
    
    # Résultat final
    if test1 and test2 and test3:
        logger.info("TOUS LES TESTS ONT RÉUSSI ✅✅✅")
        return 0
    else:
        logger.error("CERTAINS TESTS ONT ÉCHOUÉ ❌")
        return 1

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(main())
    print("\nRésultat final: {}".format('SUCCÈS ✅' if result == 0 else 'ÉCHEC ❌'))
