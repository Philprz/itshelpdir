"""
Script d'exécution des tests des adaptateurs vectoriels

Ce script exécute les tests unitaires des adaptateurs de bases de données vectorielles
et génère un rapport des résultats.
"""

import os
import sys
import unittest
# Corriger l'importation pour pointer vers le bon chemin
from src.adapters.vector_stores.tests.test_vector_stores import TestVectorStoreAdapters

def run_tests():
    """Exécute tous les tests des adaptateurs vectoriels"""
    print("=" * 80)
    print("TESTS DES ADAPTATEURS VECTORIELS")
    print("=" * 80)
    
    # Créer le test runner
    runner = unittest.TextTestRunner(verbosity=2)
    
    # Exécuter les tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVectorStoreAdapters)
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
