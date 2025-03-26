"""
test_netsuite_dummies_client.py - Tests unitaires pour le client NetsuiteDummiesSearchClient
"""

import pytest
import logging
from unittest.mock import patch, MagicMock, AsyncMock

from search.clients.netsuite_dummies_client import NetsuiteDummiesSearchClient, NetsuiteDummiesResultProcessor

# Tests pour NetsuiteDummiesResultProcessor
class TestNetsuiteDummiesResultProcessor:
    """Tests unitaires pour le processeur de résultats NetsuiteDummies"""
    
    def test_extract_payload(self):
        """Teste l'extraction et la transformation de la payload"""
        # Arrange
        processor = NetsuiteDummiesResultProcessor()
        
        # Test 1: Payload avec titre sans préfixe [EXEMPLE]
        result1 = MagicMock()
        result1.payload = {"title": "Documentation NetSuite", "content": "Contenu test"}
        
        # Test 2: Payload avec titre ayant déjà le préfixe [EXEMPLE]
        result2 = MagicMock()
        result2.payload = {"title": "[EXEMPLE] Documentation NetSuite", "content": "Contenu test"}
        
        # Test 3: Payload sans titre
        result3 = MagicMock()
        result3.payload = {"content": "Contenu test sans titre"}
        
        # Act
        payload1 = processor.extract_payload(result1)
        payload2 = processor.extract_payload(result2)
        payload3 = processor.extract_payload(result3)
        
        # Assert
        assert payload1["title"] == "[EXEMPLE] Documentation NetSuite"
        assert payload2["title"] == "[EXEMPLE] Documentation NetSuite"  # Ne devrait pas ajouter de préfixe double
        assert "title" not in payload3  # Ne devrait pas ajouter de titre


# Tests pour NetsuiteDummiesSearchClient
class TestNetsuiteDummiesSearchClient:
    """Tests unitaires pour le client NetsuiteDummiesSearchClient"""
    
    def test_init_defaults(self, mock_qdrant_client, mock_embedding_service):
        """Teste l'initialisation avec des valeurs par défaut"""
        # Act
        client = NetsuiteDummiesSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Assert
        assert client.collection_name == "NETSUITE_DUMMIES"
        assert client.client == mock_qdrant_client
        assert client.embedding_service == mock_embedding_service
        assert isinstance(client.processor, NetsuiteDummiesResultProcessor)
        assert isinstance(client.logger, logging.Logger)
        assert client.logger.name == 'ITS_HELP.netsuite_dummies_client'
    
    def test_init_custom_values(self, mock_qdrant_client, mock_embedding_service, mock_translation_service):
        """Teste l'initialisation avec des valeurs personnalisées"""
        # Act
        client = NetsuiteDummiesSearchClient(
            collection_name="CUSTOM_NETSUITE_DUMMIES",
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            translation_service=mock_translation_service
        )
        
        # Assert
        assert client.collection_name == "CUSTOM_NETSUITE_DUMMIES"
        assert client.client == mock_qdrant_client
        assert client.embedding_service == mock_embedding_service
        assert client.translation_service == mock_translation_service
    
    def test_get_source_name(self, mock_qdrant_client, mock_embedding_service):
        """Teste la méthode get_source_name"""
        # Arrange
        client = NetsuiteDummiesSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Act
        source_name = client.get_source_name()
        
        # Assert
        assert source_name == "NetSuite Exemples"
    
    def test_valider_resultat_valid(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation de résultats valides"""
        # Arrange
        client = NetsuiteDummiesSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Cas 1: Résultat complet
        result1 = MagicMock()
        result1.payload = {
            "title": "Document test",
            "content": "Contenu de test pour le document",
            "url": "https://exemple.com/doc1"
        }
        
        # Act & Assert
        assert client.valider_resultat(result1) is True
    
    def test_valider_resultat_invalid_no_content(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans contenu"""
        # Arrange
        client = NetsuiteDummiesSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Cas 1: Sans contenu
        result1 = MagicMock()
        result1.payload = {
            "title": "Document test",
            "url": "https://exemple.com/doc1"
        }
        
        # Act & Assert
        assert client.valider_resultat(result1) is False
    
    def test_valider_resultat_invalid_no_payload(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans payload"""
        # Arrange
        client = NetsuiteDummiesSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Cas: Sans payload
        result = MagicMock()
        result.payload = None
        
        # Act & Assert
        assert client.valider_resultat(result) is False
    
    @pytest.mark.asyncio
    async def test_format_for_message_with_results(self, mock_qdrant_client, mock_embedding_service, mock_search_results):
        """Teste le formatage des résultats pour un message"""
        # Arrange
        client = NetsuiteDummiesSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Utiliser les résultats génériques
        results = mock_search_results["generic"]
        
        # Patch la méthode format_for_message de la classe parente pour simuler son comportement
        with patch('search.core.client_base.GenericSearchClient.format_for_message', 
                   new_callable=AsyncMock) as mock_parent_format:
            mock_parent_format.return_value = (
                "📝 **Documents pertinents:**\n"
                "1. [Document test 1](https://exemple.com/document1)\n"
                "2. [Document test 2](https://exemple.com/document2)\n"
            )
            
            # Act
            formatted = await client.format_for_message(results)
            
            # Assert
            assert "⚠️ EXEMPLES DE DOCUMENTATION:" in formatted
            assert "**Documents pertinents:**" in formatted
            assert "[Document test 1]" in formatted
            assert "[Document test 2]" in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_no_results(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage quand il n'y a pas de résultats"""
        # Arrange
        client = NetsuiteDummiesSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Act
        formatted = await client.format_for_message([])
        
        # Assert
        assert formatted == "Aucun exemple trouvé."
