#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fix_collection_case.py
Script pour harmoniser la casse des noms de collections entre le code et Qdrant.
"""

import os
import re
import logging
from typing import Dict, List, Set, Tuple
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('ITS_HELP.fix_case')

# Chargement des variables d'environnement
load_dotenv(verbose=True)

# Liste des fichiers à analyser (à adapter selon le projet)
FILES_TO_SCAN = [
    'chatbot.py',
    'search_factory.py',
    'search_clients.py',
    'search_base.py',
    'test_analyze_question.py',
    'test_erp_search.py',
]

# Motifs regex pour trouver les références aux collections
COLLECTION_PATTERNS = [
    r'collection_name\s*=\s*[\'"]([^\'"]+)[\'"]',  # collection_name = "NETSUITE"
    r'collection_name\.upper\(\)\s*==\s*[\'"]([^\'"]+)[\'"]',  # collection_name.upper() == "NETSUITE"
    r'collection_name\s*==\s*[\'"]([^\'"]+)[\'"]',  # collection_name == "NETSUITE"
    r'get_client\([\'"]([^\'"]+)[\'"]\)',  # get_client("netsuite")
    r'\.get\([\'"]([^\'"]+)[\'"]\)',  # .get("netsuite")
    r'[\'"]source_type[\'"]\s*:\s*[\'"]([^\'"]+)[\'"]',  # "source_type": "netsuite"
    r'sources\s*=\s*\[[^\]]*[\'"]([^\'"]+)[\'"]',  # sources = ["NETSUITE", ...
]

def get_qdrant_collections() -> List[str]:
    """
    Récupère la liste des collections Qdrant existantes.
    
    Returns:
        Liste des noms de collections dans Qdrant
    """
    try:
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not qdrant_url:
            logger.error("URL Qdrant manquante")
            return []
        
        qdrant_client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=10
        )
        
        collections = qdrant_client.get_collections()
        return [col.name for col in collections.collections]
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des collections Qdrant: {str(e)}")
        return []

def scan_files_for_collections() -> Set[str]:
    """
    Analyse les fichiers du projet pour trouver toutes les références aux collections.
    
    Returns:
        Ensemble des noms de collections trouvés dans le code
    """
    collections_found = set()
    
    for filename in FILES_TO_SCAN:
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                content = file.read()
                
                for pattern in COLLECTION_PATTERNS:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        # Ne garder que les collections qui semblent être des ERP
                        if match.lower() in ['netsuite', 'netsuite_dummies', 'sap']:
                            collections_found.add(match)
        except Exception as e:
            logger.warning(f"Erreur lors de l'analyse du fichier {filename}: {str(e)}")
    
    return collections_found

def analyze_collection_case() -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Analyse les incohérences de casse entre le code et Qdrant.
    
    Returns:
        Tuple de deux dictionnaires:
        1. Collections trouvées dans le code, regroupées par version en minuscules
        2. Collections trouvées dans Qdrant, regroupées par version en minuscules
    """
    # Collections dans le code
    code_collections = scan_files_for_collections()
    code_map = {}
    for col in code_collections:
        col_lower = col.lower()
        if col_lower not in code_map:
            code_map[col_lower] = []
        code_map[col_lower].append(col)
    
    # Collections dans Qdrant
    qdrant_collections = get_qdrant_collections()
    qdrant_map = {}
    for col in qdrant_collections:
        col_lower = col.lower()
        if col_lower not in qdrant_map:
            qdrant_map[col_lower] = []
        qdrant_map[col_lower].append(col)
    
    return code_map, qdrant_map

def propose_fixes(code_map: Dict[str, List[str]], qdrant_map: Dict[str, List[str]]) -> Dict[str, str]:
    """
    Propose des correctifs pour les problèmes de casse.
    
    Args:
        code_map: Collections trouvées dans le code
        qdrant_map: Collections trouvées dans Qdrant
        
    Returns:
        Dictionnaire des correctifs proposés (ancienne valeur -> nouvelle valeur)
    """
    fixes = {}
    
    # Trouver les collections avec plusieurs versions de casse dans le code
    for col_lower, variations in code_map.items():
        if len(variations) > 1:
            logger.warning(f"Collection {col_lower} a {len(variations)} variations de casse dans le code: {variations}")
            
            # Si la collection existe dans Qdrant, utiliser cette version
            if col_lower in qdrant_map:
                qdrant_version = qdrant_map[col_lower][0]
                for code_version in variations:
                    if code_version != qdrant_version:
                        fixes[code_version] = qdrant_version
            else:
                # Sinon, standardiser vers la version en majuscules
                upper_version = col_lower.upper()
                for code_version in variations:
                    if code_version != upper_version:
                        fixes[code_version] = upper_version
    
    # Trouver les collections qui existent dans le code mais avec une casse différente de Qdrant
    for col_lower in set(code_map.keys()).intersection(qdrant_map.keys()):
        code_versions = code_map[col_lower]
        qdrant_versions = qdrant_map[col_lower]
        
        if len(qdrant_versions) == 1:
            qdrant_version = qdrant_versions[0]
            for code_version in code_versions:
                if code_version != qdrant_version:
                    fixes[code_version] = qdrant_version
    
    return fixes

def apply_fixes(fixes: Dict[str, str]) -> None:
    """
    Applique les correctifs proposés aux fichiers du projet.
    
    Args:
        fixes: Dictionnaire des correctifs (ancienne valeur -> nouvelle valeur)
    """
    if not fixes:
        logger.info("Aucun correctif à appliquer.")
        return
    
    logger.info(f"Application de {len(fixes)} correctifs:")
    for old, new in fixes.items():
        logger.info(f"  {old} -> {new}")
    
    for filename in FILES_TO_SCAN:
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                content = file.read()
            
            modified = False
            new_content = content
            
            for old, new in fixes.items():
                # Remplacer les occurrences exactes (comme chaînes)
                patterns = [
                    f'"{old}"',
                    f"'{old}'",
                ]
                
                for pattern in patterns:
                    if pattern in new_content:
                        replacement = pattern.replace(old, new)
                        new_content = new_content.replace(pattern, replacement)
                        modified = True
            
            if modified:
                with open(filename, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                logger.info(f"✅ Fichier {filename} mis à jour.")
            else:
                logger.info(f"❌ Aucune modification dans {filename}.")
        except Exception as e:
            logger.error(f"Erreur lors de la modification du fichier {filename}: {str(e)}")

def main():
    """Fonction principale."""
    logger.info("Démarrage de l'analyse et correction des problèmes de casse des collections...")
    
    # Analyse des problèmes de casse
    code_map, qdrant_map = analyze_collection_case()
    
    # Affichage des résultats de l'analyse
    logger.info("\nCollections trouvées dans le code:")
    for col_lower, variations in code_map.items():
        logger.info(f"  {col_lower}: {variations}")
    
    logger.info("\nCollections trouvées dans Qdrant:")
    for col_lower, variations in qdrant_map.items():
        logger.info(f"  {col_lower}: {variations}")
    
    # Proposition et application des correctifs
    fixes = propose_fixes(code_map, qdrant_map)
    
    logger.info("\nCorrectifs proposés:")
    if fixes:
        for old, new in fixes.items():
            logger.info(f"  {old} -> {new}")
    else:
        logger.info("  Aucun correctif nécessaire.")
    
    # Demander confirmation avant d'appliquer les correctifs
    apply_fixes(fixes)
    
    logger.info("Analyse et correction terminées.")

if __name__ == "__main__":
    main()
