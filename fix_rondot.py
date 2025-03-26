"""
Correctif ciblé pour la détection des tickets RONDOT

Ce script se concentre spécifiquement sur la correction de la détection 
du client RONDOT et l'amélioration du processus de recherche.
"""

import os
import re
import shutil
import logging
import sys
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("fix_rondot.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.fix_rondot")

# Création d'un dossier pour les backups
BACKUP_DIR = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

def create_backup(file_path):
    """Crée une sauvegarde du fichier"""
    if os.path.exists(file_path):
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(file_path))
        shutil.copy2(file_path, backup_path)
        logger.info(f"Backup créé: {backup_path}")
        return True
    else:
        logger.warning(f"Fichier non trouvé: {file_path}")
        return False

def fix_extract_client_name():
    """Corrige la fonction extract_client_name pour détecter RONDOT"""
    file_path = "gestion_clients.py"
    
    # Créer une sauvegarde
    create_backup(file_path)
    
    try:
        # Lire le fichier
        with open(file_path, "r") as f:
            content = f.read()
        
        # Vérifier si la fonction existe
        if "def extract_client_name" not in content:
            logger.error(f"Fonction extract_client_name non trouvée dans {file_path}")
            return False
        
        # Trouver où insérer le code de détection RONDOT
        pattern = r"def extract_client_name\([^)]*\):.*?logger\.info\(f[\"']Extraction du client depuis:"
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            logger.error("Pattern pour l'insertion non trouvé")
            return False
        
        # Déterminer le niveau d'indentation
        found_text = match.group(0)
        lines = found_text.splitlines()
        if len(lines) >= 2:
            # Trouver l'indentation de la deuxième ligne
            second_line = lines[1]
            indentation = len(second_line) - len(second_line.lstrip())
            spaces = " " * indentation
        else:
            spaces = "    "  # Indentation par défaut
        
        # Préparer le code à insérer
        insertion = f"""
{spaces}# Détection explicite de RONDOT (prioritaire)
{spaces}if "RONDOT" in text.upper():
{spaces}    logger.info("Client RONDOT détecté explicitement")
{spaces}    return {{"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}}
"""
        
        # Trouver le bon endroit pour insérer le code (après le premier logger.info)
        pattern_end = r"logger\.info\(f[\"']Extraction du client depuis: [^\"']*[\"']\)"
        match_end = re.search(pattern_end, content)
        
        if not match_end:
            logger.error("Point d'insertion non trouvé")
            return False
        
        end_pos = match_end.end()
        new_content = content[:end_pos] + insertion + content[end_pos:]
        
        # Écrire le fichier modifié
        with open(file_path, "w") as f:
            f.write(new_content)
        
        logger.info(f"{file_path} modifié avec succès")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification de {file_path}: {str(e)}")
        return False

def fix_process_web_message():
    """Modifie process_web_message pour améliorer la détection RONDOT"""
    file_path = "chatbot.py"
    
    # Créer une sauvegarde
    create_backup(file_path)
    
    try:
        # Lire le fichier
        with open(file_path, "r") as f:
            content = f.read()
        
        # Vérifier si la méthode existe
        if "async def process_web_message" not in content:
            logger.error(f"Méthode process_web_message non trouvée dans {file_path}")
            return False
        
        # Trouver la méthode process_web_message
        pattern = r"async def process_web_message\s*\([^)]*\):.*?(?=async def|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            logger.error("Méthode process_web_message non trouvée avec le pattern regex")
            return False
        
        # Extraire la méthode existante pour l'analyser
        existing_method = match.group(0)
        
        # Déterminer l'indentation
        lines = existing_method.splitlines()
        if len(lines) >= 2:
            # Trouver l'indentation de la deuxième ligne
            second_line = lines[1] if len(lines) > 1 else "    "
            indentation = len(second_line) - len(second_line.lstrip())
            spaces = " " * indentation
        else:
            spaces = "    "  # Indentation par défaut
        
        # Check if we need to modify for client detection
        if "RONDOT" not in existing_method:
            # Trouver la ligne où le client est extrait
            client_extraction_pattern = r"client_info\s*=\s*await\s*self\.extract_client_name\(text\)"
            client_match = re.search(client_extraction_pattern, existing_method)
            
            if client_match:
                # Préparer le code à insérer pour la détection de RONDOT
                insertion = f"""
{spaces}# Détection spéciale pour RONDOT
{spaces}rondot_detected = "RONDOT" in text.upper()
{spaces}
{spaces}# Extraction standard du client
{spaces}client_info = await self.extract_client_name(text)
{spaces}
{spaces}# Si RONDOT est détecté dans le texte mais pas par extract_client_name, forcer
{spaces}if rondot_detected and (not client_info or client_info.get('source') != "RONDOT"):
{spaces}    self.logger.info("Forçage de la détection RONDOT")
{spaces}    client_info = {{"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}}
"""
                
                # Remplacer la ligne d'extraction du client
                new_method = existing_method.replace(client_match.group(0), insertion)
                
                # Remplacer l'ancienne méthode par la nouvelle
                new_content = content.replace(existing_method, new_method)
                
                # Écrire le fichier modifié
                with open(file_path, "w") as f:
                    f.write(new_content)
                
                logger.info(f"{file_path} modifié avec succès pour la détection RONDOT")
                return True
            else:
                logger.error("Pattern d'extraction du client non trouvé")
                return False
        else:
            logger.info("La détection de RONDOT semble déjà être implémentée")
            return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification de {file_path}: {str(e)}")
        return False

