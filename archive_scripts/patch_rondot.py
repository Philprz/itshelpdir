# Patch simple pour corriger la détection de RONDOT
# Ce script modifie uniquement la fonction extract_client_name pour détecter RONDOT

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
        logging.FileHandler("patch_rondot.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.patch")

# Création d'un dossier pour les backups
BACKUP_DIR = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

def create_backup(file_path):
    # Crée une sauvegarde du fichier
    if os.path.exists(file_path):
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(file_path))
        shutil.copy2(file_path, backup_path)
        logger.info(f"Backup créé: {backup_path}")
        return True
    else:
        logger.warning(f"Fichier non trouvé: {file_path}")
        return False

def patch_extract_client_name():
    # Corrige la fonction extract_client_name pour détecter RONDOT
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

def patch_chatbot_process():
    # Modifie process_web_message pour améliorer la détection RONDOT et la sélection des collections
    file_path = "chatbot.py"
    
    # Créer une sauvegarde
    create_backup(file_path)
    
    try:
        # Lire le contenu du fichier
        with open(file_path, "r") as f:
            lines = f.readlines()
        
        # Variables pour suivre où insérer le code
        client_extract_line = -1
        collections_line = -1
        
        # Rechercher les lignes importantes
        for i, line in enumerate(lines):
            if "client_info = await self.extract_client_name" in line:
                client_extract_line = i
            elif "collections = " in line and "jira" in line and "zendesk" in line:
                collections_line = i
        
        if client_extract_line == -1:
            logger.error("Ligne d'extraction du client non trouvée")
            return False
        
        # Déterminer l'indentation
        indentation = len(lines[client_extract_line]) - len(lines[client_extract_line].lstrip())
        spaces = " " * indentation
        
        # Préparer le code à insérer pour la détection RONDOT
        rondot_code = [
            f"{spaces}# Détection spéciale pour RONDOT\n",
            f"{spaces}rondot_detected = 'RONDOT' in text.upper()\n",
            f"{spaces}\n",
            lines[client_extract_line],  # Ligne originale d'extraction
            f"{spaces}\n",
            f"{spaces}# Si RONDOT est détecté dans le texte mais pas par extract_client_name, forcer\n",
            f"{spaces}if rondot_detected and (not client_info or client_info.get('source') != 'RONDOT'):\n",
            f"{spaces}    self.logger.info('Forçage de la détection RONDOT')\n",
            f"{spaces}    client_info = {{'source': 'RONDOT', 'jira': 'RONDOT', 'zendesk': 'RONDOT'}}\n"
        ]
        
        # Remplacer la ligne d'extraction par le nouveau code
        new_lines = lines[:client_extract_line] + rondot_code + lines[client_extract_line+1:]
        
        # Si la ligne des collections a été trouvée, mettre à jour la sélection des collections
        if collections_line != -1:
            # Ajuster l'index de la ligne après notre insertion
            collections_line += len(rondot_code) - 1
            
            # Remplacer la ligne des collections par une sélection conditionnelle
            collections_code = [
                f"{spaces}# Sélection des collections en fonction du client\n",
                f"{spaces}if client_info and client_info.get('source') == 'RONDOT':\n",
                f"{spaces}    collections = ['jira', 'zendesk', 'confluence']\n",
                f"{spaces}    self.logger.info('Collections spécifiques pour RONDOT sélectionnées')\n",
                f"{spaces}elif any(term in text.lower() for term in ['netsuite', 'erp', 'compte', 'fournisseur']):\n",
                f"{spaces}    collections = ['netsuite', 'netsuite_dummies', 'sap']\n",
                f"{spaces}    self.logger.info('Collections ERP sélectionnées')\n",
                f"{spaces}else:\n",
                f"{spaces}    collections = ['jira', 'zendesk', 'confluence', 'netsuite', 'netsuite_dummies', 'sap']\n",
                f"{spaces}    self.logger.info('Toutes les collections sélectionnées')\n"
            ]
            
            # Remplacer la ligne originale des collections
            new_lines = new_lines[:collections_line] + collections_code + new_lines[collections_line+1:]
        
        # Écrire le fichier modifié
        with open(file_path, "w") as f:
            f.writelines(new_lines)
        
        logger.info(f"{file_path} modifié avec succès")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification de {file_path}: {str(e)}")
        return False

def create_test_script():
    # Crée un script simple pour tester les modifications
    file_content = """
# Script de test pour la détection RONDOT

import os
import asyncio
import logging
from dotenv import load_dotenv
import sys

# Charger les variables d'environnement
load_dotenv()

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("test_rondot")

# Importer après le chargement des variables d'environnement
from chatbot import ChatBot  # noqa: E402

async def main():
    # Test principal
    try:
        # Initialiser le chatbot
        chatbot = ChatBot(
            openai_key=os.getenv('OPENAI_API_KEY'),
            qdrant_url=os.getenv('QDRANT_URL'),
            qdrant_api_key=os.getenv('QDRANT_API_KEY')
        )
        
        # Requête test pour RONDOT
        query = "Quels sont les derniers tickets de RONDOT?"
        
        print(f"\\n🔍 Test pour la requête: '{query}'")
        
        # Test de l'extraction du client
        print("\\n1. Test de l'extraction du client:")
        client_info = await chatbot.extract_client_name(query)
        print(f"   Client détecté: {client_info}")
        
        # Test du traitement complet
        print("\\n2. Test du traitement complet:")
        response = await chatbot.process_web_message(
            text=query,
            conversation={"id": "test", "user_id": "test"},
            user_id="test",
            mode="guide"
        )
        
        if response:
            print(f"   Réponse: {response.get('text', '')[:150]}...")
            print(f"   Métadonnées: {response.get('metadata', {})}")
        else:
            print("   Aucune réponse reçue")
    
    except Exception as e:
        logger.error(f"Erreur lors du test: {str(e)}")
        print(f"❌ Erreur: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
"""
    
    with open("test_rondot.py", "w") as f:
        f.write(file_content)
    
    logger.info("Script de test créé: test_rondot.py")
    return True

def main():
    print("🔧 Patch pour la détection des tickets RONDOT")
    print("==========================================\n")
    
    try:
        # 1. Patch de extract_client_name
        print("1. Modification de extract_client_name pour détecter RONDOT...")
        if patch_extract_client_name():
            print("✅ gestion_clients.py modifié avec succès")
        else:
            print("❌ Échec de la modification de gestion_clients.py")
        
        # 2. Patch de process_web_message
        print("\n2. Modification de process_web_message pour RONDOT...")
        if patch_chatbot_process():
            print("✅ chatbot.py modifié avec succès")
        else:
            print("❌ Échec de la modification de chatbot.py")
        
        # 3. Création du script de test
        print("\n3. Création du script de test...")
        if create_test_script():
            print("✅ Script de test créé: test_rondot.py")
        else:
            print("❌ Échec de la création du script de test")
        
        print(f"\n✅ Modifications terminées! Une sauvegarde des fichiers originaux a été créée dans {BACKUP_DIR}")
        print("\nPour tester le correctif, exécutez:")
        print("python test_rondot.py")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()
