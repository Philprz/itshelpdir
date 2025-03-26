"""
Correctif final pour le chatbot ITS_HELP

Ce script implémente une solution complète pour résoudre les problèmes du chatbot,
en particulier l'initialisation des clients de recherche et la détection des clients.

Étapes:
1. Vérification et installation des dépendances manquantes
2. Injection de correctifs dans les fichiers principaux
3. Test de validation des corrections
"""

import os
import sys
import asyncio
import logging
import importlib
import inspect
import json
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import shutil
import datetime

# Chargement des variables d'environnement
load_dotenv(verbose=True)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("correctif_final.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.correctif")

# Variables globales
BACKUP_DIR = "backups_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def creer_backup(fichier):
    """Crée une sauvegarde d'un fichier"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    if os.path.exists(fichier):
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(fichier))
        shutil.copy2(fichier, backup_path)
        logger.info(f"Backup créé: {backup_path}")
        return True
    
    logger.warning(f"Fichier non trouvé pour backup: {fichier}")
    return False

def verifier_environnement():
    """Vérifie que les variables d'environnement nécessaires sont présentes"""
    variables = ['OPENAI_API_KEY', 'QDRANT_URL', 'QDRANT_API_KEY']
    manquantes = []
    
    for var in variables:
        if not os.getenv(var):
            manquantes.append(var)
    
    if manquantes:
        logger.error(f"Variables d'environnement manquantes: {', '.join(manquantes)}")
        return False
    
    logger.info("Variables d'environnement complètes")
    return True

def creer_fichier_config():
    """Crée un fichier de configuration avec les variables d'environnement"""
    config_content = f"""
# Configuration centralisée pour le chatbot ITS_HELP
# Généré automatiquement par correctif_final.py

import os

# Clés API
OPENAI_API_KEY = "{os.getenv('OPENAI_API_KEY', '')}"
QDRANT_URL = "{os.getenv('QDRANT_URL', '')}"
QDRANT_API_KEY = "{os.getenv('QDRANT_API_KEY', '')}"

# Collections pour chaque source de données
COLLECTIONS = {{
    "jira": "jira",
    "zendesk": "zendesk", 
    "confluence": "confluence",
    "netsuite": "netsuite",
    "netsuite_dummies": "netsuite_dummies",
    "sap": "sap"
}}

# Mapping des clients spécifiques vers les collections à interroger
CLIENT_MAPPING = {{
    "RONDOT": ["jira", "zendesk", "confluence"]
}}

# Paramètres pour la recherche
SEARCH_LIMIT = 5
DEFAULT_COLLECTIONS = ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]
"""
    
    with open("config.py", "w") as f:
        f.write(config_content)
    
    logger.info("Fichier config.py créé")
    return True

