# fix_if_block.py
# Script pour corriger l'indentation du bloc 'if' dans gestion_clients.py

import os
import logging
import sys

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("fix_if_block.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.fix_if_block")

def fix_if_block_indentation():
    """Corrige l'indentation du bloc if"""
    file_path = "gestion_clients.py"
    
    try:
        # Lire le fichier
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Trouver la ligne avec l'instruction if RONDOT
        rondot_if_line_idx = None
        for i, line in enumerate(lines):
            if "if 'RONDOT' in message_clean.upper():" in line:
                rondot_if_line_idx = i
                break
        
        if rondot_if_line_idx is None:
            logger.error("Ligne 'if RONDOT' non trouvée dans gestion_clients.py")
            return False
        
        # Déterminer l'indentation correcte pour le bloc if
        current_indent = len(lines[rondot_if_line_idx]) - len(lines[rondot_if_line_idx].lstrip())
        block_indent = current_indent + 4  # Ajout de 4 espaces pour le bloc interne
        
        # Corriger l'indentation des lignes suivant le if
        rondot_return_idx = None
        for i in range(rondot_if_line_idx + 1, len(lines)):
            if "return 'RONDOT'" in lines[i]:
                rondot_return_idx = i
                break
        
        if rondot_return_idx is None:
            logger.error("Instruction return pour RONDOT non trouvée")
            return False
        
        # Corriger les indentations pour les lignes entre if et return
        for i in range(rondot_if_line_idx + 1, rondot_return_idx + 1):
            content = lines[i].lstrip()
            lines[i] = " " * block_indent + content
        
        # Écrire le fichier modifié
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        logger.info("Bloc if corrigé avec succès dans gestion_clients.py")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la correction du bloc if: {str(e)}")
        return False

def main():
    """Fonction principale du script"""
    print("🔧 Correction de l'indentation du bloc if dans gestion_clients.py")
    print("===========================================================\n")
    
    try:
        if fix_if_block_indentation():
            print("✅ Bloc if corrigé avec succès dans gestion_clients.py")
        else:
            print("❌ Échec de la correction du bloc if")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()
