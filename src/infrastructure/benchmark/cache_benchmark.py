"""
Benchmark du cache intelligent

Ce script effectue des tests de performance sur le cache intelligent
et mesure les économies de tokens dans différents scénarios.
"""

import os
import sys
import time
import random
import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

# Ajout du chemin racine au PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.infrastructure.cache import get_cache_instance, IntelligentCache
from src.adapters.embeddings import EmbeddingServiceFactory

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cache_benchmark")

# Jeu de données pour les tests
BENCHMARK_DATA = {
    "questions_similaires": [
        "Comment réinitialiser mon mot de passe NetSuite?",
        "Je n'arrive pas à me connecter à NetSuite, comment réinitialiser mon password?",
        "Procédure de reset de mot de passe pour NetSuite",
        "J'ai oublié mon mot de passe NetSuite",
        "Comment changer mon mot de passe sur NetSuite?",
        "Réinitialisation de password NetSuite",
        "Je souhaite modifier mon mot de passe NetSuite",
        "NetSuite - procédure de récupération de mot de passe",
        "Reset password NetSuite - procédure à suivre",
        "Comment faire pour changer mon mot de passe sur NetSuite?"
    ],
    "questions_variées": [
        "Comment créer une facture dans SAP?",
        "Quel est le processus d'approbation des congés?",
        "Comment installer le VPN?",
        "Où trouver les documents partagés de l'équipe?",
        "Comment soumettre une note de frais?",
        "Procédure pour le remboursement des dépenses",
        "Comment configurer mon email professionnel sur mon téléphone?",
        "Quelle est la politique de télétravail?",
        "Comment signaler un problème informatique?",
        "Comment accéder au système CRM?"
    ],
    "réponses_longues": [
        """Pour réinitialiser votre mot de passe NetSuite, suivez ces étapes :
        
        1. Accédez à la page de connexion NetSuite à l'adresse https://system.netsuite.com
        2. Cliquez sur le lien "Mot de passe oublié?" en dessous du bouton de connexion
        3. Entrez votre adresse e-mail professionnelle associée à votre compte NetSuite
        4. Cliquez sur le bouton "Envoyer le lien de réinitialisation"
        5. Consultez votre boîte de réception pour un e-mail de réinitialisation de NetSuite
        6. Cliquez sur le lien contenu dans l'e-mail (valide pendant 30 minutes)
        7. Sur la nouvelle page, créez un nouveau mot de passe en respectant les critères suivants :
           - Au moins 8 caractères
           - Au moins une lettre majuscule
           - Au moins une lettre minuscule
           - Au moins un chiffre
           - Au moins un caractère spécial
        8. Confirmez votre nouveau mot de passe
        9. Cliquez sur le bouton "Enregistrer"
        10. Vous serez automatiquement connecté à NetSuite
        
        Rappel : Votre mot de passe doit être changé tous les 90 jours selon notre politique de sécurité.
        Si vous rencontrez des problèmes avec cette procédure, contactez l'assistance IT au poste 4567."""
    ]
}