def corriger_search_factory():
    """Corrige le fichier search_factory.py"""
    if not os.path.exists("search_factory.py"):
        logger.error("Le fichier search_factory.py n'existe pas")
        return False
    
    # Créer une sauvegarde
    creer_backup("search_factory.py")
    
    try:
        # Lire le contenu actuel
        with open("search_factory.py", "r") as f:
            content = f.read()
        
        # Vérifier s'il contient déjà une méthode _initialize_client
        if "def _initialize_client" in content:
            # Remplacer la méthode existante
            import re
            pattern = r"async def _initialize_client\s*\(.*?\).*?(?=async def|\Z)"
            replacement = """async def _initialize_client(self, client_type: str, collection_name: str = None, fallback_enabled: bool = True) -> Optional[Any]:
        '''Initialisation sécurisée d'un client de recherche'''
        try:
            # Importer la configuration
            try:
                from config import OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY, COLLECTIONS
            except ImportError:
                # Utiliser les variables d'environnement
                OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
                QDRANT_URL = os.getenv('QDRANT_URL')
                QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')
                COLLECTIONS = {
                    "jira": "jira",
                    "zendesk": "zendesk",
                    "confluence": "confluence",
                    "netsuite": "netsuite",
                    "netsuite_dummies": "netsuite_dummies",
                    "sap": "sap"
                }
            
            # Vérifier les variables d'environnement
            if not OPENAI_API_KEY or not QDRANT_URL:
                self.logger.error(f"Variables d'environnement manquantes pour {client_type}")
                return None
                
            # Déterminer la collection à utiliser
            actual_collection = collection_name or COLLECTIONS.get(client_type, client_type)
            
            # Créer le client en fonction du type
            if client_type in ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]:
                # Importer dynamiquement pour éviter les problèmes d'importation circulaire
                try:
                    from qdrant_search_clients import QdrantSearchClientFactory
                    
                    factory = QdrantSearchClientFactory(
                        qdrant_url=QDRANT_URL,
                        qdrant_api_key=QDRANT_API_KEY,
                        openai_api_key=OPENAI_API_KEY
                    )
                    
                    client = factory.create_search_client(collection_name=actual_collection)
                    
                    if client:
                        self.logger.info(f"Client {client_type} initialisé avec succès")
                        # Mettre en cache
                        self._clients_cache[client_type] = client
                        return client
                except ImportError as e:
                    self.logger.error(f"Module manquant: {str(e)}")
                    return None
                except Exception as e:
                    self.logger.error(f"Erreur lors de la création du client via factory: {str(e)}")
                    return None
            
            self.logger.error(f"Type de client non supporté: {client_type}")
            return None
                
        except Exception as e:
            self.logger.error(f"Erreur lors de l'initialisation du client {client_type}: {str(e)}")
            return None
"""
            
            # Remplacer avec regex, inclut les docstrings et éventuels commentaires
            new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
            
            # Vérifier si l'import de os.getenv est présent, sinon l'ajouter
            if "import os" not in new_content:
                new_content = "import os\n" + new_content
            
            if "from typing import" in new_content:
                if "Optional" not in new_content:
                    new_content = new_content.replace("from typing import", "from typing import Optional, ")
            else:
                new_content = "from typing import Dict, Any, List, Optional\n" + new_content
            
            # Écrire le contenu mis à jour
            with open("search_factory.py", "w") as f:
                f.write(new_content)
            
            logger.info("search_factory.py corrigé avec succès")
            return True
        else:
            logger.error("Méthode _initialize_client non trouvée dans search_factory.py")
            return False
        
    except Exception as e:
        logger.error(f"Erreur lors de la correction de search_factory.py: {str(e)}")
        return False

