#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de nettoyage automatisé pour le projet ITS_HELP_DIRECT

Ce script effectue les opérations suivantes:
1. Crée une branche Git pour le nettoyage
2. Archive les anciens scripts et backups
3. Supprime les fichiers redondants ou temporaires
4. Documente les changements dans un fichier CLEANUP.md

Usage:
    python cleanup_project.py [--dry-run] [--no-git]

Options:
    --dry-run    Simule les opérations sans les exécuter
    --no-git     Ne crée pas de branche Git pour le nettoyage
"""

import os
import sys
import shutil
import argparse
import subprocess
import logging
from datetime import datetime
from pathlib import Path
import zipfile

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('cleanup')

# Répertoire racine du projet
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Liste des fichiers à supprimer
FILES_TO_DELETE = [
    # Tests et fichiers de débogage redondants
    "test_serialization.py",
    "test_qdrant_simple.py",
    "list_qdrant_collections.py",
    "cache_benchmark_results.txt",
    "direct_search_results.json",
    "diagnostic_clients.log",
    "interface_fix.log",
    "run_unit_tests.py",
    
    # Scripts de démarrage redondants
    "start_windows.bat",
    "start_windows.ps1",
    "run_app.py",
    
    # Documentation obsolète
    "MIGRATION_PLAN.md",
    "erp_collections_recommendations.txt",
]

# Dossiers à supprimer
DIRS_TO_DELETE = [
    # Backups et anciennes versions
    "backup_20250326_085146",
    "backup_20250326_085355",
    
    # Fichiers compilés et caches
    "__pycache__",
    ".pytest_cache"
]

# Dossiers à archiver
DIRS_TO_ARCHIVE = [
    "archive_scripts"
]

def run_command(command, dry_run=False):
    """
    Exécute une commande shell
    
    Args:
        command: Liste contenant la commande et ses arguments
        dry_run: Si True, affiche la commande sans l'exécuter
        
    Returns:
        Résultat de la commande ou None si dry_run est True
    """
    cmd_str = " ".join(command)
    if dry_run:
        logger.info(f"[DRY-RUN] Commande: {cmd_str}")
        return None
    
    logger.info(f"Exécution: {cmd_str}")
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur lors de l'exécution de {cmd_str}: {str(e)}")
        logger.error(f"STDERR: {e.stderr}")
        return None

def create_git_branch(branch_name, dry_run=False):
    """Crée une branche Git pour le nettoyage"""
    # Vérifier si Git est installé
    result = run_command(["git", "--version"], dry_run)
    if result is None and not dry_run:
        logger.error("Git n'est pas installé ou accessible. Abandon de la création de branche.")
        return False
        
    # Créer la branche
    logger.info(f"Création de la branche Git: {branch_name}")
    run_command(["git", "checkout", "-b", branch_name], dry_run)
    
    return True

def archive_directories(dirs_to_archive, archive_name, dry_run=False):
    """Archive les dossiers spécifiés dans un fichier ZIP"""
    if not dirs_to_archive:
        return True
        
    # Vérifier que les dossiers existent
    valid_dirs = []
    for dir_path in dirs_to_archive:
        full_path = os.path.join(PROJECT_ROOT, dir_path)
        if os.path.isdir(full_path):
            valid_dirs.append(dir_path)
        else:
            logger.warning(f"Dossier non trouvé, ignoré: {dir_path}")
            
    if not valid_dirs:
        logger.warning("Aucun dossier valide à archiver")
        return True
    
    # Créer le nom d'archive avec la date
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(PROJECT_ROOT, f"{archive_name}_{timestamp}.zip")
    
    if dry_run:
        logger.info(f"[DRY-RUN] Création de l'archive: {archive_path}")
        logger.info(f"[DRY-RUN] Contenu de l'archive: {valid_dirs}")
        return True
        
    try:
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for dir_path in valid_dirs:
                full_dir_path = os.path.join(PROJECT_ROOT, dir_path)
                
                # Ajouter tous les fichiers du dossier à l'archive
                for root, _, files in os.walk(full_dir_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, PROJECT_ROOT)
                        zipf.write(file_path, arcname)
                        
        logger.info(f"Archive créée avec succès: {archive_path}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la création de l'archive: {str(e)}")
        return False

def delete_files(files_to_delete, dry_run=False):
    """Supprime les fichiers spécifiés"""
    success = True
    
    for file_path in files_to_delete:
        full_path = os.path.join(PROJECT_ROOT, file_path)
        if os.path.exists(full_path):
            if dry_run:
                logger.info(f"[DRY-RUN] Suppression: {file_path}")
            else:
                try:
                    if os.path.isdir(full_path):
                        shutil.rmtree(full_path)
                    else:
                        os.remove(full_path)
                    logger.info(f"Supprimé: {file_path}")
                except Exception as e:
                    logger.error(f"Erreur lors de la suppression de {file_path}: {str(e)}")
                    success = False
        else:
            logger.warning(f"Fichier/dossier non trouvé, ignoré: {file_path}")
            
    return success

def delete_directories(dirs_to_delete, dry_run=False):
    """Supprime récursivement les dossiers spécifiés"""
    success = True
    
    for dir_pattern in dirs_to_delete:
        # Recherche récursive pour les motifs comme "__pycache__"
        for root, dirs, _ in os.walk(PROJECT_ROOT):
            if ".git" in root:  # Ignorer le répertoire .git
                continue
                
            for d in dirs:
                if d == dir_pattern or d.startswith(dir_pattern):
                    full_path = os.path.join(root, d)
                    if dry_run:
                        logger.info(f"[DRY-RUN] Suppression du dossier: {full_path}")
                    else:
                        try:
                            shutil.rmtree(full_path)
                            logger.info(f"Dossier supprimé: {full_path}")
                        except Exception as e:
                            logger.error(f"Erreur lors de la suppression de {full_path}: {str(e)}")
                            success = False
                            
    return success

def create_cleanup_doc(deleted_files, deleted_dirs, archived_dirs, dry_run=False):
    """Crée un fichier markdown documentant les changements effectués"""
    doc_path = os.path.join(PROJECT_ROOT, "CLEANUP.md")
    
    content = f"""# Nettoyage du projet ITS_HELP_DIRECT

Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Ce document liste les fichiers et dossiers qui ont été nettoyés lors de la refactorisation 
du projet ITS_HELP_DIRECT pour améliorer sa maintenabilité et sa performance.

