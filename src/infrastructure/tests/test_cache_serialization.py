"""
Tests de robustesse pour la gestion des erreurs de sérialisation JSON dans le cache.

Ce module contient des tests spécifiquement conçus pour vérifier que les erreurs
de sérialisation JSON sont correctement gérées dans le système de cache.
"""

import unittest
import asyncio
import logging
import json
from unittest.mock import MagicMock, patch

from ..cache_compat import GlobalCache
from ..cache_decorators import safe_cache_operation, log_cache_operation

# Désactiver les logs pendant les tests
logging.disable(logging.CRITICAL)

class NonSerializableObject:
    """Objet volontairement non-sérialisable pour les tests."""
    def __init__(self, name):
        self.name = name
        self.complex_attribute = lambda x: x  # Fonction lambda non-sérialisable

class TestCacheSerialization(unittest.TestCase):
    """Tests pour vérifier la gestion correcte des erreurs de sérialisation."""

    def setUp(self):
        """Initialisation avant chaque test."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.cache = GlobalCache(max_size=10, ttl=60)

    def tearDown(self):
        """Nettoyage après chaque test."""
        self.loop.close()

    def test_to_dict_method(self):
        """Vérifie que la méthode to_dict retourne un dictionnaire sérialisable."""
        # Obtenir le dictionnaire de l'état du cache
        cache_dict = self.cache.to_dict()
        
        # Vérifier que c'est un dictionnaire
        self.assertIsInstance(cache_dict, dict)
        
        # Vérifier qu'il contient les clés attendues
        self.assertIn("type", cache_dict)
        self.assertIn("max_size", cache_dict)
        self.assertIn("ttl_seconds", cache_dict)
        
        # Vérifier qu'il est sérialisable en JSON
        try:
            json_str = json.dumps(cache_dict)
            self.assertIsInstance(json_str, str)
        except TypeError:
            self.fail("Le dictionnaire n'est pas sérialisable en JSON")

    def test_str_representation(self):
        """Vérifie que la représentation chaîne du cache est correcte."""
        # Obtenir la représentation chaîne
        cache_str = str(self.cache)
        
        # Vérifier qu'elle contient les informations importantes
        self.assertIn("GlobalCache", cache_str)
        self.assertIn(str(self.cache._max_size), cache_str)
        
        # Vérifier que repr fonctionne aussi
        cache_repr = repr(self.cache)
        self.assertEqual(cache_str, cache_repr)

    def test_safe_cache_operation_decorator(self):
        """Vérifie que le décorateur safe_cache_operation protège contre les erreurs de sérialisation."""
        
        # Définir une fonction qui génère une erreur de sérialisation
        @safe_cache_operation(fallback_value="fallback")
        def function_with_serialization_error():
            obj = NonSerializableObject("test")
            # Tenter de sérialiser un objet non-sérialisable
            return json.dumps(obj.__dict__)
        
        # La fonction devrait retourner la valeur de repli au lieu de lever une exception
        result = function_with_serialization_error()
        self.assertEqual(result, "fallback")
        
        # Tester avec une fonction asynchrone
        @safe_cache_operation(fallback_value="async_fallback")
        async def async_function_with_error():
            obj = NonSerializableObject("test")
            # Tenter de sérialiser un objet non-sérialisable
            return json.dumps(obj.__dict__)
        
        # Exécuter la fonction asynchrone
        result = self.loop.run_until_complete(async_function_with_error())
        self.assertEqual(result, "async_fallback")

    def test_log_cache_operation_decorator(self):
        """Vérifie que le décorateur log_cache_operation gère correctement les objets non-sérialisables."""
        
        # Simuler une fonction logger
        mock_logger = MagicMock()
        
        # Patch le logger utilisé par le décorateur
        with patch('src.infrastructure.cache_decorators.logger', mock_logger):
            
            # Définir une fonction qui prend un objet non-sérialisable en argument
            @log_cache_operation(log_level="info")
            def function_with_complex_arg(obj):
                return obj.name
            
            # Appeler la fonction avec un objet non-sérialisable
            obj = NonSerializableObject("test_name")
            result = function_with_complex_arg(obj)
            
            # Vérifier que la fonction a bien été appelée et a retourné le résultat attendu
            self.assertEqual(result, "test_name")
            
            # Vérifier que le logger a été appelé sans erreur
            mock_logger.info.assert_called()
            
            # Vérifier que le message de log ne contient pas l'objet complet
            log_message = mock_logger.info.call_args[0][0]
            self.assertIn("function_with_complex_arg", log_message)
            self.assertNotIn("complex_attribute", log_message)  # L'attribut lambda ne devrait pas être dans le log

    def test_serialization_in_embedding_service(self):
        """
        Test d'intégration simulant le comportement de l'EmbeddingService.
        
        Ce test simule le scénario où un service d'embedding tente d'utiliser
        un objet cache non-sérialisable.
        """
        try:
            # Importer le service d'embedding
            from embedding_service_compat import EmbeddingService
            
            # Créer un mock pour le client OpenAI
            mock_openai = MagicMock()
            mock_openai.embeddings.create = MagicMock()
            
            # Configurer le mock pour retourner un embedding factice
            mock_result = MagicMock()
            mock_result.data = [MagicMock()]
            mock_result.data[0].embedding = [0.1, 0.2, 0.3]
            mock_openai.embeddings.create.return_value = mock_result
            
            # Créer un service d'embedding avec notre cache
            embedding_service = EmbeddingService(
                openai_client=mock_openai,
                cache=self.cache
            )
            
            # Tester la génération d'embedding
            embedding = self.loop.run_until_complete(embedding_service.get_embedding("test text"))
            
            # Vérifier que nous obtenons un résultat valide
            self.assertIsInstance(embedding, list)
            self.assertEqual(len(embedding), 3)  # Notre mock retourne 3 valeurs
            
            # Forcer une erreur de sérialisation dans le cache
            with patch.object(self.cache, 'get', side_effect=TypeError("Object is not JSON serializable")):
                # Même avec l'erreur, le service devrait continuer à fonctionner
                embedding = self.loop.run_until_complete(embedding_service.get_embedding("test text"))
                
                # Le décorateur safe_cache_operation devrait assurer qu'on obtient un résultat valide
                self.assertIsInstance(embedding, list)
                
        except ImportError:
            # Si le service d'embedding n'est pas disponible, ignorer ce test
            self.skipTest("EmbeddingService non disponible pour le test")

if __name__ == '__main__':
    unittest.main()