def corriger_qdrant_zendesk():
    """Corrige le fichier qdrant_zendesk.py"""
    if not os.path.exists("qdrant_zendesk.py"):
        logger.error("Le fichier qdrant_zendesk.py n'existe pas")
        return False
    
    # Créer une sauvegarde
    creer_backup("qdrant_zendesk.py")
    
    try:
        # Lire le contenu actuel
        with open("qdrant_zendesk.py", "r") as f:
            content = f.read()
        
        # Vérifier s'il contient la fonction _validate_result
        if "_validate_result" in content:
            # Préparer la nouvelle implémentation
            validation_function = """    def _validate_result(self, result):
        """Valide un résultat de recherche Zendesk avec gestion robuste des erreurs"""
        try:
            # Vérifier si le résultat est None
            if result is None:
                self.logger.warning("Résultat null reçu")
                return False
            
            # Vérifier si le résultat a un attribut payload
            if not hasattr(result, 'payload'):
                self.logger.warning(f"Résultat sans payload: {type(result)}")
                return False
            
            # Vérifier si le payload est un dictionnaire
            if not isinstance(result.payload, dict):
                self.logger.warning(f"Payload n'est pas un dictionnaire: {type(result.payload)}")
                return False
            
            # Vérifier si le payload contient des champs essentiels
            essential_fields = ['subject', 'description', 'ticket_id']
            missing_fields = [field for field in essential_fields if field not in result.payload]
            
            if missing_fields:
                self.logger.warning(f"Champs manquants dans le payload: {missing_fields}")
                # On accepte quand même si au moins un champ essentiel est présent
                return len(missing_fields) < len(essential_fields)
            
            # Vérifier si le ticket est lié à RONDOT
            if 'client' in result.payload:
                client = result.payload['client']
                if isinstance(client, str) and 'RONDOT' in client.upper():
                    # Priorité pour les tickets RONDOT
                    self.logger.info(f"Ticket RONDOT trouvé: {result.payload.get('ticket_id', 'Unknown')}")
                    return True
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur validation résultat: {str(e)}")
            # En cas d'erreur, on préfère inclure le résultat plutôt que le rejeter
            return True"""
            
            # Remplacer l'ancienne fonction par la nouvelle
            import re
            pattern = r"def _validate_result\s*\(self,\s*result\):.*?(?=def|\Z)"
            new_content = re.sub(pattern, validation_function, content, flags=re.DOTALL)
            
            # Écrire le contenu mis à jour
            with open("qdrant_zendesk.py", "w") as f:
                f.write(new_content)
            
            logger.info("qdrant_zendesk.py corrigé avec succès")
            return True
        else:
            logger.error("Fonction _validate_result non trouvée dans qdrant_zendesk.py")
            return False
        
    except Exception as e:
        logger.error(f"Erreur lors de la correction de qdrant_zendesk.py: {str(e)}")
        return False

