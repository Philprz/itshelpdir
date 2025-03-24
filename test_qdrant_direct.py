#!/usr/bin/env python
# -*- coding: utf-8 -*-

# test_qdrant_direct.py
# Outil pour tester directement l'interrogation de Qdrant via le handle

import os
import sys
import json
import argparse
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

# Import des modules du projet
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from configuration import setup_logging
from embedding_service import EmbeddingService

# Configuration du logging
setup_logging()
logger = logging.getLogger('ITS_HELP.qdrant_test')
logger.setLevel(logging.INFO)

class QdrantDirectTester:
    """Classe pour tester directement l'interrogation de Qdrant via le handle."""
    
    def __init__(self, collection_name: str):
        """
        Initialise le testeur Qdrant direct.
        
        Args:
            collection_name: Nom de la collection Qdrant à interroger
        """
        self.collection_name = collection_name
        self._init_clients()
        self.embedding_service = EmbeddingService()
    
    def _init_clients(self):
        """Initialise les clients nécessaires."""
        try:
            self.qdrant_client = QdrantClient(
                url=os.getenv('QDRANT_URL'),
                api_key=os.getenv('QDRANT_API_KEY')
            )
            
            # Vérification que la collection existe
            collections = self.qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                available_collections = ", ".join(collection_names)
                logger.error(f"La collection '{self.collection_name}' n'existe pas. Collections disponibles: {available_collections}")
                sys.exit(1)
                
            logger.info(f"Connexion réussie à Qdrant. Collection '{self.collection_name}' accessible.")
            
        except Exception as e:
            logger.error(f"Erreur d'initialisation des clients: {str(e)}")
            sys.exit(1)
    
    async def obtenir_embedding(self, texte: str) -> List[float]:
        """
        Obtient l'embedding d'un texte.
        
        Args:
            texte: Texte à transformer en embedding
            
        Returns:
            Liste des valeurs de l'embedding
        """
        try:
            embedding = await self.embedding_service.get_embedding(texte)
            if not embedding:
                raise ValueError("Erreur génération embedding: résultat vide")
            return embedding
        except Exception as e:
            logger.error(f"Erreur génération embedding: {str(e)}")
            sys.exit(1)
    
    def construire_filtre(self, client_name: Optional[str] = None) -> Optional[Filter]:
        """
        Construit un filtre Qdrant en fonction des critères.
        
        Args:
            client_name: Nom du client pour filtrer les résultats (optionnel)
            
        Returns:
            Filtre Qdrant ou None si pas de filtre
        """
        if not client_name:
            return None
            
        return Filter(
            must=[
                FieldCondition(
                    key="client",
                    match=MatchValue(value=client_name)
                )
            ]
        )
    
    async def recherche_directe(self, 
                               question: str, 
                               limit: int = 5, 
                               client_name: Optional[str] = None,
                               afficher_scores: bool = True,
                               format_json: bool = False) -> List[Dict[str, Any]]:
        """
        Effectue une recherche directe dans Qdrant.
        
        Args:
            question: Question ou texte à rechercher
            limit: Nombre maximum de résultats à retourner
            client_name: Nom du client pour filtrer les résultats (optionnel)
            afficher_scores: Affiche les scores de similarité
            format_json: Retourne les résultats en format JSON
            
        Returns:
            Liste des résultats de recherche
        """
        try:
            # Obtention de l'embedding
            vector = await self.obtenir_embedding(question)
            
            # Construction du filtre
            query_filter = self.construire_filtre(client_name)
            
            # Exécution de la recherche
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=limit,
                query_filter=query_filter
            )
            
            # Transformation des résultats
            results = []
            for result in search_results:
                item = {
                    "score": round(result.score, 4)
                }
                # Fusion du payload dans l'item
                item.update(result.payload)
                results.append(item)
            
            return results
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche: {str(e)}")
            return []
    
    def afficher_resultats(self, resultats: List[Dict[str, Any]], format_json: bool = False):
        """
        Affiche les résultats de recherche.
        
        Args:
            resultats: Liste des résultats de recherche
            format_json: Affiche les résultats en format JSON
        """
        if not resultats:
            print("Aucun résultat trouvé.")
            return
            
        if format_json:
            print(json.dumps(resultats, indent=2, ensure_ascii=False))
            return
            
        print(f"\n{'-' * 80}")
        print(f"Résultats de recherche ({len(resultats)} trouvés) :")
        print(f"{'-' * 80}")
        
        for i, result in enumerate(resultats, 1):
            score = result.get("score", 0)
            print(f"\n[{i}] Score: {score:.4f}")
            
            # Affichage des champs prioritaires s'ils existent
            priority_fields = ["key", "summary", "title", "content", "description", "client"]
            for field in priority_fields:
                if field in result and result[field]:
                    value = result[field]
                    # Tronquer les champs trop longs
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:97] + "..."
                    print(f"  {field.capitalize()}: {value}")
            
            # Affichage des autres champs
            other_fields = [f for f in result.keys() if f not in priority_fields and f != "score"]
            for field in other_fields:
                value = result[field]
                # Ne pas afficher les valeurs vides ou très longues
                if value and (not isinstance(value, str) or len(value) < 100):
                    print(f"  {field.capitalize()}: {value}")
            
            print(f"{'-' * 40}")

async def main():
    # Analyse des arguments de ligne de commande
    parser = argparse.ArgumentParser(description='Outil de test direct de Qdrant')
    parser.add_argument('question', help='Question ou texte à rechercher')
    parser.add_argument('--collection', '-c', default='jira', help='Nom de la collection Qdrant (défaut: jira)')
    parser.add_argument('--limit', '-l', type=int, default=5, help='Nombre maximum de résultats (défaut: 5)')
    parser.add_argument('--client', help='Nom du client pour filtrer les résultats')
    parser.add_argument('--json', '-j', action='store_true', help='Affiche les résultats en format JSON')
    parser.add_argument('--list-collections', action='store_true', help='Liste les collections disponibles')
    
    args = parser.parse_args()
    
    # Vérification des variables d'environnement
    for env_var in ['OPENAI_API_KEY', 'QDRANT_URL']:
        if not os.getenv(env_var):
            print(f"Erreur: Variable d'environnement {env_var} non définie.")
            sys.exit(1)
    
    # Liste des collections si demandé
    if args.list_collections:
        client = QdrantClient(
            url=os.getenv('QDRANT_URL'),
            api_key=os.getenv('QDRANT_API_KEY')
        )
        collections = client.get_collections().collections
        print("Collections disponibles:")
        for coll in collections:
            print(f"- {coll.name}")
        return
    
    # Création du testeur
    tester = QdrantDirectTester(args.collection)
    
    # Exécution de la recherche
    print(f"Recherche dans la collection '{args.collection}' pour: {args.question}")
    if args.client:
        print(f"Filtrage par client: {args.client}")
        
    resultats = await tester.recherche_directe(
        args.question,
        limit=args.limit,
        client_name=args.client,
        format_json=args.json
    )
    
    # Affichage des résultats
    tester.afficher_resultats(resultats, args.json)

if __name__ == "__main__":
    asyncio.run(main())
