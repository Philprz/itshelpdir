"""
Tests pour les adaptateurs de bases de données vectorielles

Ce module contient les tests unitaires pour les adaptateurs vectoriels,
avec des mocks pour Qdrant et d'autres systèmes.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

# Ajouter le répertoire parent au chemin d'importation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

# Imports après ajustement du path
from src.adapters.vector_stores.qdrant_adapter import QdrantAdapter  # noqa: E402

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
        
        # Générer un vecteur mock basé sur le hash du texte
        import hashlib
        import numpy as np
        
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
        if model and 'small' in str(model).lower():
            dimensions = 768
            
        return np.random.random(dimensions).tolist()

# Mock Qdrant pour les tests
class MockQdrantClient:
    """Mock de client Qdrant pour les tests"""
    
    def __init__(self, url=None, api_key=None, timeout=None):
        """Initialise le mock Qdrant"""
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.collections = {}
        self.points = {}
        
        # Créer une collection de test
        self.create_test_collection()
    
    def create_test_collection(self):
        """Crée une collection de test avec des données"""
        # Structure de collection
        test_collection = {
            "name": "test_collection",
            "vectors_count": 100,
            "status": "green",
            "config": MagicMock(
                params=MagicMock(
                    vectors=MagicMock(
                        size=1536,
                        distance="cosine",
                        hnsw_config=MagicMock(
                            m=16,
                            ef_construct=100
                        )
                    )
                )
            )
        }
        
        # Ajouter aux collections
        self.collections["test_collection"] = test_collection
        self.points["test_collection"] = {}
        
        # Ajouter quelques points de test
        for i in range(5):
            point_id = f"test_point_{i}"
            vector = np.random.random(1536).tolist()
            payload = {
                "text": f"Test document {i}",
                "source": "test",
                "metadata": {
                    "importance": i % 3,
                    "category": "test" if i % 2 == 0 else "example"
                }
            }
            
            # Stocker le point
            self.points["test_collection"][point_id] = {
                "id": point_id,
                "vector": vector,
                "payload": payload
            }
    
    def search(self, collection_name, query_vector, limit=10, query_filter=None, with_payload=True, with_vectors=False, score_threshold=None):
        """Simule une recherche dans Qdrant"""
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        results = []
        
        # Calculer les scores (simulés)
        for point_id, point_data in self.points.get(collection_name, {}).items():
            # Calculer un score fictif (plus élevé pour les premiers points)
            score = 1.0 - (0.1 * int(point_id.split("_")[-1]))
            
            # Appliquer le seuil de score
            if score_threshold is not None and score < score_threshold:
                continue
            
            # Créer un résultat
            result = MagicMock(
                id=point_id,
                score=score
            )
            
            # Ajouter le payload si demandé
            if with_payload:
                result.payload = point_data["payload"]
            
            # Ajouter le vecteur si demandé
            if with_vectors:
                result.vector = point_data["vector"]
            
            results.append(result)
        
        # Trier par score et limiter
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    def retrieve(self, collection_name, ids, with_vectors=False):
        """Simule une récupération par ID dans Qdrant"""
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        results = []
        
        for point_id in ids:
            point_data = self.points.get(collection_name, {}).get(point_id)
            
            if point_data:
                # Créer un résultat
                result = MagicMock(
                    id=point_id
                )
                
                # Ajouter le payload
                result.payload = point_data["payload"]
                
                # Ajouter le vecteur si demandé
                if with_vectors:
                    result.vector = point_data["vector"]
                
                results.append(result)
        
        return results
    
    def upsert(self, collection_name, points):
        """Simule une insertion dans Qdrant"""
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        for point in points:
            self.points.setdefault(collection_name, {})[point.id] = {
                "id": point.id,
                "vector": point.vector,
                "payload": point.payload
            }
    
    def delete(self, collection_name, points_selector):
        """Simule une suppression dans Qdrant"""
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        for point_id in points_selector:
            if point_id in self.points.get(collection_name, {}):
                del self.points[collection_name][point_id]
    
    def get_collections(self):
        """Simule la récupération des collections Qdrant"""
        result = MagicMock()
        result.collections = [
            MagicMock(name=name) for name in self.collections.keys()
        ]
        return result
    
    def get_collection(self, collection_name):
        """Simule la récupération des informations sur une collection"""
        if collection_name not in self.collections:
            raise ValueError(f"Collection {collection_name} not found")
        
        return MagicMock(**self.collections[collection_name])

class TestVectorStoreAdapters(unittest.IsolatedAsyncioTestCase):
    """Tests unitaires pour les adaptateurs de bases vectorielles"""
    
    async def asyncSetUp(self):
        """Configuration des tests"""
        # Créer un service d'embedding mock
        self.mock_embedding_service = MockEmbeddingService()
        
        # Créer un patch pour le client Qdrant
        # Nous utilisons cette forme plus spécifique qui garantit que le module est
        # importé correctement avant d'être patché
        mock_qdrant = MagicMock()
        mock_qdrant.QdrantClient = MockQdrantClient
        self.qdrant_patcher = patch.dict('sys.modules', {'qdrant_client': mock_qdrant})
        self.qdrant_patcher.start()
        
        # Créer un mock pour asyncio.to_thread pour éviter les appels réels
        self.thread_patcher = patch('asyncio.to_thread', new=self.mock_to_thread)
        self.thread_patcher.start()
    
    async def mock_to_thread(self, func, *args, **kwargs):
        """Mock de to_thread qui exécute la fonction directement"""
        return func(*args, **kwargs)
    
    async def asyncTearDown(self):
        """Nettoyage après les tests"""
        self.qdrant_patcher.stop()
        self.thread_patcher.stop()
    
    async def test_qdrant_adapter_initialization(self):
        """Test de l'initialisation de l'adaptateur Qdrant"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://localhost:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Vérifier les attributs
        self.assertEqual(adapter.qdrant_url, "http://localhost:6333")
        self.assertEqual(adapter.provider_name, "qdrant")
        
        # Vérifier que le client n'est pas encore initialisé
        self.assertIsNone(adapter._client)
    
    async def test_qdrant_search(self):
        """Test de la recherche par vecteur dans Qdrant"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Créer un vecteur de test
        test_vector = [0.1, 0.2, 0.3] * 100
        
        # Effectuer une recherche
        results = await adapter.search(
            query_vector=test_vector,
            collection_name="test_collection",
            limit=3,
            score_threshold=0.7
        )
        
        # Vérifier les résultats
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        self.assertIn("id", results[0])
        self.assertIn("score", results[0])
        self.assertIn("payload", results[0])
    
    async def test_qdrant_search_by_text(self):
        """Test de la recherche par texte dans Qdrant"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Effectuer une recherche par texte
        results = await adapter.search_by_text(
            query_text="test document",
            collection_name="test_collection",
            limit=3
        )
        
        # Vérifier que le service d'embedding a été appelé
        self.assertEqual(self.mock_embedding_service.embed_called, 1)
        
        # Vérifier les résultats
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        self.assertIn("id", results[0])
        self.assertIn("score", results[0])
        self.assertIn("payload", results[0])
    
    async def test_qdrant_get_by_id(self):
        """Test de la récupération par ID dans Qdrant"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Récupérer par ID
        result = await adapter.get_by_id(
            id="test_point_1",
            collection_name="test_collection"
        )
        
        # Vérifier le résultat
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "test_point_1")
        self.assertIn("payload", result)
        self.assertIn("text", result["payload"])
    
    async def test_qdrant_upsert(self):
        """Test de l'insertion/mise à jour dans Qdrant"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Préparer les données
        test_id = "test_new_point"
        test_vector = [0.1, 0.2, 0.3] * 100
        test_payload = {
            "text": "Document test",
            "source": "test",
            "metadata": {"category": "test"}
        }
        
        # Insérer/mettre à jour
        success = await adapter.upsert(
            id=test_id,
            vector=test_vector,
            payload=test_payload,
            collection_name="test_collection"
        )
        
        # Vérifier le résultat
        self.assertTrue(success)
        
        # Récupérer pour confirmer l'insertion
        result = await adapter.get_by_id(
            id=test_id,
            collection_name="test_collection"
        )
        
        # Vérifier l'insertion
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], test_id)
    
    async def test_qdrant_upsert_by_text(self):
        """Test de l'insertion à partir d'un texte"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Données de test
        test_id = "test_text_point"
        test_text = "Ceci est un document test pour embedding"
        test_payload = {"source": "test", "category": "example"}
        
        # Insérer avec génération d'embedding
        success = await adapter.upsert_text(
            id=test_id,
            text=test_text,
            payload=test_payload,
            collection_name="test_collection"
        )
        
        # Vérifier que le service d'embedding a été appelé
        self.assertEqual(self.mock_embedding_service.embed_called, 1)
        self.assertEqual(self.mock_embedding_service.texts[0], test_text)
        
        # Vérifier le résultat
        self.assertTrue(success)
    
    async def test_qdrant_delete(self):
        """Test de la suppression dans Qdrant"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Supprimer un élément existant
        success = await adapter.delete(
            id="test_point_0",
            collection_name="test_collection"
        )
        
        # Vérifier le succès
        self.assertTrue(success)
        
        # Vérifier que l'élément a été supprimé
        result = await adapter.get_by_id(
            id="test_point_0",
            collection_name="test_collection"
        )
        self.assertIsNone(result)
    
    async def test_qdrant_list_collections(self):
        """Test de la liste des collections Qdrant"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Récupérer la liste des collections
        collections = await adapter.list_collections()
        
        # Vérifier qu'il y a au moins une collection (la collection de test)
        self.assertIsInstance(collections, list)
        self.assertIn("test_collection", collections)
    
    async def test_qdrant_collection_info(self):
        """Test de la récupération des informations sur une collection"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Récupérer les informations
        info = await adapter.get_collection_info("test_collection")
        
        # Vérifier les informations
        self.assertIsInstance(info, dict)
        self.assertIn("vectors_count", info)
        self.assertIn("status", info)
    
    async def test_qdrant_health_check(self):
        """Test du contrôle de santé Qdrant"""
        
        # Initialiser l'adaptateur
        adapter = QdrantAdapter(
            qdrant_url="http://test:6333",
            embedding_service=self.mock_embedding_service
        )
        
        # Effectuer un contrôle de santé
        status = await adapter.health_check()
        
        # Vérifier le statut
        self.assertIsInstance(status, dict)
        self.assertIn("status", status)
        self.assertEqual(status["status"], "ok")
    
    async def test_factory_creation(self):
        """Test de la création d'adaptateur via la factory"""
        from src.adapters.vector_stores.factory import VectorStoreFactory
        
        # Créer un adaptateur via la factory
        adapter = VectorStoreFactory.create_adapter(
            provider="qdrant",
            embedding_service=self.mock_embedding_service
        )
        
        # Vérifier le type et les attributs
        self.assertIsInstance(adapter, QdrantAdapter)
        self.assertEqual(adapter.provider_name, "qdrant")
        
        # Vérifier la détection automatique
        with patch.dict(os.environ, {"QDRANT_URL": "http://env:6333"}):
            auto_adapter = VectorStoreFactory.create_adapter(
                provider="auto",
                embedding_service=self.mock_embedding_service
            )
            self.assertIsInstance(auto_adapter, QdrantAdapter)
            self.assertEqual(auto_adapter.qdrant_url, "http://env:6333")
        
        # Vérifier le cas d'erreur
        with self.assertRaises(ValueError):
            VectorStoreFactory.create_adapter(provider="invalid_provider")
        
        # Vérifier les providers disponibles
        providers = VectorStoreFactory.list_providers()
        self.assertIn("qdrant", providers)

def run_tests():
    """Exécute les tests avec un rapport détaillé"""
    unittest.main(verbosity=2)

if __name__ == "__main__":
    run_tests()
