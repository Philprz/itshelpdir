"""
Tests pour les adaptateurs LLM

Ce module contient les tests unitaires pour les adaptateurs LLM,
validant la fonctionnalité et la cohérence de l'interface.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any

# Ajouter le répertoire parent au chemin d'importation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

# Import des modules à tester
from src.adapters.llm.base import LLMAdapter, LLMMessage, LLMResponse, LLMConfig
from src.adapters.llm.openai_adapter import OpenAIAdapter
from src.adapters.llm.anthropic_adapter import AnthropicAdapter
from src.adapters.llm.factory import LLMAdapterFactory

class MockResponse:
    """Classe de réponse mock pour simuler les réponses d'API"""
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class TestLLMAdapters(unittest.IsolatedAsyncioTestCase):
    """Tests unitaires pour les adaptateurs LLM"""
    
    async def test_openai_adapter_initialization(self):
        """Test de l'initialisation de l'adaptateur OpenAI"""
        
        # Test avec clé API explicite
        adapter = OpenAIAdapter(api_key="test_key", default_model="gpt-3.5-turbo")
        self.assertEqual(adapter.api_key, "test_key")
        self.assertEqual(adapter.default_model, "gpt-3.5-turbo")
        self.assertEqual(adapter.provider_name, "openai")
        
        # Vérifier que les modèles disponibles sont définis
        self.assertIsInstance(adapter.available_models, list)
        self.assertGreater(len(adapter.available_models), 0)
    
    @patch('openai.AsyncOpenAI')
    async def test_openai_complete(self, mock_openai):
        """Test de la méthode complete de l'adaptateur OpenAI"""
        
        # Configurer le mock
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        
        # Configurer la réponse mock
        mock_response = MagicMock()
        mock_response.model = "gpt-3.5-turbo"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        
        # Configurer le client mock pour retourner la réponse mock
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        # Créer l'adaptateur et appeler complete
        adapter = OpenAIAdapter(api_key="test_key")
        messages = [LLMMessage(role="user", content="Test message")]
        response = await adapter.complete(messages)
        
        # Vérifier que le client a été appelé correctement
        mock_client.chat.completions.create.assert_called_once()
        
        # Vérifier la réponse
        self.assertEqual(response.content, "Test response")
        self.assertEqual(response.model, "gpt-3.5-turbo")
        self.assertEqual(response.usage["total_tokens"], 30)
        self.assertEqual(response.finish_reason, "stop")
    
    @patch('openai.AsyncOpenAI')
    async def test_openai_embed(self, mock_openai):
        """Test de la méthode embed de l'adaptateur OpenAI"""
        
        # Configurer le mock
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        
        # Configurer la réponse mock
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1, 0.2, 0.3]
        
        # Configurer le client mock pour retourner la réponse mock
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        
        # Créer l'adaptateur et appeler embed
        adapter = OpenAIAdapter(api_key="test_key")
        embedding = await adapter.embed("Test text")
        
        # Vérifier que le client a été appelé correctement
        mock_client.embeddings.create.assert_called_once()
        
        # Vérifier l'embedding
        self.assertEqual(embedding, [0.1, 0.2, 0.3])
    
    async def test_anthropic_adapter_initialization(self):
        """Test de l'initialisation de l'adaptateur Anthropic"""
        
        # Test avec clé API explicite
        adapter = AnthropicAdapter(api_key="test_key", default_model="claude-3-sonnet-20240229")
        self.assertEqual(adapter.api_key, "test_key")
        self.assertEqual(adapter.default_model, "claude-3-sonnet-20240229")
        self.assertEqual(adapter.provider_name, "anthropic")
        
        # Vérifier que les modèles disponibles sont définis
        self.assertIsInstance(adapter.available_models, list)
        self.assertGreater(len(adapter.available_models), 0)
    
    @patch('anthropic.AsyncAnthropic')
    async def test_anthropic_complete(self, mock_anthropic):
        """Test de la méthode complete de l'adaptateur Anthropic"""
        
        # Configurer le mock
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        
        # Configurer la réponse mock
        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 20
        
        mock_content = MagicMock()
        mock_content.text = "Test response"
        
        mock_response = MagicMock()
        mock_response.model = "claude-3-sonnet-20240229"
        mock_response.usage = mock_usage
        mock_response.stop_reason = "stop"
        mock_response.content = [mock_content]
        
        # Configurer le client mock pour retourner la réponse mock
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        
        # Créer l'adaptateur et appeler complete
        adapter = AnthropicAdapter(api_key="test_key")
        messages = [LLMMessage(role="user", content="Test message")]
        response = await adapter.complete(messages)
        
        # Vérifier que le client a été appelé correctement
        mock_client.messages.create.assert_called_once()
        
        # Vérifier la réponse
        self.assertEqual(response.content, "Test response")
        self.assertEqual(response.model, "claude-3-sonnet-20240229")
        self.assertEqual(response.usage["total_tokens"], 30)
        self.assertEqual(response.finish_reason, "stop")
    
    async def test_anthropic_embed_not_supported(self):
        """Test que la méthode embed de l'adaptateur Anthropic lève une exception"""
        
        adapter = AnthropicAdapter(api_key="test_key")
        
        # Vérifier que l'appel à embed lève une exception NotImplementedError
        with self.assertRaises(NotImplementedError):
            await adapter.embed("Test text")
    
    async def test_llm_factory(self):
        """Test de la factory d'adaptateurs LLM"""
        
        # Test de création d'un adaptateur OpenAI
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            adapter = LLMAdapterFactory.create_adapter("openai")
            self.assertIsInstance(adapter, OpenAIAdapter)
            self.assertEqual(adapter.provider_name, "openai")
        
        # Test de création d'un adaptateur Anthropic
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test_key"}):
            adapter = LLMAdapterFactory.create_adapter("anthropic")
            self.assertIsInstance(adapter, AnthropicAdapter)
            self.assertEqual(adapter.provider_name, "anthropic")
        
        # Test d'autodetection du provider
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            adapter = LLMAdapterFactory.create_adapter("auto")
            self.assertIsInstance(adapter, OpenAIAdapter)
        
        # Test de provider invalide
        with self.assertRaises(ValueError):
            LLMAdapterFactory.create_adapter("invalid_provider")
        
        # Test des providers disponibles
        providers = LLMAdapterFactory.list_providers()
        self.assertIn("openai", providers)
        self.assertIn("anthropic", providers)

def run_tests():
    """Exécute les tests avec un rapport détaillé"""
    unittest.main(verbosity=2)

if __name__ == "__main__":
    run_tests()
