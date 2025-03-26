# fix_syntax.py
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
        pattern = r"async def process_web_message\(self, text: str, conversation: Any.*?\):.*?handle_action_button"
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
        corrected_extraction = """# Extraction du client
                    client_info = None
                    search_context = analysis.get("search_context", {})
                    if search_context.get("has_client"):
                        client_name, _, _ = await extract_client_name(text)
                        # Ajout d'une recherche spécifique pour les mots simples
                        if not client_name and re.search(r'\\b[A-Za-z]{4,}\\b', text):
                            potential_clients = re.findall(r'\\b[A-Za-z]{4,}\\b', text)
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

                    # Gestion des dates"""
        
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
    print("=================================================\n")
    
    try:
        # Corriger l'erreur de syntaxe dans process_web_message
        print("Correction de l'erreur de syntaxe dans process_web_message...")
        if fix_process_web_message():
            print("✅ chatbot.py corrigé avec succès")
        else:
            print("❌ Échec de la correction de chatbot.py")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}")
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    main()
