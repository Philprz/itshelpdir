# tests/test_chatbot.py
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from chatbot import ChatBot

@pytest.fixture
def chatbot():
    with patch('openai.AsyncOpenAI'), patch('qdrant_client.QdrantClient'):
        return ChatBot(
            openai_key="test_key",
            qdrant_url="http://test",
            qdrant_api_key="test_api_key"
        )

@pytest.mark.asyncio
async def test_analyze_question(chatbot):
    with patch.object(chatbot.openai_client.chat.completions, 'create') as mock_create:
        mock_create.return_value.choices[0].message.content = '{"type": "support", "search_context": {"has_client": true, "client_name": "TESTCLIENT"}}'
        result = await chatbot.analyze_question("Problème avec TESTCLIENT")
        assert result["type"] == "support"
        assert result["search_context"]["has_client"] is True
        assert result["search_context"]["client_name"] == "TESTCLIENT"

@pytest.mark.asyncio
async def test_recherche_parallele(chatbot):
    # Mock pour tester la recherche parallèle
    async def mock_recherche(*args, **kwargs):
        await asyncio.sleep(0.1)  # Simuler délai réseau
        return [MagicMock(score=0.95)]
        
    with patch.object(chatbot, 'qdrant_clients') as mock_clients:
        # Configuration des mocks
        mock_jira = MagicMock()
        mock_jira.recherche_intelligente = mock_recherche
        mock_zendesk = MagicMock()
        mock_zendesk.recherche_intelligente = mock_recherche
        
        mock_clients.__getitem__.side_effect = lambda x: mock_jira if x == 'jira' else mock_zendesk
        
        # Test de recherche sur plusieurs collections
        results = await chatbot.recherche_parallele(
            collections=['jira', 'zendesk'],
            question="Test question"
        )
        
        assert len(results) == 2  # Deux résultats attendus (un par collection)
        assert all(hasattr(r, 'score') for r in results)