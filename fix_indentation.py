# fix_indentation.py
# Script pour corriger l'erreur d'indentation dans le fichier gestion_clients.py

import os
import re
import logging
import sys

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("fix_indentation.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.fix_indentation")

def fix_extract_client_name():
    """Corrige l'erreur d'indentation dans extract_client_name"""
    file_path = "gestion_clients.py"
    
    try:
        # Lire le fichier
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Chercher la ligne qui contient "message_clean = normalize_string(message)"
        normalize_line_idx = None
        for i, line in enumerate(lines):
            if "message_clean = normalize_string(message)" in line:
                normalize_line_idx = i
                break
        
        if normalize_line_idx is None:
            logger.error("Ligne 'message_clean = normalize_string(message)' non trouvée dans gestion_clients.py")
            return False
        
        # Déterminer l'indentation correcte
        normalize_line = lines[normalize_line_idx]
        correct_indent = " " * (len(normalize_line) - len(normalize_line.lstrip()))
        
        # Corriger la section problématique
        # Trouver où commence la section problématique - doit être après normalize_line_idx
        rondot_section_start = None
        for i in range(normalize_line_idx + 1, len(lines)):
            if "# Détection explicite de RONDOT" in lines[i]:
                rondot_section_start = i
                break
        
        if rondot_section_start is None:
            logger.error("Section de détection RONDOT non trouvée")
            return False
        
        # Corriger l'indentation de toute la section RONDOT (5 lignes)
        for i in range(rondot_section_start, min(rondot_section_start + 5, len(lines))):
            line_content = lines[i].lstrip()
            lines[i] = correct_indent + line_content
        
        # Écrire le fichier modifié
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        logger.info(f"gestion_clients.py corrigé avec succès")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la correction de {file_path}: {str(e)}")
        return False

def main():
    """Fonction principale du script"""
    print("🔧 Correction de l'erreur d'indentation dans gestion_clients.py")
    print("=========================================================\n")
    
    try:
        # Corriger l'erreur d'indentation dans extract_client_name
        print("Correction de l'erreur d'indentation dans extract_client_name...")
        if fix_extract_client_name():
            print("✅ gestion_clients.py corrigé avec succès")
        else:
            print("❌ Échec de la correction de gestion_clients.py")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()