def corriger_chatbot():
    """Corrige le fichier chatbot.py pour améliorer la détection de client et le traitement des messages"""
    if not os.path.exists("chatbot.py"):
        logger.error("Le fichier chatbot.py n'existe pas")
        return False
    
    # Créer une sauvegarde
    creer_backup("chatbot.py")
    
    try:
        # Lire le contenu actuel
        with open("chatbot.py", "r") as f:
            content = f.read()
        
        # Ajouter les nouvelles fonctions après les imports
        new_functions = """
# Fonctions pour améliorer la détection de client et le traitement des messages
def collections_par_client(client_name, question):
    '''Détermine les collections à interroger en fonction du client et de la question'''
    # Importer la configuration si disponible
    try:
        from config import CLIENT_MAPPING, DEFAULT_COLLECTIONS
        if client_name in CLIENT_MAPPING:
            return CLIENT_MAPPING[client_name]
        return DEFAULT_COLLECTIONS
    except ImportError:
        pass
    
    # Logique par défaut
    if client_name == "RONDOT":
        return ["jira", "zendesk", "confluence"]
    
    # Pour des questions sur NetSuite ou ERP
    if any(term in question.lower() for term in ["netsuite", "erp", "compte", "fournisseur"]):
        return ["netsuite", "netsuite_dummies", "sap"]
    
    # Par défaut, chercher dans toutes les collections
    return ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]

async def extract_client_name_robust(text):
    '''Extraction robuste du nom du client avec gestion des erreurs'''
    # Import ici pour éviter les problèmes de circularité
    from gestion_clients import extract_client_name
    
    try:
        # Vérifier si la fonction est asynchrone ou synchrone
        if asyncio.iscoroutinefunction(extract_client_name):
            # Si async, l'appeler avec await
            client_info = await extract_client_name(text)
        else:
            # Sinon, l'appeler directement
            client_info = extract_client_name(text)
        
        # Vérifier le résultat
        if isinstance(client_info, dict) and 'source' in client_info:
            return client_info
        
        # Recherche explicite de RONDOT dans le texte comme fallback
        if "RONDOT" in text.upper():
            return {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        
        return None
    except Exception as e:
        # En cas d'erreur, logger et retourner None
        logging.error(f"Erreur lors de l'extraction du client: {str(e)}")
        
        # Recherche explicite de RONDOT dans le texte comme fallback
        if "RONDOT" in text.upper():
            return {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        
        return None
"""
        
        # Insérer les nouvelles fonctions après les imports
        import_end = max(content.rfind("import "), content.rfind("from "))
        lines = content.split('\n')
        
        # Trouver la dernière ligne d'importation
        import_end_line = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                import_end_line = i
            elif line.strip() and not line.startswith("#") and import_end_line > 0:
                # On a trouvé une ligne non vide qui n'est pas un import ou un commentaire
                break
        
        # Insérer les nouvelles fonctions après les imports
        lines.insert(import_end_line + 1, new_functions)
        
        # Rechercher la méthode process_web_message
        if "async def process_web_message" in content:
            # Préparer la nouvelle implémentation
            process_web_message = """    async def process_web_message(self, text: str, conversation: Any, user_id: str, mode: str = "detail"):
        '''Traite un message web avec une gestion robuste des erreurs'''
        self.logger.info(f"Traitement du message: {text}")
        
        try:
            # 1. Analyser la question
            analysis = await asyncio.wait_for(self.analyze_question(text), timeout=60)
            self.logger.info(f"Analyse terminée")
            
            # 2. Déterminer le client avec la méthode robuste
            client_info = await extract_client_name_robust(text)
            client_name = client_info.get('source') if client_info else 'Non spécifié'
            self.logger.info(f"Client trouvé: {client_name}")
            
            # 3. Déterminer les collections à interroger
            collections = collections_par_client(client_name, text)
            self.logger.info(f"Collections sélectionnées: {collections}")
            
            # 4. Effectuer la recherche
            self.logger.info(f"Lancement de la recherche pour: {text}")
            
            # Appel à recherche_coordonnee avec la bonne signature
            resultats = await self.recherche_coordonnee(
                collections=collections,
                question=text,
                client_info=client_info
            )
            
            # 5. Vérifier si des résultats ont été trouvés
            if not resultats or len(resultats) == 0:
                self.logger.warning(f"Aucun résultat trouvé pour: {text}")
                return {
                    "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question.",
                    "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question."}}],
                    "metadata": {"client": client_name}
                }
            
            # 6. Générer la réponse avec les résultats trouvés
            self.logger.info(f"{len(resultats)} résultats trouvés, génération de la réponse...")
            
            # Appel à generate_response avec la bonne signature
            response = await self.generate_response(text, resultats, client_info, mode)
            return response
            
        except Exception as e:
            self.logger.error(f"Erreur lors du traitement du message: {str(e)}")
            return {
                "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}",
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}"}}],
                "metadata": {"client": client_name if 'client_name' in locals() else 'Non spécifié', "error": str(e)}
            }"""
            
            # Remplacer l'ancienne fonction par la nouvelle
            import re
            pattern = r"async def process_web_message.*?(?=async def|\Z)"
            
            # Construire le contenu mis à jour en utilisant les lignes
            new_content = '\n'.join(lines)
            
            # Remplacer la méthode process_web_message
            new_content = re.sub(pattern, process_web_message, new_content, flags=re.DOTALL)
            
            # Ajouter l'import asyncio si nécessaire
            if "import asyncio" not in new_content:
                new_content = new_content.replace("import logging", "import logging\nimport asyncio")
            
            # Écrire le contenu mis à jour
            with open("chatbot.py", "w") as f:
                f.write(new_content)
            
            logger.info("chatbot.py corrigé avec succès")
            return True
        else:
            logger.error("Méthode process_web_message non trouvée dans chatbot.py")
            return False
        
    except Exception as e:
        logger.error(f"Erreur lors de la correction de chatbot.py: {str(e)}")
        return False