## Fichiers supprimés

Les fichiers suivants ont été identifiés comme redondants, obsolètes ou temporaires
et ont été supprimés du projet:

"""
    
    for file_path in deleted_files:
        content += f"- `{file_path}`\n"
        
    content += "\n## Dossiers supprimés\n\n"
    
    for dir_path in deleted_dirs:
        content += f"- `{dir_path}`/\n"
        
    content += "\n## Dossiers archivés\n\n"
    
    for dir_path in archived_dirs:
        content += f"- `{dir_path}`/\n"
        
    content += """
## Impact sur le projet

Ce nettoyage n'affecte pas le fonctionnement du programme principal.
Il a simplement permis de:

1. Supprimer les fichiers temporaires et de test redondants
2. Archiver les anciennes versions des composants
3. Éliminer les scripts de démarrage redondants
4. Supprimer les fichiers de documentation obsolètes

Ces changements permettent de réduire la taille du projet et de clarifier sa structure.
"""
    
    if dry_run:
        logger.info(f"[DRY-RUN] Création du fichier: {doc_path}")
        logger.info(f"[DRY-RUN] Contenu du fichier CLEANUP.md:\n{content[:300]}...")
        return True
        
    try:
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Documentation de nettoyage créée: {doc_path}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la création de la documentation: {str(e)}")
        return False

def main():
    """Fonction principale du script"""
    parser = argparse.ArgumentParser(description="Script de nettoyage automatisé pour le projet ITS_HELP_DIRECT")
    parser.add_argument("--dry-run", action="store_true", help="Simule les opérations sans les exécuter")
    parser.add_argument("--no-git", action="store_true", help="Ne crée pas de branche Git")
    args = parser.parse_args()
    
    dry_run = args.dry_run
    use_git = not args.no_git
    
    if dry_run:
        logger.info("*** MODE SIMULATION ACTIVÉ - Aucune modification ne sera effectuée ***")
    
    # Confirmation de l'utilisateur
    if not dry_run:
        confirm = input("Cette opération va supprimer des fichiers et dossiers du projet. Continuer? (y/N): ")
        if confirm.lower() != 'y':
            logger.info("Opération annulée par l'utilisateur.")
            return
    
    # 1. Créer une branche Git si demandé
    branch_created = False
    if use_git:
        branch_name = f"cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        branch_created = create_git_branch(branch_name, dry_run)
    
    # 2. Archiver les dossiers spécifiés
    archive_success = archive_directories(DIRS_TO_ARCHIVE, "archived_components", dry_run)
    
    # 3. Supprimer les fichiers et dossiers
    files_deleted = delete_files(FILES_TO_DELETE, dry_run)
    dirs_deleted = delete_directories(DIRS_TO_DELETE, dry_run)
    
    # Si archivage réussi, supprimer les dossiers archivés
    if archive_success and not dry_run:
        dirs_archived = DIRS_TO_ARCHIVE.copy()
        delete_files(DIRS_TO_ARCHIVE, dry_run)
    else:
        dirs_archived = []
    
    # 4. Créer la documentation du nettoyage
    doc_created = create_cleanup_doc(FILES_TO_DELETE, DIRS_TO_DELETE, dirs_archived, dry_run)
    
    # Résumé des opérations
    logger.info("\n*** RÉSUMÉ DES OPÉRATIONS ***")
    
    if use_git:
        status = "Créée" if branch_created else "ÉCHEC"
        logger.info(f"Branche Git: {status}")
        
    status = "Réussi" if archive_success else "ÉCHEC"
    logger.info(f"Archivage des dossiers: {status}")
    
    status = "Réussi" if files_deleted else "ÉCHEC"
    logger.info(f"Suppression des fichiers: {status}")
    
    status = "Réussi" if dirs_deleted else "ÉCHEC" 
    logger.info(f"Suppression des dossiers: {status}")
    
    status = "Créée" if doc_created else "ÉCHEC"
    logger.info(f"Documentation: {status}")
    
    # Message final
    if dry_run:
        logger.info("\nMode simulation terminé. Exécutez sans --dry-run pour effectuer les modifications.")
    else:
        if branch_created and use_git:
            logger.info(f"\nOpération terminée avec succès sur la branche {branch_name}.")
            logger.info("Vérifiez les modifications avec 'git status' puis validez avec 'git commit -m \"Nettoyage du projet\"'")
        else:
            logger.info("\nOpération terminée.")

if __name__ == "__main__":
    main()
