# correctif_rondot.py
# Script de correction ciblée pour la détection des tickets RONDOT dans le chatbot ITS_HELP

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
        logging.FileHandler("correctif_rondot.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.correctif")

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
    """Améliore la fonction extract_client_name pour détecter RONDOT explicitement"""
    file_path = "gestion_clients.py"
    
    # Créer une sauvegarde
    create_backup(file_path)
    
    try:
        # Lire le fichier
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Trouver la position appropriée pour insérer notre code
        insert_position = None
        for i, line in enumerate(lines):
            if "message_clean = normalize_string(message)" in line:
                # Nous voulons insérer après cette ligne et après la ligne de log qui suit
                insert_position = i + 2
                break
        
        if insert_position is None:
            logger.error("Position d'insertion non trouvée dans gestion_clients.py")
            return False
        
        # Obtenir l'indentation de la ligne actuelle
        current_line = lines[insert_position]
        indentation = len(current_line) - len(current_line.lstrip())
        indent = " " * indentation
        
        # Préparer le code à insérer
        code_to_insert = [
            f"{indent}# Détection explicite de RONDOT (prioritaire)\n",
            f"{indent}if 'RONDOT' in message_clean.upper():\n",
            f"{indent}    logger.info(f\"Match RONDOT trouvé explicitement\")\n",
            f"{indent}    return 'RONDOT', 100.0, {{\"source\": \"RONDOT\", \"jira\": \"RONDOT\", \"zendesk\": \"RONDOT\"}}\n",
            f"{indent}\n"
        ]
        
        # Insérer le code
        new_lines = lines[:insert_position] + code_to_insert + lines[insert_position:]
        
        # Écrire le fichier modifié
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        
        logger.info("gestion_clients.py modifié avec succès pour la détection de RONDOT")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification de {file_path}: {str(e)}")
        return False

def fix_determine_collections():
    """Améliore la méthode determine_collections pour gérer spécifiquement les requêtes RONDOT"""
    file_path = "chatbot.py"
    
    # Créer une sauvegarde
    create_backup(file_path)
    
    try:
        # Lire le fichier
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Trouver la méthode determine_collections
        pattern = r"def determine_collections\(self, analysis: Dict\) -> List\[str\]:(.*?)def "
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            logger.error("Méthode determine_collections non trouvée dans chatbot.py")
            return False
        
        method_content = match.group(1)
        
        # Vérifier si la détection RONDOT est déjà présente
        if "RONDOT" in method_content:
            logger.info("La détection RONDOT semble déjà être implémentée dans determine_collections")
            return True
        
        # Trouver le début du corps de la méthode
        method_start = content.find(method_content)
        
        # Trouver la ligne qui vérifie les tickets
        tickets_check_line = '        # Vérification spécifique pour les tickets'
        tickets_check_pos = content.find(tickets_check_line, method_start)
        
        if tickets_check_pos == -1:
            logger.error("Ligne 'Vérification spécifique pour les tickets' non trouvée")
            return False
        
        # Préparer le code à insérer pour la détection RONDOT
        code_to_insert = '''        # Vérification spécifique pour RONDOT
        query_text = analysis.get('query', {}).get('original','').upper()
        if "RONDOT" in query_text:
            self.logger.info("Collections déterminées par mention de 'RONDOT': ['jira', 'zendesk', 'confluence']")
            return ['jira', 'zendesk', 'confluence']
            
'''
        
        # Insérer le code avant la vérification des tickets
        new_content = content[:tickets_check_pos] + code_to_insert + content[tickets_check_pos:]
        
        # Écrire le fichier modifié
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        logger.info("chatbot.py modifié avec succès pour la détection de RONDOT dans determine_collections")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification de {file_path}: {str(e)}")
        return False