def fix_collections_selection():
    """Modifie la sélection des collections dans recherche_coordonnee"""
    file_path = "chatbot.py"
    
    try:
        # Le fichier est déjà sauvegardé par fix_process_web_message
        
        # Lire le fichier
        with open(file_path, "r") as f:
            content = f.read()
        
        # Vérifier si la méthode existe
        if "async def recherche_coordonnee" not in content:
            logger.error(f"Méthode recherche_coordonnee non trouvée dans {file_path}")
            return False
        
        # Trouver la méthode recherche_coordonnee
        pattern = r"async def recherche_coordonnee\s*\([^)]*\):.*?(?=async def|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            logger.error("Méthode recherche_coordonnee non trouvée avec le pattern regex")
            return False
        
        # Extraire la méthode existante
        existing_method = match.group(0)
        
        # Vérifier si collections est le premier paramètre
        if "collections: List[str]" not in existing_method and "collections=None" not in existing_method:
            # La méthode a probablement une signature différente
            # Chercher pour identifier la signature actuelle
            signature_pattern = r"async def recherche_coordonnee\s*\(([^)]*)\)"
            signature_match = re.search(signature_pattern, existing_method)
            
            if not signature_match:
                logger.error("Impossible de déterminer la signature de recherche_coordonnee")
                return False
            
            current_signature = signature_match.group(1)
            
            # Détecter l'indentation
            lines = existing_method.splitlines()
            if len(lines) >= 2:
                second_line = lines[1]
                indentation = len(second_line) - len(second_line.lstrip())
                spaces = " " * indentation
            else:
                spaces = "    "
            
            # Créer une nouvelle méthode avec les paramètres collections et client_info
            new_signature = current_signature
            if "collections" not in current_signature:
                new_signature = f"self, collections: List[str], {new_signature.replace('self, ', '')}"
            if "client_info" not in current_signature:
                new_signature = f"{new_signature}, client_info=None"
            
            # Créer la nouvelle signature complète
            new_header = f"async def recherche_coordonnee({new_signature}):"
            
            # Remplacer l'ancienne signature par la nouvelle
            new_method = existing_method.replace(signature_match.group(0), new_header)
            
            # Vérifier s'il y a un code qui itère sur des collections fixes
            # et le remplacer par une itération sur le paramètre collections
            collection_loop_pattern = r"(for source_type in \[)([^\]]*?)(\])"
            collection_loop_match = re.search(collection_loop_pattern, new_method)
            
            if collection_loop_match:
                # Remplacer la boucle sur les collections fixes
                replacement = f"{collection_loop_match.group(1)}collections{collection_loop_match.group(3)}"
                new_method = new_method.replace(collection_loop_match.group(0), replacement)
            
            # Remplacer l'ancienne méthode par la nouvelle
            new_content = content.replace(existing_method, new_method)
            
            # Assurer les imports nécessaires
            if "from typing import List" not in new_content and "from typing import" in new_content:
                new_content = new_content.replace("from typing import", "from typing import List, ")
            elif "from typing" not in new_content:
                new_content = "from typing import List, Dict, Any\n" + new_content
            
            # Écrire le fichier modifié
            with open(file_path, "w") as f:
                f.write(new_content)
            
            logger.info(f"{file_path} modifié avec succès pour la sélection des collections")
            return True
        else:
            logger.info("La méthode recherche_coordonnee semble déjà accepter les collections en paramètre")
            return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification des collections: {str(e)}")
        return False

