#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
run_unit_tests.py
Script pour exécuter les tests unitaires des clients de recherche.
Conformément aux conventions du projet, les imports sont effectués après 
le chargement des variables d'environnement.
"""

import sys
import logging
from dotenv import load_dotenv

# Chargement des variables d'environnement AVANT toute importation spécifique
load_dotenv(verbose=True)
print("\nVariables d'environnement chargées.\n")
print("="*80 + "\n")

# Configuration du logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('ITS_HELP.tests')

# Import des modules après chargement des variables d'environnement
import pytest  # noqa: E402

def print_section(title):
    """Affiche un titre de section formaté"""
    print("\n" + "="*80)
    print(title.upper().center(80))
    print("="*80 + "\n")

def run_tests():
    """
    Exécute tous les tests unitaires pour les clients de recherche.
    """
    print_section("EXÉCUTION DES TESTS UNITAIRES DES CLIENTS DE RECHERCHE")
    
    try:
        # Détection des arguments de ligne de commande
        args = sys.argv[1:] if len(sys.argv) > 1 else []
        
        # Arguments par défaut pour pytest
        default_args = [
            "-v",  # Mode verbeux
            "--color=yes",  # Activer la couleur
        ]
        
        # Tests spécifiques à un client si spécifié
        if "--jira" in args:
            args.remove("--jira")
            default_args.append("tests/clients/test_jira_client.py")
            print("Exécution des tests unitaires pour le client JIRA uniquement.")
        elif "--netsuite-dummies" in args:
            args.remove("--netsuite-dummies")
            default_args.append("tests/clients/test_netsuite_dummies_client.py")
            print("Exécution des tests unitaires pour le client NetSuite Dummies uniquement.")
        elif "--erp" in args:
            args.remove("--erp")
            default_args.append("tests/clients/test_erp_client.py")
            print("Exécution des tests unitaires pour le client ERP uniquement.")
        elif "--confluence" in args:
            args.remove("--confluence")
            default_args.append("tests/clients/test_confluence_client.py")
            print("Exécution des tests unitaires pour le client Confluence uniquement.")
        else:
            print("Exécution de tous les tests unitaires des clients de recherche.")
        
        # Fusionner les arguments par défaut avec ceux passés en ligne de commande
        pytest_args = default_args + args
        
        # Exécution de pytest avec les arguments
        exit_code = pytest.main(pytest_args)
        
        # Afficher le résultat global
        if exit_code == 0:
            print_section("TOUS LES TESTS ONT RÉUSSI")
        else:
            print_section(f"CERTAINS TESTS ONT ÉCHOUÉ (Code: {exit_code})")
            
        return exit_code
        
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution des tests: {str(e)}", exc_info=True)
        print(f"\n❌ ERREUR CRITIQUE: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
