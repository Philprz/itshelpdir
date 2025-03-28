"""
Script d'exécution des tests des services d'embedding

Ce script exécute les tests unitaires des services d'embedding
et génère un rapport des résultats.
"""

import os
import sys
import unittest
# Corriger l'importation pour pointer vers le bon chemin
from src.adapters.embeddings.tests.test_embeddings import TestEmbeddingServices

def run_tests():
    """Exécute tous les tests des services d'embedding"""
    print("=" * 80)
    print("TESTS DES SERVICES D'EMBEDDING")
    print("=" * 80)
    
    # Créer le test runner
    runner = unittest.TextTestRunner(verbosity=2)
    
    # Exécuter les tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEmbeddingServices)
    result = runner.run(suite)
    
    # Afficher le résumé
    print("\n" + "=" * 80)
    print(f"RÉSUMÉ: {result.testsRun} tests exécutés, {len(result.errors)} erreurs, {len(result.failures)} échecs")
    print("=" * 80)
    
    # Retourner un code de sortie basé sur le résultat
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    # Exécuter les tests et sortir avec le code approprié
    sys.exit(run_tests())
