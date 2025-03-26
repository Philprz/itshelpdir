"""
test_jira_client.py - Tests unitaires pour le client JiraSearchClient
"""

import pytest
import logging
from unittest.mock import patch, MagicMock, AsyncMock

from search.clients.jira_client import JiraSearchClient, JiraResultProcessor

# Tests pour JiraResultProcessor
class TestJiraResultProcessor:
    """Tests unitaires pour le processeur de résultats Jira"""
    
    def test_extract_title_complete(self):
        """Teste l'extraction du titre avec key et title"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {"key": "PROJ-123", "title": "Problème de connexion"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "[PROJ-123] Problème de connexion"
    
    def test_extract_title_with_summary(self):
        """Teste l'extraction du titre avec key et summary (sans title)"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {"key": "PROJ-123", "summary": "Problème de connexion"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "[PROJ-123] Problème de connexion"
    
    def test_extract_title_key_only(self):
        """Teste l'extraction du titre avec key uniquement"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {"key": "PROJ-123"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "[PROJ-123]"
    
    def test_extract_title_no_key(self):
        """Teste l'extraction du titre sans key"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {"title": "Problème de connexion"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Problème de connexion"
    
    def test_extract_title_empty(self):
        """Teste l'extraction du titre avec payload vide"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Ticket sans titre"
    
    def test_extract_url_direct(self):
        """Teste l'extraction de l'URL directement disponible"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {"url": "https://jira.example.com/browse/PROJ-123"}
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://jira.example.com/browse/PROJ-123"
    
    def test_extract_url_from_key(self):
        """Teste la construction de l'URL à partir du key"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {
            "key": "PROJ-123", 
            "base_url": "https://custom-jira.example.com"
        }
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://custom-jira.example.com/browse/PROJ-123"
    
    def test_extract_url_from_key_default_base(self):
        """Teste la construction de l'URL avec base_url par défaut"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {"key": "PROJ-123"}
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://jira.example.com/browse/PROJ-123"
    
    def test_extract_url_fallback(self):
        """Teste le fallback pour l'extraction d'URL"""
        # Arrange
        processor = JiraResultProcessor()
        result = MagicMock()
        result.payload = {"some_field": "value"}  # Sans URL ni key
        
        # Patch la méthode parent
        with patch('search.core.result_processor.DefaultResultProcessor.extract_url', 
                  return_value="https://default-url.com") as mock_parent:
            
            # Act
            url = processor.extract_url(result)
            
            # Assert
            mock_parent.assert_called_once_with(result)
            assert url == "https://default-url.com"


