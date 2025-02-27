# tests/test_qdrant_integration.py
import pytest
import os
from unittest.mock import patch, MagicMock
from qdrant_jira import QdrantJiraSearch
from qdrant_zendesk import QdrantZendeskSearch

@pytest.fixture
def mock_qdrant_client():
    with patch('qdrant_client.QdrantClient') as mock_client:
        # Configuration du mock
        instance = mock_client.return_value
        instance.search.return_value = [
            MagicMock(
                id="test-1",
                score=0.85,
                payload={
                    "key": "TEST-123",
                    "summary": "Test ticket",
                    "content": "Test content",
                    "client": "TESTCLIENT",
                    "resolution": "Done",
                    "assignee": "test_user",
                    "created": "2023-01-01",
                    "updated": "2023-01-02",
                    "url": "http://test.com"
                }
            )
        ]
        return instance

@pytest.mark.asyncio
async def test_jira_search(mock_qdrant_client):
    with patch('openai.OpenAI'):
        with patch.object(QdrantJiraSearch, 'obtenir_embedding', return_value=[0.1] * 1536):
            jira_search = QdrantJiraSearch("test_collection")
            results = await jira_search.recherche_intelligente("Test question")
            
            assert len(results) == 1
            assert results[0].score == 0.85
            assert results[0].payload["key"] == "TEST-123"