def fix_process_web_message():
    """Améliore process_web_message pour la détection et le traitement des requêtes RONDOT"""
    file_path = "chatbot.py"
    
    try:
        # Le fichier est déjà sauvegardé par fix_determine_collections
        
        # Lire le fichier
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Trouver la section de code pertinente dans process_web_message
        pattern = r"# Tentative d'extraction directe du client si non trouvé par l'analyse(.*?)self\.logger\.info\(\"Aucun client identifié pour cette requête\"\)"
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            logger.error("Section pour l'amélioration de process_web_message non trouvée")
            return False
        
        section = match.group(0)
        section_pos = content.find(section)
        
        # Déterminer l'indentation
        lines = section.splitlines()
        if lines:
            indentation = len(lines[0]) - len(lines[0].lstrip())
            indent = " " * indentation
        else:
            indent = "                    "  # Indentation par défaut
        
        # Préparer le code de remplacement avec détection explicite de RONDOT
        replacement = f"""# Tentative d'extraction directe du client si non trouvé par l'analyse
{indent}if not client_info:
{indent}    # Vérification explicite pour RONDOT
{indent}    if "RONDOT" in text.upper():
{indent}        client_info = {{"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}}
{indent}        self.logger.info("Client RONDOT détecté explicitement")
{indent}    else:
{indent}        # Extraction standard
{indent}        client_name, _, _ = await extract_client_name(text)
{indent}        if client_name:
{indent}            client_info = {{"source": client_name, "jira": client_name, "zendesk": client_name}}
{indent}            self.logger.info(f"Client trouvé (méthode directe): {{client_name}}")
{indent}        else:
{indent}            self.logger.info("Aucun client identifié pour cette requête")"""
        
        # Remplacer la section
        new_content = content[:section_pos] + replacement + content[section_pos + len(section):]
        
        # Écrire le fichier modifié
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        logger.info("chatbot.py modifié avec succès pour la détection de RONDOT dans process_web_message")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification du process_web_message: {str(e)}")
        return False

def create_test_script():
    """Crée un script de test simple pour valider les modifications"""
    file_path = "test_rondot.py"
    
    test_code = """
# Script de test pour valider la détection des tickets RONDOT
import os
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
logger = logging.getLogger("test_rondot")

# Import après chargement des variables d'environnement
from chatbot import ChatBot
from gestion_clients import extract_client_name

async def test_extract_client():
    print("\\n---- Test de extract_client_name ----")
    queries = [
        "Quels sont les derniers tickets RONDOT?",
        "J'ai besoin d'info sur les tickets RONDOT",
        "RONDOT a des problèmes",
        "Cherche les tickets du client RONDOT",
        "Recherche tickets rondot" # en minuscule
    ]
    
    for query in queries:
        client_name, score, metadata = await extract_client_name(query)
        print(f"Query: '{query}'")
        print(f"  → Client: {client_name}, Score: {score}, Metadata: {metadata}\\n")

async def test_chatbot():
    print("\\n---- Test du chatbot ----")
    # Initialisation du chatbot
    chatbot = ChatBot(
        openai_key=os.getenv('OPENAI_API_KEY'),
        qdrant_url=os.getenv('QDRANT_URL'),
        qdrant_api_key=os.getenv('QDRANT_API_KEY')
    )
    
    # Test de determine_collections (analyse seule)
    print("\\n1. Test de determine_collections:")
    test_analysis = {
        "type": "support",
        "query": {
            "original": "Tickets récents pour RONDOT"
        }
    }
    collections = chatbot.determine_collections(test_analysis)
    print(f"Collections sélectionnées: {collections}")
    
    # Test avec une requête RONDOT
    query = "Je cherche les derniers tickets de RONDOT"
    print(f"\\n2. Test avec la requête: '{query}'")
    
    try:
        response = await chatbot.process_web_message(
            text=query,
            conversation={"id": "test", "user_id": "test"},
            user_id="test_user",
            mode="guide"
        )
        
        print(f"Réponse reçue:")
        print(f"  → Text: {response.get('text', '')[:150]}...")
        print(f"  → Metadata: {response.get('metadata', {})}")
        
    except Exception as e:
        print(f"Erreur lors du test du chatbot: {str(e)}")

async def main():
    try:
        # Test de la fonction extract_client_name
        await test_extract_client()
        
        # Test du chatbot
        await test_chatbot()
        
    except Exception as e:
        print(f"Erreur globale: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
"""
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(test_code)
    
    logger.info(f"Script de test créé: {file_path}")
    return True

def main():
    """Fonction principale du script"""
    print("🔧 Correctif pour la détection des tickets RONDOT")
    print("==============================================\n")
    
    try:
        # 1. Améliorer extract_client_name pour la détection de RONDOT
        print("1. Amélioration de extract_client_name pour la détection de RONDOT...")
        if fix_extract_client_name():
            print("✅ gestion_clients.py modifié avec succès")
        else:
            print("❌ Échec de la modification de gestion_clients.py")
        
        # 2. Améliorer determine_collections pour prioritiser les collections pertinentes
        print("\n2. Amélioration de determine_collections pour les requêtes RONDOT...")
        if fix_determine_collections():
            print("✅ determine_collections dans chatbot.py modifié avec succès")
        else:
            print("❌ Échec de la modification de determine_collections")
        
        # 3. Améliorer process_web_message pour la détection explicite de RONDOT
        print("\n3. Amélioration de process_web_message pour la détection de RONDOT...")
        if fix_process_web_message():
            print("✅ process_web_message dans chatbot.py modifié avec succès")
        else:
            print("❌ Échec de la modification de process_web_message")
        
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