# Tests pour JiraSearchClient
class TestJiraSearchClient:
    """Tests unitaires pour le client JiraSearchClient"""
    
    def test_init_defaults(self, mock_qdrant_client, mock_embedding_service):
        """Teste l'initialisation avec des valeurs par défaut"""
        # Act
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Assert
        assert client.collection_name == "JIRA"
        assert client.client == mock_qdrant_client
        assert client.embedding_service == mock_embedding_service
        assert isinstance(client.processor, JiraResultProcessor)
        assert isinstance(client.logger, logging.Logger)
        assert client.logger.name == 'ITS_HELP.jira_client'
    
    def test_init_custom_values(self, mock_qdrant_client, mock_embedding_service, mock_translation_service):
        """Teste l'initialisation avec des valeurs personnalisées"""
        # Act
        client = JiraSearchClient(
            collection_name="CUSTOM_JIRA",
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            translation_service=mock_translation_service
        )
        
        # Assert
        assert client.collection_name == "CUSTOM_JIRA"
        assert client.client == mock_qdrant_client
        assert client.embedding_service == mock_embedding_service
        assert client.translation_service == mock_translation_service
    
    def test_get_source_name(self, mock_qdrant_client, mock_embedding_service):
        """Teste la méthode get_source_name"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Act
        source_name = client.get_source_name()
        
        # Assert
        assert source_name == "JIRA"
    
    def test_valider_resultat_valid(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat valide"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Cas 1: Avec title
        result1 = MagicMock()
        result1.payload = {
            "key": "PROJ-123",
            "title": "Problème de connexion"
        }
        
        # Cas 2: Avec summary
        result2 = MagicMock()
        result2.payload = {
            "key": "PROJ-456",
            "summary": "Problème d'authentification"
        }
        
        # Act & Assert
        assert client.valider_resultat(result1) is True
        assert client.valider_resultat(result2) is True
    
    def test_valider_resultat_invalid_no_key(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans key"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        result = MagicMock()
        result.payload = {
            "title": "Problème de connexion"
        }
        
        # Act
        is_valid = client.valider_resultat(result)
        
        # Assert
        assert is_valid is False
    
    def test_valider_resultat_invalid_no_title_or_summary(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans titre ni résumé"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        result = MagicMock()
        result.payload = {
            "key": "PROJ-123"
        }
        
        # Act
        is_valid = client.valider_resultat(result)
        
        # Assert
        assert is_valid is False
    
    def test_valider_resultat_invalid_no_payload(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans payload"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        result = MagicMock()
        result.payload = None
        
        # Act
        is_valid = client.valider_resultat(result)
        
        # Assert
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_format_for_message_with_results(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage des résultats pour un message"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer des résultats de test
        results = [
            MagicMock(
                payload={
                    "key": "PROJ-123",
                    "title": "Problème de connexion",
                    "status": "En cours",
                    "priority": "Haute",
                    "description": "L'utilisateur ne peut pas se connecter à l'application."
                }
            ),
            MagicMock(
                payload={
                    "key": "PROJ-456",
                    "title": "Erreur d'authentification",
                    "status": "Nouveau",
                    "description": "Le système refuse les identifiants valides."
                }
            )
        ]
        
        # Patch la méthode extract_url pour retourner une URL de test
        with patch.object(client.processor, 'extract_url', 
                         side_effect=lambda result: f"https://jira.example.com/browse/{result.payload['key']}"):
            
            # Act
            formatted = await client.format_for_message(results)
            
            # Assert
            assert "🎫 **Tickets Jira pertinents:**" in formatted
            assert "**[PROJ-123](https://jira.example.com/browse/PROJ-123)**" in formatted
            assert "**[PROJ-456](https://jira.example.com/browse/PROJ-456)**" in formatted
            assert "Status: En cours" in formatted
            assert "Priorité: Haute" in formatted
            assert "L'utilisateur ne peut pas se connecter" in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_more_than_five(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage avec plus de 5 résultats"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer plus de 5 résultats
        results = [MagicMock(payload={"key": f"PROJ-{i}", "title": f"Ticket {i}"}) for i in range(1, 8)]
        
        # Patch la méthode extract_url pour retourner une URL de test
        with patch.object(client.processor, 'extract_url', 
                         side_effect=lambda result: f"https://jira.example.com/browse/{result.payload['key']}"):
            
            # Act
            formatted = await client.format_for_message(results)
            
            # Assert
            assert "_...et 2 autres tickets._" in formatted
            # Vérifier que seuls les 5 premiers tickets sont détaillés
            for i in range(1, 6):
                assert f"**[PROJ-{i}]" in formatted
            # Vérifier que les tickets au-delà de 5 ne sont pas inclus
            for i in range(6, 8):
                assert f"**[PROJ-{i}]" not in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_long_description(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage avec une description longue"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer un résultat avec une description longue
        long_description = "A" * 200  # 200 caractères
        result = MagicMock(
            payload={
                "key": "PROJ-123",
                "title": "Problème avec description longue",
                "description": long_description
            }
        )
        
        # Patch la méthode extract_url
        with patch.object(client.processor, 'extract_url', return_value="https://jira.example.com/browse/PROJ-123"):
            
            # Act
            formatted = await client.format_for_message([result])
            
            # Assert
            assert "..." in formatted  # Vérifier que la description est tronquée
            description_in_message = formatted.split("> ")[1].split("\n")[0]
            assert len(description_in_message) <= 150  # Vérifier que la longueur est limitée
    
    @pytest.mark.asyncio
    async def test_format_for_message_no_results(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage quand il n'y a pas de résultats"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Act
        formatted = await client.format_for_message([])
        
        # Assert
        assert formatted == "Aucun ticket Jira trouvé."
    
    @pytest.mark.asyncio
    async def test_recherche_intelligente(self, mock_qdrant_client, mock_embedding_service, mock_search_results):
        """Teste la méthode de recherche intelligente"""
        # Arrange
        client = JiraSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Mock pour la méthode de recherche de la classe parent
        with patch('search.core.client_base.GenericSearchClient.recherche_intelligente', 
                   new_callable=AsyncMock) as mock_parent_search:
            mock_parent_search.return_value = mock_search_results
            
            # Act
            results = await client.recherche_intelligente(
                question="Comment résoudre PROJ-123?",
                client_name="TestClient",
                limit=5,
                score_threshold=0.5
            )
            
            # Assert
            mock_parent_search.assert_called_once_with(
                question="Comment résoudre PROJ-123?",
                client_name="TestClient",
                limit=5,
                score_threshold=0.5
            )
            assert results == mock_search_results
