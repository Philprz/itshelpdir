"""
Tests simplifiés pour les adaptateurs de bases de données vectorielles

Ce module contient des tests unitaires simplifiés pour les adaptateurs vectoriels,
avec des mocks pour Qdrant.
"""

import sys
import logging
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import hashlib

# Importer les modules à tester
from src.adapters.vector_stores.qdrant_adapter import QdrantAdapter

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vector_store_tests")

# Mock du service d'embedding
class MockEmbeddingService:
    """Mock de service d'embedding pour les tests"""
    
    def __init__(self):
        self.embed_called = 0
        self.texts = []
        self.models = []
    
    async def get_embedding(self, text, model=None):
        """Génère un embedding mock"""
        self.embed_called += 1
        self.texts.append(text)
        self.models.append(model)
        
        # Nettoyer le texte et hash
        clean_text = str(text).lower().strip()
        hash_obj = hashlib.md5(clean_text.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()
        
        # Utiliser seulement les 8 premiers caractères pour un seed valide
        hash_int = int(hash_hex[:8], 16) % (2**32 - 1)
        
        # Générer un vecteur déterministe
        np.random.seed(hash_int)
        
        # Différentes dimensions selon le modèle
        dimensions = 1536  # Défaut comme OpenAI ada-002
        return np.random.random(dimensions).tolist()

# Mock du client Qdrant
class MockQdrantClient:
    """Version simplifiée du mock de client Qdrant pour les tests"""
    
    def __init__(self, url=None, api_key=None, timeout=None):
        """Initialise le mock Qdrant"""
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.collections = {"test_collection": {"name": "test_collection"}}
        self.points = {"test_collection": {}}
        
        # Ajouter quelques points de test
        for i in range(5):
            point_id = f"test_point_{i}"
            vector = np.random.random(1536).tolist()
            payload = {
                "text": f"Test document {i}",
                "source": "test"
            }
            
            # Stocker le point
            self.points["test_collection"][point_id] = {
                "id": point_id,
                "vector": vector,
                "payload": payload
            }
    
    def search(self, collection_name, query_vector, limit=10, query_filter=None, with_payload=True, with_vectors=False, score_threshold=None):
        """Simule une recherche dans Qdrant"""
        results = []
        for i, (point_id, point) in enumerate(self.points.get(collection_name, {}).items()):
            if i >= limit:
                break
            results.append({
                "id": point_id,
                "score": 0.9 - (i * 0.1),
                "payload": point["payload"] if with_payload else None,
                "vector": point["vector"] if with_vectors else None
            })
        return results
    
    def retrieve(self, collection_name, ids, with_vectors=False):
        """Simule une récupération par ID dans Qdrant"""
        results = []
        for id in ids:
            point = self.points.get(collection_name, {}).get(id)
            if point:
                results.append({
                    "id": id,
                    "payload": point["payload"],
                    "vector": point["vector"] if with_vectors else None
                })
        return results
    
    def upsert(self, collection_name, points):
        """Simule une insertion/mise à jour dans Qdrant"""
        for point in points:
            self.points.setdefault(collection_name, {})[point.id] = {
                "id": point.id,
                "vector": point.vector,
                "payload": point.payload
            }
        return True
    
    def delete(self, collection_name, points_selector):
        """Simule une suppression dans Qdrant"""
        if hasattr(points_selector, 'points'):
            ids = points_selector.points
            for id in ids:
                if id in self.points.get(collection_name, {}):
                    del self.points[collection_name][id]
        return True
    
    def get_collections(self):
        """Simule la récupération des collections Qdrant"""
        return [{"name": name} for name in self.collections.keys()]
    
    def get_collection(self, collection_name):
        """Simule la récupération des informations sur une collection"""
        if collection_name in self.collections:
            return {
                "name": collection_name,
                "vectors_count": len(self.points.get(collection_name, {})),
                "status": "green"
            }
        return None


class TestVectorStoreBasics(unittest.IsolatedAsyncioTestCase):
    """Tests simplifiés pour les adaptateurs vectoriels"""
    
    async def asyncSetUp(self):
        """Configuration des tests"""
        # Créer un service d'embedding mock
        self.mock_embedding_service = MockEmbeddingService()
        
        # Définir les mocks pour qdrant_client
        self.module_patcher = patch.dict('sys.modules', {
            'qdrant_client': MagicMock(),
            'qdrant_client.http': MagicMock(),
            'qdrant_client.http.models': MagicMock(),
            'qdrant_client.models': MagicMock()
        })
        self.module_patcher.start()
        
        # Patcher directement la classe QdrantClient
        self.client_patcher = patch('qdrant_client.QdrantClient', MockQdrantClient)
        self.mock_qdrant = self.client_patcher.start()
        
        # Patcher asyncio.to_thread pour qu'il exécute la fonction directement
        self.thread_patcher = patch('asyncio.to_thread', new=self._mock_to_thread)
        self.thread_patcher.start()
    
    async def _mock_to_thread(self, func, *args, **kwargs):
        """Mock pour asyncio.to_thread qui exécute la fonction synchrone directement"""
        return func(*args, **kwargs)
    
    async def asyncTearDown(self):
        """Nettoyage après les tests"""
        self.thread_patcher.stop()
        self.client_patcher.stop()
        self.module_patcher.stop()
    
    async def test_initialization(self):
        """Test l'initialisation de l'adaptateur"""
        # Créer l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Vérifier les attributs de base
        self.assertEqual(adapter.qdrant_url, "http://test:6333")
        self.assertEqual(adapter.provider_name, "qdrant")
        self.assertIsNotNone(adapter.embedding_service)
    
    async def test_basic_operations(self):
        """Test des opérations de base"""
        # Créer l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # 1. Vérifier la liste des collections
        collections = await adapter.list_collections()
        self.assertIsInstance(collections, list)
        self.assertIn("test_collection", collections)
        
        # 2. Recherche par texte
        results = await adapter.search_by_text(
            query_text="test query",
            collection_name="test_collection",
            limit=2
        )
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 2)
        
        # Vérifier que la méthode d'embedding a été appelée
        self.assertEqual(self.mock_embedding_service.embed_called, 1)
        
        # 3. Insertion d'un nouveau document
        success = await adapter.upsert_text(
            id="test_new_doc",
            text="This is a test document",
            payload={"source": "test", "category": "example"},
            collection_name="test_collection"
        )
        self.assertTrue(success)
        
        # 4. Opérations de santé
        health = await adapter.health_check()
        self.assertIsInstance(health, dict)
        self.assertIn("status", health)


def run_tests():
    """Exécute les tests avec un rapport détaillé"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestVectorStoreBasics)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Afficher un résumé
    print("\n" + "=" * 80)
    print(f"RÉSUMÉ: {result.testsRun} tests exécutés, {result.errors} erreurs, {result.failures} échecs")
    print("=" * 80)
    
    # Retourner 0 si succès, 1 sinon (pour les scripts)
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(run_tests())
