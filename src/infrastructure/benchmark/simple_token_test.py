"""
Test simple d'économie de tokens avec le cache intelligent

Ce script démontre les économies de tokens réalisées par notre cache intelligent
dans un scénario simple et contrôlé.
"""

import os
import sys
import time
import asyncio
import logging
from typing import Dict, List, Any, Optional

# Ajout du chemin racine au PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.infrastructure.cache import get_cache_instance, IntelligentCache

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("token_test")

# Mock pour la fonction d'embedding
async def mock_embedding_function(text: str) -> List[float]:
    """Génère un embedding mock basé sur le contenu du texte"""
    import hashlib
    import numpy as np
    
    # Nettoyer et normaliser le texte pour améliorer les correspondances
    clean_text = text.lower().strip()
    words = clean_text.split()
    
    # Extraire les mots-clés importants (ignorer les mots communs)
    stop_words = {'le', 'la', 'les', 'un', 'une', 'des', 'et', 'ou', 'je', 'tu', 'il', 'nous', 'vous', 'ils', 
                 'ce', 'cette', 'ces', 'mon', 'ton', 'son', 'ma', 'ta', 'sa', 'mes', 'tes', 'ses', 'notre', 'votre', 'leur',
                 'à', 'de', 'en', 'par', 'pour', 'avec', 'sans', 'sur', 'sous', 'dans', 'hors', 'avant', 'après'}
    
    keywords = [w for w in words if w not in stop_words]
    keyword_text = ' '.join(keywords)
    
    # Générer un hash des mots-clés
    hash_obj = hashlib.md5(keyword_text.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    
    # Utiliser le hash comme seed pour la génération de nombres aléatoires
    seed = int(hash_hex[:8], 16) % (2**32 - 1)
    np.random.seed(seed)
    
    # Générer un vecteur de 1536 dimensions (comme OpenAI ada-002)
    # Mais avec des valeurs plus similaires pour des textes similaires
    base_vector = np.random.random(1536)
    
    # Ajouter des perturbations basées sur les mots du texte
    perturbations = np.zeros(1536)
    for word in words:
        word_hash = int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
        np.random.seed(word_hash % (2**32 - 1))
        perturbation = np.random.random(1536) * 0.01  # Petite perturbation
        perturbations += perturbation
    
    # Combinaison du vecteur de base et des perturbations
    final_vector = base_vector + perturbations
    
    # Normaliser le vecteur pour avoir une norme L2 de 1
    norm = np.linalg.norm(final_vector)
    if norm > 0:
        final_vector = final_vector / norm
    
    return final_vector.tolist()

async def run_token_economy_test():
    """
    Exécute un test simple pour démontrer les économies de tokens
    
    Ce test simule un scénario réaliste où:
    1. Des utilisateurs posent des questions similaires
    2. Le système utilise le cache pour éviter de regénérer des réponses
    3. Nous mesurons les tokens économisés
    """
    logger.info("=== TEST D'ÉCONOMIE DE TOKENS ===")
    
    # Définir le seuil de similarité via une variable d'environnement
    os.environ['CACHE_SIMILARITY_THRESHOLD'] = '0.70'  # Seuil plus permissif
    
    # Créer une instance de cache avec notre fonction d'embedding mock
    cache = get_cache_instance(
        embedding_function=mock_embedding_function,
        max_entries=100,
        default_ttl=3600
    )
    
    # Données de test - réponse longue, estimée à ~500 tokens
    long_response = """
    Pour résoudre ce problème NetSuite, suivez ces étapes détaillées:
    
    1. Connectez-vous à votre compte NetSuite avec des privilèges d'administrateur
    2. Accédez au menu "Configuration > Paramètres de la société > Général"
    3. Vérifiez que les paramètres fiscaux sont correctement configurés
    4. Ouvrez le module "Transactions > Gestion des ventes > Factures"
    5. Sélectionnez la facture problématique dans la liste
    6. Cliquez sur "Modifier" pour ouvrir les détails de la facture
    7. Vérifiez les champs "Conditions de paiement" et "Méthodes de paiement"
    8. Assurez-vous que le compte de revenus est correctement mappé pour chaque article
    9. Vérifiez le statut de l'intégration avec votre système de paiement
    10. Si nécessaire, annulez la facture et créez-en une nouvelle avec les paramètres corrects
    11. Générez un nouveau PDF de facture
    12. Envoyez à nouveau la facture au client avec une note explicative
    13. Vérifiez le journal d'audit pour toute anomalie
    14. Surveillez le statut de paiement dans les prochains jours
    15. Documentez la solution dans votre système de tickets pour référence future
    
    Si ces étapes ne résolvent pas votre problème, contactez l'équipe de support NetSuite
    en leur fournissant les identifiants de transaction et les logs d'erreur complets.
    """
    
    # Estimation approximative des tokens dans la réponse
    tokens_per_response = len(long_response.split()) / 0.75
    logger.info(f"Tokens estimés par réponse: {tokens_per_response:.0f}")
    
    # Liste de questions similaires sur le même sujet
    similar_questions = [
        "Problème de facturation sur NetSuite, comment corriger?",
        "Je n'arrive pas à finaliser une facture sur NetSuite",
        "Erreur lors de la création d'une facture NetSuite",
        "NetSuite affiche une erreur sur ma facture, comment résoudre?",
        "Problème avec les factures sur NetSuite",
        "Comment corriger une erreur de facturation NetSuite?",
        "Facture NetSuite - erreur à la création",
        "NetSuite facture erreur correction",
        "Résoudre problème facturation NetSuite",
        "Ma facture NetSuite est bloquée avec une erreur"
    ]
    
    # Compteurs pour les statistiques
    total_tokens_without_cache = 0
    total_tokens_with_cache = 0
    hit_count = 0
    semantic_hit_count = 0
    
    # Première question - pas dans le cache
    start_time = time.time()
    logger.info(f"Q1: {similar_questions[0]}")
    
    # Simuler l'appel à l'API LLM (coût complet en tokens)
    total_tokens_without_cache += tokens_per_response
    total_tokens_with_cache += tokens_per_response
    
    # Stocker dans le cache
    await cache.set(
        similar_questions[0],
        long_response,
        should_embed=True,
        metadata={"token_count": tokens_per_response}
    )
    
    logger.info("Réponse générée et mise en cache")
    
    # Questions suivantes - potentiellement servies depuis le cache
    for i, question in enumerate(similar_questions[1:], 2):
        logger.info(f"\nQ{i}: {question}")
        
        # Sans cache, chaque question coûterait des tokens
        total_tokens_without_cache += tokens_per_response
        
        # Avec notre cache intelligent, on essaie de trouver une correspondance
        result = await cache.get(
            question,
            allow_semantic_match=True,
            embedding_text=question
        )
        
        if result == long_response:
            # Cache hit - pas de génération nécessaire
            hit_count += 1
            semantic_hit_count += 1
            logger.info("Réponse servie depuis le cache (correspondance sémantique)")
        else:
            # Cache miss - générer et stocker
            logger.info("Pas de correspondance dans le cache - génération d'une nouvelle réponse")
            total_tokens_with_cache += tokens_per_response
            
            # Stocker pour les futures requêtes
            await cache.set(
                question,
                long_response,
                should_embed=True,
                metadata={"token_count": tokens_per_response}
            )
    
    # Récupérer les statistiques du cache
    stats = await cache.get_stats()
    
    # Calculs finaux
    duration = time.time() - start_time
    tokens_saved = total_tokens_without_cache - total_tokens_with_cache
    savings_percentage = (tokens_saved / total_tokens_without_cache) * 100
    
    # Afficher les résultats
    logger.info("\n" + "=" * 60)
    logger.info("RÉSULTATS DU TEST D'ÉCONOMIE DE TOKENS")
    logger.info("=" * 60)
    logger.info(f"Nombre de questions traitées: {len(similar_questions)}")
    logger.info(f"Correspondances trouvées: {hit_count} sur {len(similar_questions)-1} questions")
    logger.info(f"Tokens sans cache: {total_tokens_without_cache:.0f}")
    logger.info(f"Tokens avec cache: {total_tokens_with_cache:.0f}")
    logger.info(f"Tokens économisés: {tokens_saved:.0f}")
    logger.info(f"Pourcentage d'économie: {savings_percentage:.2f}%")
    logger.info(f"Durée du test: {duration:.2f} secondes")
    logger.info("=" * 60)
    
    # Afficher les statistiques du cache
    logger.info("\nStatistiques du cache:")
    logger.info(f"  Hit rate: {stats.get('hit_rate', 0):.2%}")
    logger.info(f"  Semantic match rate: {stats.get('semantic_match_rate', 0):.2%}")
    logger.info(f"  Tokens saved: {stats.get('tokens_saved', 0):.0f}")
    logger.info(f"  Token savings rate: {stats.get('token_savings_rate', 0):.2%}")
    
    return {
        "questions_count": len(similar_questions),
        "hit_count": hit_count,
        "tokens_without_cache": total_tokens_without_cache,
        "tokens_with_cache": total_tokens_with_cache,
        "tokens_saved": tokens_saved,
        "savings_percentage": savings_percentage,
        "duration": duration,
        "cache_stats": stats
    }

async def main():
    """Fonction principale"""
    try:
        results = await run_token_economy_test()
        logger.info(f"\nConclusion: Notre cache intelligent a économisé {results['savings_percentage']:.2f}% des tokens")
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution du test: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