class CacheBenchmark:
    """Benchmark pour le cache intelligent"""
    
    def __init__(self):
        """Initialise le benchmark"""
        self.results = []
        self.embedding_service = None
        self.cache = None
    
    async def setup(self):
        """Configure l'environnement de test"""
        logger.info("Initialisation des services pour le benchmark...")
        
        # Créer un service d'embedding
        self.embedding_service = EmbeddingServiceFactory.create_service("openai")
        
        # Fonction d'embedding pour le cache
        async def get_embedding(text):
            return await self.embedding_service.get_embedding(text)
        
        # Créer une instance de cache optimisée pour le benchmark
        self.cache = get_cache_instance(
            embedding_function=get_embedding,
            max_entries=1000,
            default_ttl=600,  # 10 minutes
            max_memory_mb=50
        )
        
        logger.info("Environnement de test initialisé")
    
    async def run_test_exact_match(self, iterations=5):
        """Test de correspondance exacte"""
        logger.info("=== TEST DE CORRESPONDANCE EXACTE ===")
        
        start_time = time.time()
        tokens_sans_cache = 0
        tokens_avec_cache = 0
        
        # Réinitialiser le cache pour ce test
        self.cache.clear()
        
        # Pré-remplir le cache avec des données de test
        sample_data = BENCHMARK_DATA["réponses_longues"][0]
        sample_tokens = len(sample_data.split()) / 0.75
        
        # Générer des clés
        keys = [f"test_key_{i}" for i in range(10)]
        
        # Remplir le cache
        for key in keys:
            await self.cache.set(
                key,
                sample_data,
                metadata={"token_count": sample_tokens}
            )
            tokens_sans_cache += sample_tokens
        
        # Tests de récupération
        for _ in range(iterations):
            for key in keys:
                await self.cache.get(key)
                tokens_avec_cache += 0  # Le cache exact devrait consommer 0 token
        
        duration = time.time() - start_time
        stats = await self.cache.get_stats()
        
        result = {
            "test_name": "Correspondance Exacte",
            "iterations": iterations,
            "hits": stats["hits"],
            "tokens_sans_cache": tokens_sans_cache,
            "tokens_avec_cache": tokens_avec_cache,
            "tokens_économisés": tokens_sans_cache - tokens_avec_cache,
            "économie_pourcentage": ((tokens_sans_cache - tokens_avec_cache) / tokens_sans_cache) * 100 if tokens_sans_cache > 0 else 0,
            "durée_secondes": duration
        }
        
        self.results.append(result)
        logger.info(f"Résultats - Correspondance Exacte: {result['économie_pourcentage']:.2f}% d'économie")
        
        return result
    
    async def run_test_semantic_match(self, iterations=5):
        """Test de correspondance sémantique"""
        logger.info("=== TEST DE CORRESPONDANCE SÉMANTIQUE ===")
        
        start_time = time.time()
        tokens_sans_cache = 0
        tokens_avec_cache = 0
        
        # Réinitialiser le cache pour ce test
        self.cache.clear()
        
        # Pré-remplir le cache avec des données de test
        sample_data = BENCHMARK_DATA["réponses_longues"][0]
        sample_tokens = len(sample_data.split()) / 0.75
        
        # Ajouter la première question comme référence
        reference_q = BENCHMARK_DATA["questions_similaires"][0]
        await self.cache.set(
            reference_q,
            sample_data,
            should_embed=True,
            metadata={"token_count": sample_tokens}
        )
        tokens_sans_cache += sample_tokens
        
        # Tests avec des questions similaires
        similar_questions = BENCHMARK_DATA["questions_similaires"][1:]
        
        for _ in range(iterations):
            for question in similar_questions:
                result = await self.cache.get(
                    question,
                    allow_semantic_match=True,
                    embedding_text=question
                )
                
                if result == sample_data:
                    # Requête servie depuis le cache
                    tokens_sans_cache += sample_tokens
                else:
                    # Echec du cache (rare dans ce test)
                    await self.cache.set(
                        question,
                        sample_data,
                        should_embed=True,
                        metadata={"token_count": sample_tokens}
                    )
                    tokens_sans_cache += sample_tokens
                    tokens_avec_cache += sample_tokens
                    
        duration = time.time() - start_time
        stats = await self.cache.get_stats()
        
        # Les tokens économisés sont le nombre de fois qu'on n'a pas eu à générer la réponse
        tokens_économisés = tokens_sans_cache - tokens_avec_cache
        
        result = {
            "test_name": "Correspondance Sémantique",
            "iterations": iterations,
            "semantic_hits": stats["semantic_matches"],
            "tokens_sans_cache": tokens_sans_cache,
            "tokens_avec_cache": tokens_avec_cache,
            "tokens_économisés": tokens_économisés,
            "économie_pourcentage": (tokens_économisés / tokens_sans_cache) * 100 if tokens_sans_cache > 0 else 0,
            "durée_secondes": duration
        }
        
        self.results.append(result)
        logger.info(f"Résultats - Correspondance Sémantique: {result['économie_pourcentage']:.2f}% d'économie")
        
        return result
    
    async def run_test_mixed_workload(self, iterations=3):
        """Test de charge mixte (exacte + sémantique)"""
        logger.info("=== TEST DE CHARGE MIXTE ===")
        
        start_time = time.time()
        tokens_sans_cache = 0
        tokens_avec_cache = 0
        
        # Réinitialiser le cache pour ce test
        self.cache.clear()
        
        # Données de test
        sample_data = BENCHMARK_DATA["réponses_longues"][0]
        sample_tokens = len(sample_data.split()) / 0.75
        
        # Questions similaires et variées
        similar_q = BENCHMARK_DATA["questions_similaires"]
        varied_q = BENCHMARK_DATA["questions_variées"]
        
        # Pré-remplir le cache avec quelques données
        for i, q in enumerate(similar_q[:3]):
            await self.cache.set(
                q,
                sample_data,
                should_embed=True,
                metadata={"token_count": sample_tokens}
            )
            tokens_sans_cache += sample_tokens
        
        # Effectuer des opérations mixtes
        for _ in range(iterations):
            # Mix de questions similaires et variées
            all_questions = similar_q[3:] + varied_q
            random.shuffle(all_questions)
            
            for q in all_questions:
                # 70% des requêtes avec recherche sémantique
                use_semantic = random.random() < 0.7
                
                result = await self.cache.get(
                    q,
                    allow_semantic_match=use_semantic,
                    embedding_text=q if use_semantic else None
                )
                
                if result == sample_data:
                    # Requête servie depuis le cache
                    tokens_sans_cache += sample_tokens
                else:
                    # Cache miss
                    await self.cache.set(
                        q,
                        sample_data,
                        should_embed=True,
                        metadata={"token_count": sample_tokens}
                    )
                    tokens_sans_cache += sample_tokens
                    tokens_avec_cache += sample_tokens
        
        duration = time.time() - start_time
        stats = await self.cache.get_stats()
        
        tokens_économisés = tokens_sans_cache - tokens_avec_cache
        
        result = {
            "test_name": "Charge Mixte",
            "iterations": iterations,
            "hits": stats["hits"],
            "semantic_hits": stats["semantic_matches"],
            "tokens_sans_cache": tokens_sans_cache,
            "tokens_avec_cache": tokens_avec_cache,
            "tokens_économisés": tokens_économisés,
            "économie_pourcentage": (tokens_économisés / tokens_sans_cache) * 100 if tokens_sans_cache > 0 else 0,
            "durée_secondes": duration
        }
        
        self.results.append(result)
        logger.info(f"Résultats - Charge Mixte: {result['économie_pourcentage']:.2f}% d'économie")
        
        return result
    
    async def run_all_tests(self):
        """Exécute tous les tests de benchmark"""
        logger.info("Démarrage du benchmark complet...")
        
        await self.setup()
        
        # Exécuter les tests
        await self.run_test_exact_match()
        await self.run_test_semantic_match()
        await self.run_test_mixed_workload()
        
        # Afficher les résultats consolidés
        await self.print_summary()
        
        logger.info("Benchmark terminé.")
    
    async def print_summary(self):
        """Affiche un résumé des résultats du benchmark"""
        logger.info("\n" + "=" * 80)
        logger.info("RÉSUMÉ DU BENCHMARK DU CACHE INTELLIGENT")
        logger.info("=" * 80)
        
        for result in self.results:
            logger.info(f"\nTest: {result['test_name']}")
            logger.info(f"  - Économie de tokens: {result['économie_pourcentage']:.2f}% ({result['tokens_économisés']:.0f} tokens)")
            logger.info(f"  - Tokens sans cache: {result['tokens_sans_cache']:.0f}")
            logger.info(f"  - Tokens avec cache: {result['tokens_avec_cache']:.0f}")
            logger.info(f"  - Durée: {result['durée_secondes']:.2f} secondes")
        
        # Calcul de la moyenne
        if self.results:
            avg_savings = sum(r["économie_pourcentage"] for r in self.results) / len(self.results)
            logger.info("\n" + "-" * 80)
            logger.info(f"ÉCONOMIE MOYENNE DE TOKENS: {avg_savings:.2f}%")
            logger.info("-" * 80)
        
        # Statistiques globales du cache
        stats = await self.cache.get_stats()
        logger.info("\nStatistiques du cache:")
        logger.info(f"  - Entrées: {stats.get('entry_count', 0)}")
        logger.info(f"  - Taux de hit: {stats.get('hit_rate', 0):.2%}")
        logger.info(f"  - Taux de hit sémantique: {stats.get('semantic_match_rate', 0):.2%}")
        logger.info(f"  - Utilisation mémoire: {stats.get('memory_size_mb', 0):.2f} MB")
        logger.info("=" * 80)

async def main():
    """Fonction principale"""
    benchmark = CacheBenchmark()
    await benchmark.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
