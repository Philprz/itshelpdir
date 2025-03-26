"""
test_confluence_client.py - Tests unitaires pour le client ConfluenceSearchClient
"""

import pytest
import logging
from unittest.mock import patch, MagicMock, AsyncMock

from search.clients.confluence_client import ConfluenceSearchClient, ConfluenceResultProcessor

# Tests pour ConfluenceResultProcessor
class TestConfluenceResultProcessor:
    """Tests unitaires pour le processeur de résultats Confluence"""
    
    def test_extract_title_with_title(self):
        """Teste l'extraction du titre avec le champ 'title'"""
        # Arrange
        processor = ConfluenceResultProcessor()
        result = MagicMock()
        result.payload = {"title": "Page de documentation"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Page de documentation"
    
    def test_extract_title_with_html_entities(self):
        """Teste l'extraction du titre avec des entités HTML"""
        # Arrange
        processor = ConfluenceResultProcessor()
        result = MagicMock()
        result.payload = {"title": "Document &amp; exemple"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Document & exemple"
    
    def test_extract_title_alternative_fields(self):
        """Teste l'extraction du titre avec des champs alternatifs"""
        # Arrange
        processor = ConfluenceResultProcessor()
        
        # Test avec 'name'
        result1 = MagicMock()
        result1.payload = {"name": "Guide d'utilisation"}
        
        # Test avec 'page_title'
        result2 = MagicMock()
        result2.payload = {"page_title": "Manuel technique"}
        
        # Test avec 'subject'
        result3 = MagicMock()
        result3.payload = {"subject": "Instructions d'installation"}
        
        # Act
        title1 = processor.extract_title(result1)
        title2 = processor.extract_title(result2)
        title3 = processor.extract_title(result3)
        
        # Assert
        assert title1 == "Guide d'utilisation"
        assert title2 == "Manuel technique"
        assert title3 == "Instructions d'installation"
    
    def test_extract_title_with_space_and_page_id(self):
        """Teste l'extraction du titre à partir de l'espace et de l'ID de page"""
        # Arrange
        processor = ConfluenceResultProcessor()
        
        # Test avec space et page_id
        result = MagicMock()
        result.payload = {"space": "IT", "page_id": "12345"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Page IT #12345"
    
    def test_extract_title_with_page_id_only(self):
        """Teste l'extraction du titre avec ID de page uniquement"""
        # Arrange
        processor = ConfluenceResultProcessor()
        result = MagicMock()
        result.payload = {"page_id": "12345"}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Page #12345"
    
    def test_extract_title_empty(self):
        """Teste l'extraction du titre avec payload vide"""
        # Arrange
        processor = ConfluenceResultProcessor()
        result = MagicMock()
        result.payload = {}
        
        # Act
        title = processor.extract_title(result)
        
        # Assert
        assert title == "Page Confluence sans titre"
    
    def test_extract_url_direct(self):
        """Teste l'extraction de l'URL directement disponible"""
        # Arrange
        processor = ConfluenceResultProcessor()
        result = MagicMock()
        result.payload = {"url": "https://confluence.example.com/pages/viewpage.action?pageId=12345"}
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://confluence.example.com/pages/viewpage.action?pageId=12345"
    
    def test_extract_url_from_page_id(self):
        """Teste la construction de l'URL à partir de l'ID de page"""
        # Arrange
        processor = ConfluenceResultProcessor()
        result = MagicMock()
        result.payload = {
            "page_id": "12345", 
            "base_url": "https://custom-confluence.example.com"
        }
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://custom-confluence.example.com/pages/viewpage.action?pageId=12345"
    
    def test_extract_url_from_page_id_default_base(self):
        """Teste la construction de l'URL avec base_url par défaut"""
        # Arrange
        processor = ConfluenceResultProcessor()
        result = MagicMock()
        result.payload = {"page_id": "12345"}
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "https://confluence.example.com/pages/viewpage.action?pageId=12345"
    
    def test_extract_url_no_info(self):
        """Teste l'extraction d'URL sans information disponible"""
        # Arrange
        processor = ConfluenceResultProcessor()
        result = MagicMock()
        result.payload = {"some_field": "value"}  # Sans URL ni page_id
        
        # Act
        url = processor.extract_url(result)
        
        # Assert
        assert url == "#"
    
    def test_deduplicate_results_by_page_id(self):
        """Teste la déduplication des résultats par ID de page"""
        # Arrange
        processor = ConfluenceResultProcessor()
        
        # Créer des résultats avec le même ID de page mais des scores différents
        result1 = MagicMock()
        result1.payload = {"page_id": "12345", "title": "Page A"}
        result1.score = 0.8
        
        result2 = MagicMock()
        result2.payload = {"page_id": "12345", "title": "Page A bis"}
        result2.score = 0.9  # Score plus élevé
        
        result3 = MagicMock()
        result3.payload = {"page_id": "67890", "title": "Page B"}
        result3.score = 0.7
        
        # Act
        dedup_results = processor.deduplicate_results([result1, result2, result3])
        
        # Assert
        assert len(dedup_results) == 2  # Deux résultats uniques
        
        # Vérifier que le résultat avec le meilleur score pour l'ID 12345 est conservé
        page_ids = [r.payload.get('page_id') for r in dedup_results]
        assert "12345" in page_ids
        assert "67890" in page_ids
        
        # Vérifier que c'est le résultat2 (score plus élevé) qui est conservé pour l'ID 12345
        for r in dedup_results:
            if r.payload.get('page_id') == "12345":
                assert r.score == 0.9
    
    def test_deduplicate_results_by_url(self):
        """Teste la déduplication des résultats par URL"""
        # Arrange
        processor = ConfluenceResultProcessor()
        
        # Créer des résultats sans ID mais avec des URLs
        result1 = MagicMock()
        result1.payload = {"url": "https://confluence.example.com/page1", "title": "Page 1"}
        
        result2 = MagicMock()
        result2.payload = {"url": "https://confluence.example.com/page2", "title": "Page 2"}
        
        result3 = MagicMock()
        result3.payload = {"url": "https://confluence.example.com/page1", "title": "Page 1 bis"}
        
        # Act
        dedup_results = processor.deduplicate_results([result1, result2, result3])
        
        # Assert
        assert len(dedup_results) == 2  # Deux résultats uniques
        
        # Vérifier que les deux URLs uniques sont présentes
        urls = [r.payload.get('url') for r in dedup_results]
        assert "https://confluence.example.com/page1" in urls
        assert "https://confluence.example.com/page2" in urls
    
    def test_deduplicate_results_empty(self):
        """Teste la déduplication avec une liste vide"""
        # Arrange
        processor = ConfluenceResultProcessor()
        
        # Act
        dedup_results = processor.deduplicate_results([])
        
        # Assert
        assert dedup_results == []
    
    def test_deduplicate_results_no_id_or_url(self):
        """Teste la déduplication avec des résultats sans ID ni URL"""
        # Arrange
        processor = ConfluenceResultProcessor()
        
        # Créer des résultats sans ID ni URL
        result1 = MagicMock()
        result1.payload = {"title": "Page sans identifiant"}
        
        result2 = MagicMock()
        result2.payload = {"title": "Autre page sans identifiant"}
        
        # Act - ces résultats ne seront pas dédupliqués car ils n'ont pas d'identifiant
        dedup_results = processor.deduplicate_results([result1, result2])
        
        # Assert - comme il n'y a pas d'ID ou d'URL pour dédupliquer, 
        # on s'attend à un résultat vide selon l'implémentation
        assert len(dedup_results) == 0


# Tests pour ConfluenceSearchClient
class TestConfluenceSearchClient:
    """Tests unitaires pour le client ConfluenceSearchClient"""
    
    def test_init_defaults(self, mock_qdrant_client, mock_embedding_service):
        """Teste l'initialisation avec des valeurs par défaut"""
        # Act
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Assert
        assert client.collection_name == "CONFLUENCE"
        assert client.client == mock_qdrant_client  
        assert client.embedding_service == mock_embedding_service
        assert isinstance(client.processor, ConfluenceResultProcessor)
        assert isinstance(client.logger, logging.Logger)
        assert client.logger.name == 'ITS_HELP.confluence_client'
    
    def test_init_custom_values(self, mock_qdrant_client, mock_embedding_service, mock_translation_service):
        """Teste l'initialisation avec des valeurs personnalisées"""
        # Act
        client = ConfluenceSearchClient(
            collection_name="CUSTOM_CONFLUENCE",
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            translation_service=mock_translation_service
        )
        
        # Assert
        assert client.collection_name == "CUSTOM_CONFLUENCE"
        assert client.client == mock_qdrant_client  
        assert client.embedding_service == mock_embedding_service
        assert client.translation_service == mock_translation_service
    
    def test_get_source_name(self, mock_qdrant_client, mock_embedding_service):
        """Teste la méthode get_source_name"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Act
        source_name = client.get_source_name()
        
        # Assert
        assert source_name == "CONFLUENCE"
    
    def test_valider_resultat_valid(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation de différents types de résultats valides"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Cas 1: Avec page_id et title
        result1 = MagicMock()
        result1.payload = {
            "page_id": "12345",
            "title": "Page de documentation"
        }
        
        # Cas 2: Avec URL et content
        result2 = MagicMock()
        result2.payload = {
            "url": "https://confluence.example.com/page",
            "content": "Contenu de la page"
        }
        
        # Act & Assert
        assert client.valider_resultat(result1) is True
        assert client.valider_resultat(result2) is True
    
    def test_valider_resultat_invalid_no_id_or_url(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans ID ni URL"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        result = MagicMock()
        result.payload = {
            "title": "Page sans identifiant",
            "content": "Contenu de la page"
        }
        
        # Act
        is_valid = client.valider_resultat(result)
        
        # Assert
        assert is_valid is False
    
    def test_valider_resultat_invalid_no_title_or_content(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans titre ni contenu"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        result = MagicMock()
        result.payload = {
            "page_id": "12345",
            "space": "IT"
        }
        
        # Act
        is_valid = client.valider_resultat(result)
        
        # Assert
        assert is_valid is False
    
    def test_valider_resultat_invalid_no_payload(self, mock_qdrant_client, mock_embedding_service):
        """Teste la validation d'un résultat sans payload"""
        # Arrange
        client = ConfluenceSearchClient(
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
    async def test_recherche_intelligente_with_deduplication(self, mock_qdrant_client, mock_embedding_service):
        """Teste la recherche avec déduplication des résultats"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer des résultats simulés avec doublons
        mock_results = [
            MagicMock(payload={"page_id": "12345", "title": "Page A"}, score=0.8),
            MagicMock(payload={"page_id": "12345", "title": "Page A bis"}, score=0.9),
            MagicMock(payload={"page_id": "67890", "title": "Page B"}, score=0.7)
        ]
        
        # Patch la méthode de recherche de la classe parent
        with patch('search.core.client_base.GenericSearchClient.recherche_intelligente', 
                   new_callable=AsyncMock) as mock_parent_search:
            mock_parent_search.return_value = mock_results
            
            # Patch la méthode de déduplication
            dedup_results = [mock_results[1], mock_results[2]]  # On garde les 2 résultats uniques
            with patch.object(client.processor, 'deduplicate_results', return_value=dedup_results):
                
                # Act
                results = await client.recherche_intelligente(
                    question="Comment configurer Confluence?",
                    limit=5,
                    score_threshold=0.5
                )
                
                # Assert
                mock_parent_search.assert_called_once_with(
                    question="Comment configurer Confluence?",
                    limit=10,  # Doit être 2x la limite demandée
                    score_threshold=0.5,
                    client_name=None
                )
                assert len(results) == 2
                assert results[0].payload["title"] == "Page A bis"
                assert results[1].payload["title"] == "Page B"
    
    @pytest.mark.asyncio
    async def test_format_for_message_with_results(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage des résultats pour un message"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer des résultats de test
        results = [
            MagicMock(
                payload={
                    "title": "Guide d'utilisation",
                    "page_id": "12345",
                    "space": "IT",
                    "author": "Jean Dupont",
                    "last_updated": "2023-03-15",
                    "content": "<p>Ce guide explique comment utiliser l'application.</p>"
                }
            ),
            MagicMock(
                payload={
                    "title": "Manuel technique",
                    "page_id": "67890",
                    "space": "DEV",
                    "content": "<div>Documentation technique détaillée pour les développeurs.</div>"
                }
            )
        ]
        
        # Act
        formatted = await client.format_for_message(results)
        
        # Assert
        assert "📝 **Pages Confluence pertinentes:**" in formatted
        assert "**[Guide d'utilisation]" in formatted
        assert "**[Manuel technique]" in formatted
        assert "Espace: IT" in formatted
        assert "Auteur: Jean Dupont" in formatted
        assert "Mise à jour: 2023-03-15" in formatted
        assert "Ce guide explique comment utiliser l'application" in formatted
        assert "Documentation technique détaillée pour les développeurs" in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_html_cleaning(self, mock_qdrant_client, mock_embedding_service):
        """Teste le nettoyage du HTML dans le formatage des messages"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer un résultat avec du contenu HTML complexe
        result = MagicMock(
            payload={
                "title": "Page avec HTML",
                "page_id": "12345",
                "content": "<h1>Titre</h1><p>Paragraphe avec <strong>texte en gras</strong> et <em>italique</em>.</p><ul><li>Item 1</li><li>Item 2</li></ul>"
            }
        )
        
        # Patch les méthodes extract_title et extract_url
        with patch.object(client.processor, 'extract_title', return_value="Page avec HTML"):
            with patch.object(client.processor, 'extract_url', 
                             return_value="https://confluence.example.com/pages/viewpage.action?pageId=12345"):
                
                # Act
                formatted = await client.format_for_message([result])
                
                # Assert
                assert "Titre Paragraphe avec texte en gras et italique. Item 1 Item 2" in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_long_content(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage avec un contenu long"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer un résultat avec un contenu long
        long_content = "A" * 200  # 200 caractères
        result = MagicMock(
            payload={
                "title": "Page avec contenu long",
                "page_id": "12345",
                "content": long_content
            }
        )
        
        # Patch les méthodes extract_title et extract_url
        with patch.object(client.processor, 'extract_title', return_value="Page avec contenu long"):
            with patch.object(client.processor, 'extract_url', 
                             return_value="https://confluence.example.com/pages/viewpage.action?pageId=12345"):
                
                # Act
                formatted = await client.format_for_message([result])
                
                # Assert
                assert "..." in formatted  # Vérifier que le contenu est tronqué
                content_in_message = formatted.split("> ")[1].split("\n")[0]
                assert len(content_in_message) <= 150  # Vérifier que la longueur est limitée
    
    @pytest.mark.asyncio
    async def test_format_for_message_excerpt_fallback(self, mock_qdrant_client, mock_embedding_service):
        """Teste l'utilisation du champ excerpt quand content n'est pas disponible"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer un résultat avec excerpt mais sans content
        result = MagicMock(
            payload={
                "title": "Page sans contenu",
                "page_id": "12345",
                "excerpt": "Extrait de la page à afficher comme fallback."
            }
        )
        
        # Patch les méthodes extract_title et extract_url
        with patch.object(client.processor, 'extract_title', return_value="Page sans contenu"):
            with patch.object(client.processor, 'extract_url', 
                             return_value="https://confluence.example.com/pages/viewpage.action?pageId=12345"):
                
                # Act
                formatted = await client.format_for_message([result])
                
                # Assert
                assert "Extrait de la page à afficher comme fallback" in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_more_than_five(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage avec plus de 5 résultats"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Créer plus de 5 résultats
        results = [
            MagicMock(payload={"title": f"Page {i}", "page_id": f"{i}"}) 
            for i in range(1, 8)
        ]
        
        # Patch les méthodes extract_title et extract_url
        with patch.object(client.processor, 'extract_title', 
                         side_effect=lambda r: f"Page {r.payload['page_id']}"):
            with patch.object(client.processor, 'extract_url', 
                             side_effect=lambda r: f"https://confluence.example.com/pages/viewpage.action?pageId={r.payload['page_id']}"):
                
                # Act
                formatted = await client.format_for_message(results)
                
                # Assert
                assert "_...et 2 autres pages._" in formatted
                # Vérifier que seules les 5 premières pages sont détaillées
                for i in range(1, 6):
                    assert f"**[Page {i}]" in formatted
                # Vérifier que les pages au-delà de 5 ne sont pas incluses
                for i in range(6, 8):
                    assert f"**[Page {i}]" not in formatted
    
    @pytest.mark.asyncio
    async def test_format_for_message_no_results(self, mock_qdrant_client, mock_embedding_service):
        """Teste le formatage quand il n'y a pas de résultats"""
        # Arrange
        client = ConfluenceSearchClient(
            qdrant_client=mock_qdrant_client,
            embedding_service=mock_embedding_service
        )
        
        # Act
        formatted = await client.format_for_message([])
        
        # Assert
        assert formatted == "Aucune page Confluence trouvée."