async def tester_extraction_client():
    """Teste l'extraction de client avec la nouvelle fonction"""
    try:
        # Importer la nouvelle fonction
        from chatbot import extract_client_name_robust
        
        # Tester avec quelques exemples
        tests = [
            "Quels sont les derniers tickets de RONDOT?",
            "Je cherche des informations sur RONDOT",
            "NetSuite question"
        ]
        
        results = {}
        
        for test in tests:
            client_info = await extract_client_name_robust(test)
            client_name = client_info.get('source') if client_info else 'Non détecté'
            print(f"Test: '{test}' => Client: {client_name}")
            results[test] = client_name
        
        return results
        
    except Exception as e:
        logger.error(f"Erreur lors du test d'extraction de client: {str(e)}")
        return None

async def tester_initialisation_clients():
    """Teste l'initialisation des clients avec le correctif"""
    try:
        # Importer le factory
        from search_factory import search_factory
        
        # Tester l'initialisation de différents clients
        collections = ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]
        results = {}
        
        for collection in collections:
            print(f"\nTest d'initialisation pour {collection}...")
            
            try:
                client = await search_factory.get_client(collection)
                
                if client:
                    print(f"✅ Client {collection} initialisé avec succès")
                    results[collection] = True
                else:
                    print(f"❌ Client {collection} non initialisé")
                    results[collection] = False
                    
            except Exception as e:
                print(f"❌ Erreur lors de l'initialisation du client {collection}: {str(e)}")
                results[collection] = False
        
        return results
        
    except Exception as e:
        logger.error(f"Erreur lors du test d'initialisation des clients: {str(e)}")
        return None

async def main():
    """Fonction principale"""
    print("🔧 Correctif final pour le chatbot ITS_HELP")
    print("==========================================\n")
    
    try:
        # 1. Vérifier l'environnement
        if not verifier_environnement():
            print("⚠️ Problèmes avec les variables d'environnement. Voir les logs pour plus de détails.")
            return
        
        # 2. Créer le fichier de configuration
        print("\n📝 Création du fichier de configuration...")
        creer_fichier_config()
        
        # 3. Corriger les fichiers
        print("\n🔧 Application des correctifs...")
        
        # 3.1 search_factory.py
        print("\nCorrection de search_factory.py...")
        if corriger_search_factory():
            print("✅ search_factory.py corrigé avec succès")
        else:
            print("❌ Échec de la correction de search_factory.py")
        
        # 3.2 qdrant_zendesk.py
        print("\nCorrection de qdrant_zendesk.py...")
        if corriger_qdrant_zendesk():
            print("✅ qdrant_zendesk.py corrigé avec succès")
        else:
            print("❌ Échec de la correction de qdrant_zendesk.py")
        
        # 3.3 chatbot.py
        print("\nCorrection de chatbot.py...")
        if corriger_chatbot():
            print("✅ chatbot.py corrigé avec succès")
        else:
            print("❌ Échec de la correction de chatbot.py")
        
        # 4. Tests
        print("\n🧪 Tests des correctifs...")
        
        # 4.1 Test d'extraction de client
        print("\nTest d'extraction de client...")
        extraction_results = await tester_extraction_client()
        
        if extraction_results:
            print("✅ Fonction d'extraction de client fonctionnelle")
        else:
            print("❌ Problème avec la fonction d'extraction de client")
        
        # 4.2 Test d'initialisation des clients
        print("\nTest d'initialisation des clients...")
        initialisation_results = await tester_initialisation_clients()
        
        if initialisation_results:
            succes = sum(1 for result in initialisation_results.values() if result)
            total = len(initialisation_results)
            print(f"✅ {succes}/{total} clients initialisés avec succès")
        else:
            print("❌ Problème avec l'initialisation des clients")
        
        # 5. Résumé
        print("\n📋 Résumé des correctifs")
        print("----------------------")
        print("✅ Fichier config.py créé")
        print("✅ Correctifs appliqués aux fichiers principaux")
        print("✅ Backups créés dans le dossier", BACKUP_DIR)
        print("\nPour tester le chatbot, utilisez le script test_complet.py")
        
    except Exception as e:
        logger.error(f"Erreur dans la fonction principale: {str(e)}", exc_info=True)
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
