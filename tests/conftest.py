"""
conftest.py - Fichier de configuration pytest pour les tests unitaires des clients de recherche
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Classes de base pour les mocks
class MockQdrantClient:
    """Mock de base pour QdrantClient utilisé dans les tests"""
    
    def __init__(self):
        """Initialise le mock avec des méthodes asynchrones simulées."""
        self.search = AsyncMock()
        self.get_collections = MagicMock(return_value=MagicMock(collections=[
            MagicMock(name="JIRA"),
            MagicMock(name="ZENDESK"), 
            MagicMock(name="NETSUITE"),
            MagicMock(name="NETSUITE_DUMMIES"),
            MagicMock(name="SAP"),
            MagicMock(name="CONFLUENCE"),
            MagicMock(name="ERP")
        ]))
    
    async def search_async(self, *args, **kwargs):
        """Simule une recherche asynchrone avec des résultats prédéfinis."""
        # Retourner un résultat simulé
        return self.search(*args, **kwargs)


class MockEmbeddingService:
    """Mock pour le service d'embedding utilisé dans les tests"""
    
    def __init__(self):
        """Initialise le mock avec des méthodes simulées."""
        self.get_embedding = AsyncMock(return_value=[0.1] * 1536)


class MockTranslationService:
    """Mock pour le service de traduction utilisé dans les tests"""
    
    def __init__(self):
        """Initialise le mock avec des méthodes simulées."""
        self.translate = AsyncMock(side_effect=lambda text, *args, **kwargs: text)


class MockGenericResult:
    """Classe pour simuler un résultat générique de recherche vectorielle"""
    
    def __init__(self, id="test-id", score=0.8, payload=None):
        """
        Initialise un résultat de recherche simulé.
        
        Args:
            id: Identifiant du résultat
            score: Score de similarité
            payload: Contenu du document
        """
        self.id = id
        self.score = score
        self.payload = payload or {
            "title": "Document de test",
            "content": "Contenu de test pour la recherche vectorielle",
            "url": "https://exemple.com/document",
            "type": "document"
        }


@pytest.fixture
def mock_qdrant_client():
    """Fixture pour fournir un client Qdrant simulé."""
    return MockQdrantClient()


@pytest.fixture
def mock_embedding_service():
    """Fixture pour fournir un service d'embedding simulé."""
    return MockEmbeddingService()


@pytest.fixture
def mock_translation_service():
    """Fixture pour fournir un service de traduction simulé."""
    return MockTranslationService()


@pytest.fixture
def mock_search_results():
    """Fixture pour fournir des résultats de recherche simulés."""
    # Résultats pour tests génériques
    base_results = [
        MockGenericResult(
            id=f"result-{i}",
            score=0.9 - (i * 0.1),
            payload={
                "title": f"Document test {i}",
                "content": f"Contenu de test pour le document {i}",
                "url": f"https://exemple.com/document{i}",
                "type": "document"
            }
        ) for i in range(1, 6)
    ]
    
    # Résultats pour Jira
    jira_results = [
        MockGenericResult(
            id=f"jira-{i}",
            score=0.9 - (i * 0.1),
            payload={
                "title": f"TICKET-{i} Problème test {i}",
                "content": f"Description du problème {i}",
                "url": f"https://jira.exemple.com/browse/TICKET-{i}",
                "type": "issue"
            }
        ) for i in range(1, 6)
    ]
    
    # Résultats pour Confluence
    confluence_results = [
        MockGenericResult(
            id=f"conf-{i}",
            score=0.9 - (i * 0.1),
            payload={
                "title": f"Page de documentation {i}",
                "content": f"Contenu de la page de documentation {i}",
                "url": f"https://confluence.exemple.com/pages/viewpage.action?pageId={1000+i}",
                "page_id": f"{1000+i}",
                "space": "DOC"
            }
        ) for i in range(1, 6)
    ]
    
    # Retourne les différents types de résultats en dictionnaire
    return {
        "generic": base_results,
        "jira": jira_results,
        "confluence": confluence_results
    }


# Fixture pour exécuter les coroutines asynchrones dans les tests
@pytest.fixture
def event_loop():
    """Crée une boucle d'événements pour les tests asyncio."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
