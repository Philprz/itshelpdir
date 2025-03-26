#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_date_formatting.py
Script pour tester spécifiquement le formatage des dates dans les clients de recherche.
"""

import os
import asyncio
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import ScoredPoint

# Chargement des variables d'environnement
load_dotenv(verbose=True)
print("Variables d'environnement chargées.")

# Création d'un résultat factice avec différents formats de dates
def create_mock_result(date_format_type):
    """
    Crée un résultat factice avec différents formats de dates selon le type spécifié.
    Types: 'string', 'datetime', 'timestamp', 'iso', 'malformed'
    """
    now = datetime.now(tz=timezone.utc)
    
    if date_format_type == 'string':
        created = now.strftime("%Y-%m-%d")
        updated = now.strftime("%Y/%m/%d")
    elif date_format_type == 'datetime':
        created = now
        updated = now
    elif date_format_type == 'timestamp':
        created = int(now.timestamp())
        updated = float(now.timestamp())
    elif date_format_type == 'iso':
        created = now.isoformat()
        updated = now.isoformat().replace('+00:00', 'Z')
    elif date_format_type == 'malformed':
        created = "2023.01.15"
        updated = "01/15/2023"  # format US
    else:
        created = None
        updated = None
    
    # Création d'un ScoredPoint factice
    return ScoredPoint(
        id="mock_id",
        version=1,
        score=0.95,
        payload={
            'title': f"Document test avec dates au format {date_format_type}",
            'content': "Contenu de test pour validation du formatage des dates",
            'created': created,
            'updated': updated,
            'client': 'CLIENT_TEST',
            'url': 'https://example.com/test'
        },
        vector=[0.0] * 1536
    )

async def test_date_formatting():
    """Teste spécifiquement le formatage des dates dans les clients de recherche."""
    print("\n" + "=" * 80)
    print("TEST DU FORMATAGE DES DATES")
    print("=" * 80)
    
    try:
        # Import des clients et processeurs
        from search_clients import NetsuiteSearchClient, SapSearchClient, JiraSearchClient, ZendeskSearchClient, ConfluenceSearchClient
        from search_base import DefaultResultProcessor
        
        # Initialisation du client Qdrant
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not qdrant_url:
            print("Erreur: URL Qdrant manquante!")
            return
        
        print(f"Connexion à Qdrant: {qdrant_url}")
        qdrant_client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=30
        )
        print("Client Qdrant initialisé")
        
        # Création d'un service d'embedding minimal
        class MinimalEmbeddingService:
            async def get_embedding(self, text):
                return [0.0] * 1536
                
        embedding_service = MinimalEmbeddingService()
        
        # Liste des formats de dates à tester
        date_formats = ['string', 'datetime', 'timestamp', 'iso', 'malformed', None]
        
        # Liste des clients à tester
        clients = [
            ("JIRA", JiraSearchClient("JIRA", qdrant_client, embedding_service)),
            ("ZENDESK", ZendeskSearchClient("ZENDESK", qdrant_client, embedding_service)),
            ("CONFLUENCE", ConfluenceSearchClient("CONFLUENCE", qdrant_client, embedding_service)),
            ("NETSUITE", NetsuiteSearchClient("NETSUITE", qdrant_client, embedding_service)),
            ("SAP", SapSearchClient("SAP", qdrant_client, embedding_service))
        ]
        
        # Test du processeur par défaut
        print("\n" + "=" * 40)
        print("TEST DU PROCESSEUR PAR DÉFAUT")
        print("=" * 40)
        
        processor = DefaultResultProcessor()
        
        for date_format in date_formats:
            print(f"\nFormat de date: {date_format}")
            mock_result = create_mock_result(date_format)
            
            try:
                # Test d'extraction du payload
                payload = processor.extract_payload(mock_result)
                print(f"Extraction du payload: {'Réussie' if payload else 'Échec'}")
                
                # Test de normalisation des dates
                if payload:
                    created = payload.get('created')
                    updated = payload.get('updated')
                    
                    if created:
                        normalized_created = processor.normalize_date(created)
                        print(f"Normalisation date de création: {normalized_created} (Type: {type(normalized_created).__name__})")
                    
                    if updated:
                        normalized_updated = processor.normalize_date(updated)
                        print(f"Normalisation date de mise à jour: {normalized_updated} (Type: {type(normalized_updated).__name__})")
            
            except Exception as e:
                print(f"Erreur processeur: {str(e)}")
        
        # Test de chaque client
        for client_name, client in clients:
            print("\n" + "=" * 40)
            print(f"TEST DU CLIENT: {client_name}")
            print("=" * 40)
            
            for date_format in date_formats:
                print(f"\nFormat de date: {date_format}")
                mock_result = create_mock_result(date_format)
                
                try:
                    # Test de format_for_slack
                    slack_message = await client.format_for_slack(mock_result)
                    print(f"Format pour Slack: {'Réussi' if slack_message else 'Échec'}")
                    
                    # Si SAP ou NetSuite, tester le parse_date
                    if client_name in ['SAP', 'NETSUITE'] and hasattr(client, 'parse_date'):
                        created = mock_result.payload.get('created')
                        updated = mock_result.payload.get('updated')
                        
                        if created:
                            parsed_created = client.parse_date(created)
                            print(f"Parsing date de création: {parsed_created} (Type: {type(parsed_created).__name__})")
                        
                        if updated:
                            parsed_updated = client.parse_date(updated)
                            print(f"Parsing date de mise à jour: {parsed_updated} (Type: {type(parsed_updated).__name__})")
                
                except Exception as e:
                    print(f"Erreur client {client_name}: {str(e)}")
            
            # Test du format_dates si disponible
            if hasattr(client, '_format_dates'):
                print("\nTest de _format_dates:")
                for date_format in date_formats:
                    print(f"\nFormat de date: {date_format}")
                    mock_payload = create_mock_result(date_format).payload
                    
                    try:
                        formatted_dates = client._format_dates(mock_payload)
                        print(f"Formatage des dates: {formatted_dates}")
                    except Exception as e:
                        print(f"Erreur formatage: {str(e)}")
            
    except Exception as e:
        print(f"Erreur globale: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_date_formatting())
