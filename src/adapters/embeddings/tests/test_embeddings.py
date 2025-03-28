"""
Tests pour les services d'embedding

Ce module contient les tests unitaires pour les services d'embedding,
validant la fonctionnalité et la performance.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
from typing import Dict, List, Any

# Ajouter le répertoire parent au chemin d'importation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

# Import des modules à tester - importés après l'ajout du chemin d'importation
from src.adapters.embeddings.base import EmbeddingService  # noqa: E402
from src.adapters.embeddings.openai_embedding import OpenAIEmbeddingService  # noqa: E402
from src.adapters.embeddings.factory import EmbeddingServiceFactory  # noqa: E402
from src.infrastructure.cache import IntelligentCache  # noqa: E402

class MockLLMAdapter:
    """Mock d'adaptateur LLM pour les tests"""
    
    def __init__(self):
        self.embed_called = 0
        self.texts = []
        self.models = []
        
    async def embed(self, text, model=None):
        """Génère un embedding mock"""
        self.embed_called += 1
        self.texts.append(text)
        self.models.append(model)
        
        # Générer un vecteur mock basé sur le hash du texte
        import hashlib
        hash_obj = hashlib.md5(text.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()
        
        # Générer un seed valide (entre 0 et 2**32 - 1)
        hash_int = int(hash_hex[:8], 16)  # Utiliser seulement les 8 premiers caractères hexadécimaux
        
        # Générer un vecteur déterministe
        np.random.seed(hash_int)
        dimensions = 1536 if model == "text-embedding-ada-002" else 768
        return np.random.random(dimensions).tolist()
        
    async def embed_batch(self, texts, model=None):
        """Génère des embeddings mock en batch"""
        result = []
        for text in texts:
            embedding = await self.embed(text, model)
            result.append(embedding)
        return result
        
class TestEmbeddingServices(unittest.IsolatedAsyncioTestCase):
    """Tests unitaires pour les services d'embedding"""
    
    async def asyncSetUp(self):
        """Configuration des tests"""
        self.mock_llm_adapter = MockLLMAdapter()
        
        # Créer un cache en mémoire pour les tests
        self.test_cache = IntelligentCache(
            max_entries=100,
            default_ttl=60,
            max_memory_mb=10
        )
        
        # Patch pour utiliser le cache de test
        self.original_get_cache = sys.modules['src.infrastructure.cache'].get_cache_instance
        sys.modules['src.infrastructure.cache'].get_cache_instance = lambda *args, **kwargs: self.test_cache
        
        # Démarrer la tâche de nettoyage du cache
        await self.test_cache.start_cleanup_task()
    
    async def asyncTearDown(self):
        """Nettoyage après les tests"""
        # Restaurer la fonction originale
        sys.modules['src.infrastructure.cache'].get_cache_instance = self.original_get_cache
    
    async def test_openai_embedding_service_initialization(self):
        """Test de l'initialisation du service d'embedding OpenAI"""
        
        service = OpenAIEmbeddingService(
            llm_adapter=self.mock_llm_adapter,
            model="text-embedding-ada-002",
            batch_size=10,
            cache_embeddings=True
        )
        
        self.assertEqual(service.model, "text-embedding-ada-002")
        self.assertEqual(service.batch_size, 10)
        self.assertEqual(service.provider_name, "openai")
        self.assertEqual(service.dimensions, 1536)
    
    async def test_embedding_generation(self):
        """Test de la génération d'embeddings"""
        
        service = OpenAIEmbeddingService(
            llm_adapter=self.mock_llm_adapter,
            model="text-embedding-ada-002",
            cache_embeddings=True
        )
        
        # Générer un embedding
        embedding = await service.get_embedding("Test d'embedding")
        
        # Vérifier le résultat
        self.assertIsInstance(embedding, list)
        self.assertEqual(len(embedding), 1536)
        
        # Vérifier que l'adaptateur LLM a été appelé
        self.assertEqual(self.mock_llm_adapter.embed_called, 1)
        self.assertEqual(self.mock_llm_adapter.texts[0], "Test d'embedding")
        self.assertEqual(self.mock_llm_adapter.models[0], "text-embedding-ada-002")
    
    async def test_embedding_caching(self):
        """Test du cache des embeddings"""
        
        service = OpenAIEmbeddingService(
            llm_adapter=self.mock_llm_adapter,
            model="text-embedding-ada-002",
            cache_embeddings=True
        )
        
        # Générer le même embedding plusieurs fois
        text = "Test de cache d'embedding"
        
        # Première génération (devrait utiliser l'adaptateur LLM)
        embedding1 = await service.get_embedding(text)
        
        # Deuxième génération (devrait utiliser le cache)
        embedding2 = await service.get_embedding(text)
        
        # Troisième génération (devrait utiliser le cache)
        embedding3 = await service.get_embedding(text)
        
        # Vérifier que l'adaptateur LLM n'a été appelé qu'une seule fois
        self.assertEqual(self.mock_llm_adapter.embed_called, 1)
        
        # Vérifier que tous les embeddings sont identiques
        self.assertEqual(embedding1, embedding2)
        self.assertEqual(embedding1, embedding3)
    
    async def test_batch_embedding(self):
        """Test de la génération d'embeddings en batch"""
        
        service = OpenAIEmbeddingService(
            llm_adapter=self.mock_llm_adapter,
            model="text-embedding-ada-002",
            cache_embeddings=True,
            batch_size=3  # Petit batch pour tester plusieurs appels
        )
        
        # Préparer une liste de textes
        texts = [
            "Premier texte pour test batch",
            "Deuxième texte pour test batch",
            "Troisième texte pour test batch",
            "Quatrième texte pour test batch",
            "Cinquième texte pour test batch"
        ]
        
        # Générer les embeddings en batch
        embeddings = await service.get_embeddings(texts)
        
        # Vérifier le résultat
        self.assertEqual(len(embeddings), len(texts))
        for embedding in embeddings:
            self.assertEqual(len(embedding), 1536)
        
        # Vérifier que tous les textes ont été traités
        self.assertEqual(self.mock_llm_adapter.embed_called, 5)
        
        # Générer à nouveau (devrait utiliser le cache)
        embeddings2 = await service.get_embeddings(texts)
        
        # Vérifier que l'adaptateur LLM n'a pas été appelé davantage
        self.assertEqual(self.mock_llm_adapter.embed_called, 5)
        
        # Vérifier que les résultats sont identiques
        for i in range(len(texts)):
            self.assertEqual(embeddings[i], embeddings2[i])
    
    async def test_similarity_calculation(self):
        """Test du calcul de similarité entre textes"""
        
        service = OpenAIEmbeddingService(
            llm_adapter=self.mock_llm_adapter,
            model="text-embedding-ada-002",
            cache_embeddings=True
        )
        
        # Textes similaires
        text1 = "Comment résoudre un problème de connexion à NetSuite?"
        text2 = "Problème de connexion NetSuite, quelle est la solution?"
        
        # Textes différents
        text3 = "Comment créer un ticket Jira pour un bug?"
        
        # Calculer les similarités
        sim1_2 = await service.similarity(text1, text2)
        sim1_3 = await service.similarity(text1, text3)
        
        # Un texte avec lui-même doit avoir une similarité de 1.0
        sim1_1 = await service.similarity(text1, text1)
        
        # Vérifier les résultats
        self.assertGreaterEqual(sim1_2, 0.0)
        self.assertLessEqual(sim1_2, 1.0)
        self.assertGreaterEqual(sim1_3, 0.0)
        self.assertLessEqual(sim1_3, 1.0)
        self.assertEqual(sim1_1, 1.0)
        
        # Vérifier que la similarité entre textes similaires est plus élevée
        # que celle entre textes différents
        # Note: Ce test peut échouer avec des embeddings mock aléatoires
        # mais devrait passer avec de vrais embeddings
        # self.assertGreater(sim1_2, sim1_3)
    
    async def test_ranking_by_similarity(self):
        """Test du classement par similarité"""
        
        service = OpenAIEmbeddingService(
            llm_adapter=self.mock_llm_adapter,
            model="text-embedding-ada-002",
            cache_embeddings=True
        )
        
        # Requête
        query = "Problème de connexion NetSuite"
        
        # Liste de textes à classer
        texts = [
            "Comment résoudre un problème de connexion à NetSuite?",
            "Guide de dépannage pour les erreurs de connexion NetSuite",
            "Documentation API NetSuite pour développeurs",
            "Comment créer un ticket Zendesk pour support?",
            "Procédure de création de compte SAP"
        ]
        
        # Classer par similarité
        ranked = await service.rank_by_similarity(query, texts)
        
        # Vérifier le format des résultats
        self.assertEqual(len(ranked), len(texts))
        self.assertIn("text", ranked[0])
        self.assertIn("score", ranked[0])
        self.assertIn("index", ranked[0])
        
        # Vérifier que les scores sont triés par ordre décroissant
        for i in range(len(ranked) - 1):
            self.assertGreaterEqual(ranked[i]["score"], ranked[i+1]["score"])
    
    async def test_factory_creation(self):
        """Test de la création de service via la factory"""
        
        # Création avec LLM adapter explicite
        service1 = EmbeddingServiceFactory.create_service(
            provider="openai",
            llm_adapter=self.mock_llm_adapter,
            model="text-embedding-ada-002"
        )
        
        self.assertIsInstance(service1, OpenAIEmbeddingService)
        self.assertEqual(service1.model, "text-embedding-ada-002")
        
        # Test avec provider invalide
        with self.assertRaises(ValueError):
            EmbeddingServiceFactory.create_service(provider="invalid_provider")
        
        # Vérifier les providers disponibles
        providers = EmbeddingServiceFactory.list_providers()
        self.assertIn("openai", providers)

def run_tests():
    """Exécute les tests avec un rapport détaillé"""
    unittest.main(verbosity=2)

if __name__ == "__main__":
    run_tests()