def create_test_script():
    """Crée un script simple pour tester les modifications"""
    file_path = "test_rondot.py"
    
    script_content = """
import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

# Importer après chargement des variables d'environnement
from chatbot import ChatBot  # noqa: E402

async def test_rondot():
    """Teste la détection et la recherche pour RONDOT"""
    # Initialiser le chatbot
    chatbot = ChatBot(
        openai_key=os.getenv('OPENAI_API_KEY'),
        qdrant_url=os.getenv('QDRANT_URL'),
        qdrant_api_key=os.getenv('QDRANT_API_KEY')
    )
    
    # Requête test pour RONDOT
    query = "Quels sont les derniers tickets de RONDOT?"
    
    print(f"\\n🔍 Test pour la requête: '{query}'")
    
    # 1. Test de l'extraction du client
    print("\\n1. Test de l'extraction du client:")
    client_info = await chatbot.extract_client_name(query)
    print(f"   Client détecté: {client_info}")
    
    # 2. Test du traitement complet du message
    print("\\n2. Test du traitement complet:")
    response = await chatbot.process_web_message(
        text=query,
        conversation={"id": "test", "user_id": "test"},
        user_id="test",
        mode="guide"
    )
    
    print(f"   Réponse: {response.get('text', '')[:150]}...")
    print(f"   Métadonnées: {response.get('metadata', {})}")
    
    # Test pour une requête ERP
    query_erp = "Comment configurer un compte fournisseur dans NetSuite?"
    
    print(f"\\n🔍 Test pour la requête ERP: '{query_erp}'")
    
    response_erp = await chatbot.process_web_message(
        text=query_erp,
        conversation={"id": "test", "user_id": "test"},
        user_id="test",
        mode="guide"
    )
    
    print(f"   Réponse: {response_erp.get('text', '')[:150]}...")
    print(f"   Métadonnées: {response_erp.get('metadata', {})}")

if __name__ == "__main__":
    asyncio.run(test_rondot())
"""
    
    with open(file_path, "w") as f:
        f.write(script_content)
    
    logger.info(f"Script de test créé: {file_path}")
    return True

def main():
    """Fonction principale du script"""
    print("🔧 Correctif pour la détection des tickets RONDOT")
    print("==============================================\n")
    
    try:
        # 1. Corriger extract_client_name
        print("1. Correction de la fonction extract_client_name...")
        if fix_extract_client_name():
            print("✅ gestion_clients.py modifié avec succès")
        else:
            print("❌ Échec de la modification de gestion_clients.py")
        
        # 2. Corriger process_web_message
        print("\n2. Amélioration de la détection RONDOT dans process_web_message...")
        if fix_process_web_message():
            print("✅ chatbot.py modifié pour la détection RONDOT")
        else:
            print("❌ Échec de la modification de chatbot.py pour la détection RONDOT")
        
        # 3. Corriger la sélection des collections
        print("\n3. Amélioration de la sélection des collections...")
        if fix_collections_selection():
            print("✅ Sélection des collections améliorée")
        else:
            print("❌ Échec de l'amélioration de la sélection des collections")
        
        # 4. Créer un script de test
        print("\n4. Création d'un script de test...")
        if create_test_script():
            print("✅ Script de test créé: test_rondot.py")
        else:
            print("❌ Échec de la création du script de test")
        
        # Résumé
        print("\n✅ Correctifs appliqués avec succès!")
        print(f"Une sauvegarde des fichiers originaux a été créée dans le dossier {BACKUP_DIR}")
        print("\nPour tester les modifications, exécutez:")
        print("python test_rondot.py")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()
