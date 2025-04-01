"""
Test de validation pour la correction de sérialisation JSON dans le service d'embedding.
"""

import asyncio
import logging
import sys
import json

# Import des composants à tester
from embedding_service_compat import EmbeddingService
from src.infrastructure.cache_compat import GlobalCache

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_serialization_fix')

async def test_embedding_service_with_global_cache():
    """Test de l'EmbeddingService avec GlobalCache pour vérifier la sérialisation."""
    logger.info("Initialisation du test avec GlobalCache")
    
    # Initialiser un cache
    cache = GlobalCache(max_size=10, ttl=60)
    
    # Créer un service d'embedding avec mock
    class MockOpenAI:
        """Mock pour simuler le client OpenAI."""
        def __init__(self):
            self.embeddings = self.EmbeddingsAPI()
            
        class EmbeddingsAPI:
            """API d'embeddings simulée."""
            async def create(self, model, input):
                """Simuler la création d'embeddings."""
                class MockResponse:
                    def __init__(self):
                        self.data = [type('obj', (object,), {'embedding': [0.1, 0.2, 0.3]})]
                return MockResponse()
    
    mock_client = MockOpenAI()
    
    # Initialiser le service avec le cache
    embedding_service = EmbeddingService(
        openai_client=mock_client,
        cache=cache,
        model="test-model"
    )
    
    try:
        # Tester la génération d'embedding
        logger.info("Test de génération d'embedding")
        embedding = await embedding_service.get_embedding("Test text")
        
        # Vérifier le résultat
        if isinstance(embedding, list):
            logger.info("✅ Succès: embedding est une liste de {} éléments".format(len(embedding)))
        else:
            logger.error("❌ Échec: embedding n'est pas une liste mais {}".format(type(embedding)))
            return False
            
        # Tester la sérialisation du service
        logger.info("Test de sérialisation du service")
        service_dict = embedding_service.to_json()
        json_str = json.dumps(service_dict)
        logger.info("✅ Sérialisation du service réussie: {}...".format(json_str[:50]))
        
        # Tester la récupération depuis le cache
        logger.info("Test de récupération depuis le cache")
        embedding_from_cache = await embedding_service.get_embedding("Test text")
        
        if isinstance(embedding_from_cache, list):
            logger.info("✅ Succès: embedding depuis le cache est une liste")
        else:
            logger.error("❌ Échec: embedding depuis le cache n'est pas une liste")
            return False
            
        return True
    except Exception as e:
        logger.error("❌ Exception lors du test: {}".format(str(e)))
        import traceback
        traceback.print_exc()
        return False

async def test_search_client_serialization():
    """Test de sérialisation des clients de recherche."""
    logger.info("Initialisation du test des clients de recherche")
    
    from search_clients import AbstractSearchClient
    
    # Créer une instance de base
    client = AbstractSearchClient(
        collection_name="test_collection",
        client=None,
        embedding_service=None
    )
    
    try:
        # Tester la sérialisation directe
        logger.info("Test de la méthode to_json")
        client_dict = client.to_json()
        json_str = json.dumps(client_dict)
        logger.info("✅ Sérialisation du client réussie: {}".format(json_str))
        
        # Tester __getstate__
        logger.info("Test de __getstate__")
        state = client.__getstate__()
        json_str = json.dumps(state)
        logger.info("✅ Sérialisation de l'état réussie: {}".format(json_str))
        
        return True
    except Exception as e:
        logger.error("❌ Exception lors du test de sérialisation: {}".format(str(e)))
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Fonction principale pour exécuter tous les tests."""
    logger.info("=== Début des tests de validation pour fix sérialisation JSON ===")
    
    # Test 1: EmbeddingService avec GlobalCache
    logger.info("Test 1: EmbeddingService avec GlobalCache")
    test1_result = await test_embedding_service_with_global_cache()
    logger.info("Test 1: {}".format('✅ SUCCÈS' if test1_result else '❌ ÉCHEC'))
    
    # Test 2: Sérialisation des clients de recherche
    logger.info("Test 2: Sérialisation des clients de recherche")
    test2_result = await test_search_client_serialization()
    logger.info("Test 2: {}".format('✅ SUCCÈS' if test2_result else '❌ ÉCHEC'))
    
    # Résultat global
    if test1_result and test2_result:
        logger.info("✅✅✅ TOUS LES TESTS ONT RÉUSSI")
        return 0
    else:
        logger.error("❌❌❌ CERTAINS TESTS ONT ÉCHOUÉ")
        return 1

if __name__ == "__main__":
    # Exécuter le test asynchrone
    loop = asyncio.get_event_loop()
    exit_code = loop.run_until_complete(main())
    sys.exit(exit_code)
