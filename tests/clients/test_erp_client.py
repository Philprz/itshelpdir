"""
test_erp_client.py - Tests unitaires pour le client ERPSearchClient
"""

import pytest
import logging
from unittest.mock import patch, MagicMock, AsyncMock

from search.clients.erp_client import ERPSearchClient, ERPResultProcessor

# Tests pour ERPResultProcessor
class TestERPResultProcessor:
    """Tests unitaires pour le processeur de résultats ERP"""
    
    def test_extract_title_with_title(self):
        """Teste l'extraction du titre avec le champ 'title'"""
        # Arrange
        processor = ERPResultProcessor()
        result = MagicMock()
        result.payload = {"title": "Facture client"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Facture client"
    
    def test_extract_title_alternative_fields(self):
        """Teste l'extraction du titre avec des champs alternatifs"""
        # Arrange
        processor = ERPResultProcessor()
        
        # Test avec 'name'
        result1 = MagicMock()
        result1.payload = {"name": "Commande fournisseur"}
        
        # Test avec 'docname'
        result2 = MagicMock()
        result2.payload = {"docname": "Bon de livraison"}
        
        # Test avec 'subject'
        result3 = MagicMock()
        result3.payload = {"subject": "Relevé de compte"}
        
        # Act
        title1 = processor.extract_title(result1)
        title2 = processor.extract_title(result2)
        title3 = processor.extract_title(result3)
        
        # Assert
        assert title1 == "Commande fournisseur"
        assert title2 == "Bon de livraison"
        assert title3 == "Relevé de compte"
    
    def test_extract_title_with_doc_id(self):
        """Teste l'extraction du titre à partir de doc_id et doc_type"""
        # Arrange
        processor = ERPResultProcessor()
        
        # Test avec doc_id et doc_type
        result1 = MagicMock()
        result1.payload = {"doc_id": "FV2023-001", "doc_type": "Facture"}
        
        # Test avec doc_id sans doc_type
        result2 = MagicMock()
        result2.payload = {"doc_id": "BL2023-002"}
        
        # Act
        title1 = processor.extract_title(result1)
        title2 = processor.extract_title(result2)
        
        # Assert
        assert title1 == "Facture FV2023-001"
        assert title2 == "Document BL2023-002"
    
    def test_extract_title_empty(self):
        """Teste l'extraction du titre avec payload vide"""
        # Arrange
        processor = ERPResultProcessor()
        result = MagicMock()
        result.payload = {}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Document ERP sans titre"
    
    def test_extract_url_direct(self):
        """Teste l'extraction de l'URL directement disponible"""
        # Arrange
        processor = ERPResultProcessor()
        result = MagicMock()
        result.payload = {"url": "https://erp.example.com/document/123"}
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://erp.example.com/document/123"
    
    def test_extract_url_from_doc_id(self):
        """Teste la construction de l'URL à partir du doc_id et doc_type"""
        # Arrange
        processor = ERPResultProcessor()
        result = MagicMock()
        result.payload = {
            "doc_id": "INV-2023-001", 
            "doc_type": "invoice",
            "base_url": "https://custom-erp.example.com"
        }
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://custom-erp.example.com/view?id=INV-2023-001&type=invoice"
    
    def test_extract_url_from_doc_id_default_base(self):
        """Teste la construction de l'URL avec base_url par défaut"""
        # Arrange
        processor = ERPResultProcessor()
        result = MagicMock()
        result.payload = {"doc_id": "INV-2023-001", "doc_type": "invoice"}
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://erp.example.com/view?id=INV-2023-001&type=invoice"
    
    def test_extract_url_no_info(self):
        """Teste l'extraction d'URL sans information disponible"""
        # Arrange
        processor = ERPResultProcessor()
        result = MagicMock()
        result.payload = {"some_field": "value"}  # Sans URL ni doc_id
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "#"


# Tests pour ERPSearchClient
class TestERPSearchClient:
    """Tests unitaires pour le client ERPSearchClient"""
    
    def test_init_defaults(self, mock_qdrant_client, mock_embedding_service):
        """Teste l'initialisation avec des valeurs par défaut"""
        # Act
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Assert
        assert client.collection_name == "ERP"
        assert client.client == mock_qdrant_client
        assert client.embedding_service == mock_embedding_service
        assert isinstance(client.processor, ERPResultProcessor)
        assert isinstance(client.logger, logging.Logger)
        assert client.logger.name == 'ITS_HELP.erp_client'
    
    def test_init_custom_values(self, mock_qdrant_client, mock_embedding_service, mock_translation_service):
        """Teste l'initialisation avec des valeurs personnalisées"""
        # Act
        client = ERPSearchClient(
            collection_name="CUSTOM_ERP",
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            translation_service=mock_translation_service
        )
        
        # Assert
        assert client.collection_name == "CUSTOM_ERP"
        assert client.client == mock_qdrant_client
        assert client.embedding_service == mock_embedding_service
        assert client.translation_service == mock_translation_service
    
    def test_get_source_name(self, mock_qdrant_client, mock_embedding_service):
        """Teste la méthode get_source_name"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Act
        source_name = client.get_source_name()
        
        # Assert
        assert source_name == "ERP"
    
    def test_valider_resultat_valid(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation de différents types de résultats valides"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Cas 1: Avec doc_id
        result1 = MagicMock()
        result1.payload = {
            "doc_id": "INV-2023-001",
            "doc_type": "invoice"
        }
        
        # Cas 2: Avec title
        result2 = MagicMock()
        result2.payload = {
            "title": "Facture client",
        }
        
        # Cas 3: Avec name
        result3 = MagicMock()
        result3.payload = {
            "name": "Bon de commande",
        }
        
        # Act & Assert
        assert client.valider_resultat(result1) is True
        assert client.valider_resultat(result2) is True
        assert client.valider_resultat(result3) is True
    
    def test_valider_resultat_invalid_no_identifier(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans identifiant"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        result = MagicMock()
        result.payload = {
            "description": "Document sans identifiant ni titre"
        }
        
        # Act
        is_valid = client.valider_resultat(result)
        
        # Assert
        assert is_valid is False
    
    def test_valider_resultat_invalid_empty_doc_type(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat avec doc_type vide"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        result = MagicMock()
        result.payload = {
            "doc_id": "INV-2023-001",
            "doc_type": ""  # Type de document vide
        }
        
        # Act
        is_valid = client.valider_resultat(result)
        
        # Assert
        assert is_valid is False
    
    def test_valider_resultat_invalid_no_payload(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans payload"""
        # Arrange
        client = ERPSearchClient(
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
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer des résultats de test
        results = [
            MagicMock(
                payload={
                    "title": "Facture client",
                    "doc_id": "FV2023-001",
                    "doc_type": "invoice",
                    "date": "2023-03-15",
                    "description": "Facture pour les services de maintenance informatique."
                }
            ),
            MagicMock(
                payload={
                    "name": "Bon de commande",
                    "doc_id": "BC2023-042",
                    "doc_type": "purchase_order",
                    "content": "Commande de matériel informatique pour le service comptabilité."
                }
            )
        ]
        
        # Patch la méthode extract_url pour retourner une URL de test
        with patch.object(client.processor, 'extract_url', 
                         side_effect=lambda result: f"https://erp.example.com/view?id={result.payload.get('doc_id', '')}"):
            
            # Act
            formatted = await client.format_for_message(results)
            
            # Assert
            assert "📄 **Documents ERP pertinents:**" in formatted
            assert "**[Facture client](https://erp.example.com/view?id=FV2023-001)**" in formatted
            assert "**[Bon de commande](https://erp.example.com/view?id=BC2023-042)**" in formatted
            assert "(ID: FV2023-001)" in formatted
            assert "Type: invoice" in formatted
            assert "Date: 2023-03-15" in formatted
            assert "Facture pour les services de maintenance" in formatted
            assert "Commande de matériel informatique" in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_more_than_five(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage avec plus de 5 résultats"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer plus de 5 résultats
        results = [
            MagicMock(payload={"title": f"Document {i}", "doc_id": f"DOC-{i}"}) 
            for i in range(1, 8)
        ]
        
        # Patch la méthode extract_url
        with patch.object(client.processor, 'extract_url', 
                         side_effect=lambda result: f"https://erp.example.com/view?id={result.payload['doc_id']}"):
            
            # Act
            formatted = await client.format_for_message(results)
            
            # Assert
            assert "_...et 2 autres documents._" in formatted
            # Vérifier que seuls les 5 premiers documents sont détaillés
            for i in range(1, 6):
                assert f"**[Document {i}]" in formatted
            # Vérifier que les documents au-delà de 5 ne sont pas inclus
            for i in range(6, 8):
                assert f"**[Document {i}]" not in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_long_description(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage avec une description longue"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer un résultat avec une description longue
        long_description = "A" * 200  # 200 caractères
        result = MagicMock(
            payload={
                "title": "Document avec description longue",
                "doc_id": "DOC-123",
                "description": long_description
            }
        )
        
        # Patch la méthode extract_url
        with patch.object(client.processor, 'extract_url', 
                   return_value="https://erp.example.com/view?id=DOC-123"):
            
            # Act
            formatted = await client.format_for_message([result])
            
            # Assert
            assert "..." in formatted  # Vérifier que la description est tronquée
            description_in_message = formatted.split("> ")[1].split("\n")[0]
            assert len(description_in_message) <= 150  # Vérifier que la longueur est limitée
    
    @pytest.mark.asyncio
    async def test_format_for_message_content_fallback(self, mock_qdrant_client, mock_embedding_service):
        """Teste l'utilisation du champ content quand description n'est pas disponible"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer un résultat avec content mais sans description
        result = MagicMock(
            payload={
                "title": "Document sans description",
                "doc_id": "DOC-123",
                "content": "Contenu du document à afficher comme fallback."
            }
        )
        
        # Patch la méthode extract_url
        with patch.object(client.processor, 'extract_url', 
                   return_value="https://erp.example.com/view?id=DOC-123"):
            
            # Act
            formatted = await client.format_for_message([result])
            
            # Assert
            assert "Contenu du document à afficher comme fallback" in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_no_results(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage quand il n'y a pas de résultats"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Act
        formatted = await client.format_for_message([])
        
        # Assert
        assert formatted == "Aucun document ERP trouvé."
    
    @pytest.mark.asyncio
    async def test_recherche_intelligente(self, mock_qdrant_client, mock_embedding_service, mock_search_results):
        """Teste la méthode de recherche intelligente"""
        # Arrange
        client = ERPSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Mock pour la méthode de recherche de la classe parent
        with patch('search.core.client_base.GenericSearchClient.recherche_intelligente', 
                   new_callable=AsyncMock) as mock_parent_search:
            mock_parent_search.return_value = mock_search_results
            
            # Act
            results = await client.recherche_intelligente(
                question="Comment créer une facture?",
                client_name="TestClient",
                limit=5,
                score_threshold=0.5
            )
            
            # Assert
            mock_parent_search.assert_called_once_with(
                question="Comment créer une facture?",
                client_name="TestClient",
                limit=5,
                score_threshold=0.5
            )
            assert results == mock_search_results
