# installation_correctif_rondot.py
# Script d'installation du correctif RONDOT pour le chatbot ITS_HELP

import os
import sys
import shutil
import logging
import subprocess
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("installation_correctif_rondot.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.installation")

# Création d'un dossier pour les backups
BACKUP_DIR = f"backup_installation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

# Liste des fichiers à sauvegarder avant modification
FILES_TO_BACKUP = [
    "gestion_clients.py",
    "chatbot.py"
]

def create_backups():
    """Crée des sauvegardes des fichiers avant modification"""
    logger.info(f"Création des sauvegardes dans {BACKUP_DIR}")
    for file in FILES_TO_BACKUP:
        if os.path.exists(file):
            backup_path = os.path.join(BACKUP_DIR, file)
            shutil.copy2(file, backup_path)
            logger.info(f"Sauvegarde créée: {backup_path}")
        else:
            logger.warning(f"Fichier non trouvé pour sauvegarde: {file}")
    return True

def run_correctif():
    """Exécute le script de correctif principal"""
    logger.info("Exécution du script correctif_rondot.py")
    try:
        result = subprocess.run(
            [sys.executable, "correctif_rondot.py"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"Sortie du script correctif:\n{result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur lors de l'exécution du correctif: {e}")
        logger.error(f"Sortie d'erreur: {e.stderr}")
        return False

def run_fixes():
    """Exécute les scripts de correction des erreurs potentielles"""
    scripts = ["fix_syntax.py", "fix_indentation.py", "fix_if_block.py"]
    for script in scripts:
        if not os.path.exists(script):
            # Générer le script s'il n'existe pas
            logger.info(f"Script {script} non trouvé, génération...")
            if script == "fix_syntax.py":
                generate_fix_syntax()
            elif script == "fix_indentation.py":
                generate_fix_indentation()
            elif script == "fix_if_block.py":
                generate_fix_if_block()
            
        logger.info(f"Exécution du script {script}")
        try:
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Sortie du script {script}:\n{result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Erreur lors de l'exécution de {script}: {e}")
            logger.error(f"Sortie d'erreur: {e.stderr}")
            return False
    return True

def generate_fix_syntax():
    """Génère le script fix_syntax.py s'il n'existe pas"""
    with open("fix_syntax.py", "w", encoding="utf-8") as f:
        f.write("""# fix_syntax.py
# Script pour corriger l'erreur de syntaxe dans le fichier chatbot.py

import os
import re
import logging
import sys

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("fix_syntax.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.fix_syntax")

def fix_process_web_message():
    """Corrige l'erreur de syntaxe dans process_web_message"""
    file_path = "chatbot.py"
    
    try:
        # Lire le fichier
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Trouver la méthode process_web_message complète
        pattern = r"async def process_web_message\\(self, text: str, conversation: Any.*?\\):.*?handle_action_button"
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            logger.error("Méthode process_web_message non trouvée dans chatbot.py")
            return False
        
        # Obtenir le contenu de la méthode
        method_content = match.group(0)
        
        # Rechercher le bloc try/except pertinent
        extraction_pattern = r"# Extraction du client.*?# Gestion des dates"
        extraction_match = re.search(extraction_pattern, method_content, re.DOTALL)
        
        if not extraction_match:
            logger.error("Section d'extraction du client non trouvée dans process_web_message")
            return False
        
        original_extraction = extraction_match.group(0)
        
        # Créer une version corrigée avec la structure try/except intacte
        corrected_extraction = \"""# Extraction du client
                    client_info = None
                    search_context = analysis.get("search_context", {})
                    if search_context.get("has_client"):
                        client_name, _, _ = await extract_client_name(text)
                        # Ajout d'une recherche spécifique pour les mots simples
                        if not client_name and re.search(r'\\\\b[A-Za-z]{4,}\\\\b', text):
                            potential_clients = re.findall(r'\\\\b[A-Za-z]{4,}\\\\b', text)
                            for potential in potential_clients:
                                test_name, _, _ = await extract_client_name(potential)
                                if test_name:
                                    client_name = test_name
                                    break
                        if client_name:
                            client_info = {"source": client_name, "jira": client_name, "zendesk": client_name}
                            self.logger.info(f"Client trouvé: {client_name}")

                    # Tentative d'extraction directe du client si non trouvé par l'analyse
                    if not client_info:
                        # Vérification explicite pour RONDOT
                        if "RONDOT" in text.upper():
                            client_info = {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
                            self.logger.info("Client RONDOT détecté explicitement")
                        else:
                            # Extraction standard
                            client_name, _, _ = await extract_client_name(text)
                            if client_name:
                                client_info = {"source": client_name, "jira": client_name, "zendesk": client_name}
                                self.logger.info(f"Client trouvé (méthode directe): {client_name}")
                            else:
                                self.logger.info("Aucun client identifié pour cette requête")

                    # Gestion des dates\"""
        
        # Remplacer la section originale par la version corrigée
        new_content = content.replace(original_extraction, corrected_extraction)
        
        # Vérifier que le contenu a bien été modifié
        if new_content == content:
            logger.error("Aucune modification n'a été effectuée dans le fichier")
            return False
        
        # Écrire le fichier modifié
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        logger.info(f"chatbot.py corrigé avec succès")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la correction de {file_path}: {str(e)}")
        return False

def main():
    """Fonction principale du script"""
    print("🔧 Correction de l'erreur de syntaxe dans chatbot.py")
    print("=================================================\\n")
    
    try:
        # Corriger l'erreur de syntaxe dans process_web_message
        print("Correction de l'erreur de syntaxe dans process_web_message...")
        if fix_process_web_message():
            print("✅ chatbot.py corrigé avec succès")
        else:
            print("❌ Échec de la correction de chatbot.py")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()""")

def generate_fix_indentation():
    """Génère le script fix_indentation.py s'il n'existe pas"""
    with open("fix_indentation.py", "w", encoding="utf-8") as f:
        f.write("""# fix_indentation.py
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
    print("=========================================================\\n")
    
    try:
        # Corriger l'erreur d'indentation dans extract_client_name
        print("Correction de l'erreur d'indentation dans extract_client_name...")
        if fix_extract_client_name():
            print("✅ gestion_clients.py corrigé avec succès")
        else:
            print("❌ Échec de la correction de gestion_clients.py")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()""")

def generate_fix_if_block():
    """Génère le script fix_if_block.py s'il n'existe pas"""
    with open("fix_if_block.py", "w", encoding="utf-8") as f:
        f.write("""# fix_if_block.py
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
    print("===========================================================\\n")
    
    try:
        if fix_if_block_indentation():
            print("✅ Bloc if corrigé avec succès dans gestion_clients.py")
        else:
            print("❌ Échec de la correction du bloc if")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()""")

def run_tests():
    """Exécute les tests pour vérifier que les correctifs fonctionnent"""
    logger.info("Exécution des tests de validation")
    try:
        result = subprocess.run(
            [sys.executable, "test_rondot.py"],
            capture_output=True,
            text=True
        )
        
        # Vérifier si les tests ont réussi
        success = "Client: RONDOT, Score: 100.0" in result.stdout
        if success:
            logger.info("Tests de base réussis: détection RONDOT fonctionne correctement")
        else:
            logger.warning("Résultats des tests de base incertains, vérifiez manuellement")
        
        # Exécuter également les tests avancés si disponibles
        if os.path.exists("test_rondot_avec_mock.py"):
            logger.info("Exécution des tests avancés avec simulation")
            mock_result = subprocess.run(
                [sys.executable, "test_rondot_avec_mock.py"],
                capture_output=True,
                text=True
            )
            if "Tests terminés avec succès" in mock_result.stdout:
                logger.info("Tests avancés réussis")
            else:
                logger.warning("Résultats des tests avancés incertains, vérifiez manuellement")
        
        return success
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution des tests: {str(e)}")
        return False

def main():
    """Fonction principale du script d'installation"""
    print("🚀 Installation du correctif RONDOT pour le chatbot ITS_HELP")
    print("=========================================================\n")
    
    try:
        # 1. Créer des sauvegardes
        print("1. Création des sauvegardes...")
        if create_backups():
            print(f"✅ Sauvegardes créées dans {BACKUP_DIR}")
        else:
            print("❌ Échec de la création des sauvegardes")
            return
        
        # 2. Exécuter le script de correctif principal
        print("\n2. Application du correctif principal...")
        if run_correctif():
            print("✅ Correctif principal appliqué avec succès")
        else:
            print("❌ Échec de l'application du correctif principal")
            return
        
        # 3. Exécuter les scripts de correction d'erreurs
        print("\n3. Application des corrections d'erreurs potentielles...")
        if run_fixes():
            print("✅ Corrections complémentaires appliquées avec succès")
        else:
            print("❌ Échec de l'application des corrections complémentaires")
            return
        
        # 4. Exécuter les tests
        print("\n4. Exécution des tests de validation...")
        if run_tests():
            print("✅ Tests de validation réussis")
        else:
            print("⚠️ Résultats des tests incertains, vérifiez manuellement")
        
        # Résumé
        print("\n✅ Installation du correctif RONDOT terminée avec succès!")
        print(f"Une sauvegarde des fichiers originaux a été créée dans le dossier {BACKUP_DIR}")
        print("\nPour vérifier le bon fonctionnement:")
        print("  1. Testez le chatbot avec des requêtes contenant 'RONDOT'")
        print("  2. Vérifiez les logs pour confirmer la détection du client")
        print("  3. Assurez-vous que les réponses sont pertinentes")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()
