"""
Correction des dépendances manquantes pour les clients de recherche

Ce script identifie et corrige les problèmes de dépendances manquantes
qui empêchent les clients de recherche de fonctionner correctement.
"""

import os
import asyncio
import logging
from dotenv import load_dotenv
import sys

# Chargement des variables d'environnement
load_dotenv(verbose=True)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("dependencies_fix.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.fix")

# Import après chargement des variables d'environnement
from gestion_clients import initialiser_base_clients  # noqa: E402
from search_factory import search_factory  # noqa: E402

async def verify_environment():
    """Vérifie les variables d'environnement critiques"""
    critical_vars = {
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
        'QDRANT_URL': os.getenv('QDRANT_URL'),
        'QDRANT_API_KEY': os.getenv('QDRANT_API_KEY')
    }
    
    print("\n📋 Vérification des variables d'environnement:")
    for var, value in critical_vars.items():
        status = "✅ Présente" if value else "❌ Manquante"
        masked_value = "****" if value and len(value) > 4 else None
        print(f"{var}: {status}" + (f" ({masked_value})" if masked_value else ""))
    
    return all(critical_vars.values())

async def init_dependencies():
    """Initialise les dépendances requises pour les clients de recherche"""
    try:
        # 1. Vérification de l'environnement
        print("\nInitialisation des dépendances...")
        env_ok = await verify_environment()
        
        if not env_ok:
            print("⚠️ Certaines variables d'environnement sont manquantes")
            print("Vous devez configurer OPENAI_API_KEY, QDRANT_URL et QDRANT_API_KEY")
            return False
        
        # 2. Initialisation de la base des clients
        print("\nInitialisation de la base des clients...")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée")
        
        # 3. Création du fichier de configuration de secours
        print("\nCréation d'un fichier de configuration de secours...")
        fallback_config = f"""
# Configuration de secours pour les clients de recherche
# Généré automatiquement par fix_dependencies.py

import os

# Configuration OpenAI
OPENAI_API_KEY = "{os.getenv('OPENAI_API_KEY')}"

# Configuration Qdrant
QDRANT_URL = "{os.getenv('QDRANT_URL')}"
QDRANT_API_KEY = "{os.getenv('QDRANT_API_KEY')}"

# Mapping des clients vers les collections
CLIENT_MAPPING = {{
    "jira": "jira",
    "zendesk": "zendesk",
    "confluence": "confluence",
    "netsuite": "netsuite",
    "netsuite_dummies": "netsuite_dummies",
    "sap": "sap"
}}

# Configuration des fallbacks
FALLBACK_CHAIN = {{
    "jira": ["confluence", "zendesk"],
    "zendesk": ["jira", "confluence"],
    "confluence": ["jira", "zendesk"],
    "netsuite": ["netsuite_dummies", "sap"],
    "netsuite_dummies": ["netsuite", "sap"],
    "sap": ["netsuite", "netsuite_dummies"]
}}
"""
        
        with open("fallback_config.py", "w") as f:
            f.write(fallback_config)
        
        print("✅ Configuration de secours créée")
        
        # 4. Création du correctif pour search_factory
        print("\nCréation du correctif pour search_factory...")
        
        search_factory_fix = """
# Correctif pour search_factory.py

from typing import Dict, Any, List, Optional
import logging
import os
import asyncio

# Importer la configuration de secours
try:
    from fallback_config import (
        OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY,
        CLIENT_MAPPING, FALLBACK_CHAIN
    )
except ImportError:
    # Si le fichier n'existe pas, utiliser les variables d'environnement
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    QDRANT_URL = os.getenv('QDRANT_URL')
    QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')
    
    CLIENT_MAPPING = {
        "jira": "jira",
        "zendesk": "zendesk",
        "confluence": "confluence",
        "netsuite": "netsuite",
        "netsuite_dummies": "netsuite_dummies",
        "sap": "sap"
    }
    
    FALLBACK_CHAIN = {
        "jira": ["confluence", "zendesk"],
        "zendesk": ["jira", "confluence"],
        "confluence": ["jira", "zendesk"],
        "netsuite": ["netsuite_dummies", "sap"],
        "netsuite_dummies": ["netsuite", "sap"],
        "sap": ["netsuite", "netsuite_dummies"]
    }

logger = logging.getLogger("ITS_HELP.search_factory")

# Fonction pour initialiser un client avec gestion des erreurs
async def initialize_client_safely(client_type: str, collection_name: str = None):
    """
    Initialise un client de recherche avec gestion des erreurs
    """
    from qdrant_search_clients import QdrantSearchClientFactory
    
    try:
        # Vérifier si les variables nécessaires sont disponibles
        if not OPENAI_API_KEY or not QDRANT_URL:
            logger.error(f"Variables d'environnement manquantes pour initialiser {client_type}")
            return None
        
        # Initialiser la factory Qdrant
        factory = QdrantSearchClientFactory(
            qdrant_url=QDRANT_URL,
            qdrant_api_key=QDRANT_API_KEY,
            openai_api_key=OPENAI_API_KEY
        )
        
        # Utiliser le nom de collection approprié
        actual_collection = collection_name or CLIENT_MAPPING.get(client_type, client_type)
        
        # Créer le client
        client = factory.create_search_client(collection_name=actual_collection)
        
        if client:
            logger.info(f"Client {client_type} initialisé avec succès")
            return client
        else:
            logger.warning(f"Échec de l'initialisation du client {client_type}")
            return None
            
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du client {client_type}: {str(e)}", exc_info=True)
        return None

# Appliquer ce correctif en modifiant search_factory._initialize_client dans votre code existant
"""
        
        with open("search_factory_fix.py", "w") as f:
            f.write(search_factory_fix)
        
        print("✅ Correctif pour search_factory créé")
        
        # 5. Création du correctif pour chatbot.py
        print("\nCréation du correctif pour chatbot.py...")
        
        chatbot_fix = """
# Correctif pour chatbot.py

# Fonction pour déterminer les collections en fonction du client et de la question
def collections_par_client_et_question(client_name, question):
    """
    Détermine les collections à interroger en fonction du client et de la question
    """
    # Pour RONDOT, on sait qu'on veut chercher dans JIRA, ZENDESK et CONFLUENCE
    if client_name == "RONDOT":
        return ["jira", "zendesk", "confluence"]
    
    # Pour des questions sur NetSuite, on cherche dans les collections ERP
    if any(term in question.lower() for term in ["netsuite", "erp", "compte", "fournisseur"]):
        return ["netsuite", "netsuite_dummies", "sap"]
    
    # Par défaut, on cherche dans toutes les collections
    return ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]

# Fonction pour extraire le nom du client avec gestion des erreurs
async def extract_client_name_safely(text):
    """
    Extrait le nom du client avec gestion robuste des erreurs
    """
    # Import ici pour éviter les problèmes de circularité
    from gestion_clients import extract_client_name
    import asyncio
    
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
        logging.error(f"Erreur lors de l'extraction du client: {str(e)}", exc_info=True)
        
        # Recherche explicite de RONDOT dans le texte comme fallback
        if "RONDOT" in text.upper():
            return {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        
        return None

# Version améliorée de process_web_message
async def process_web_message_fixed(self, text, conversation, user_id, mode="detail"):
    """
    Version améliorée de process_web_message qui gère correctement les erreurs et la sélection des collections
    """
    self.logger.info(f"Traitement du message: {text}")
    
    try:
        # 1. Analyser la question
        analysis = await asyncio.wait_for(self.analyze_question(text), timeout=60)
        self.logger.info(f"Analyse terminée")
        
        # 2. Déterminer le client
        client_info = await extract_client_name_safely(text)
        client_name = client_info.get('source') if client_info else 'Non spécifié'
        self.logger.info(f"Client trouvé: {client_name}")
        
        # 3. Déterminer les collections à interroger
        collections = collections_par_client_et_question(client_name, text)
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
        self.logger.error(f"Erreur lors du traitement du message: {str(e)}", exc_info=True)
        return {
            "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"Désolé, une erreur s'est produite lors du traitement de votre demande: {str(e)}"}}],
            "metadata": {"client": client_name if 'client_name' in locals() else 'Non spécifié', "error": str(e)}
        }

# Remplacer la méthode process_web_message existante par cette version améliorée
"""
        
        with open("chatbot_fix.py", "w") as f:
            f.write(chatbot_fix)
        
        print("✅ Correctif pour chatbot.py créé")
        
        return True
        
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation des dépendances: {str(e)}", exc_info=True)
        print(f"\n❌ Erreur critique: {str(e)}")
        return False

async def generer_instructions():
    """Génère des instructions d'installation pour l'utilisateur"""
    instructions = """
# Instructions pour corriger les problèmes du chatbot

## 1. Correction des dépendances manquantes

Pour résoudre les problèmes de dépendances manquantes qui empêchent l'initialisation correcte des clients de recherche:

1. **Assurez-vous que les variables d'environnement sont correctement configurées**:
   - OPENAI_API_KEY
   - QDRANT_URL
   - QDRANT_API_KEY

2. **Utilisez le fichier de configuration de secours**:
   - Le fichier `fallback_config.py` a été créé avec les valeurs actuelles des variables d'environnement
   - Ce fichier sera utilisé par le correctif de search_factory en cas de problème avec les variables d'environnement

## 2. Appliquer les correctifs

### Pour search_factory.py:

1. Ouvrez le fichier `search_factory.py`
2. Trouvez la méthode `_initialize_client`
3. Remplacez-la par la version du fichier `search_factory_fix.py`
4. Ajoutez la fonction `initialize_client_safely` au début du fichier

### Pour chatbot.py:

1. Ouvrez le fichier `chatbot.py`
2. Trouvez la méthode `process_web_message`
3. Remplacez-la par la version du fichier `chatbot_fix.py`
4. Ajoutez les fonctions `collections_par_client_et_question` et `extract_client_name_safely` au début du fichier

## 3. Vérifier les corrections

Après avoir appliqué les correctifs, vous pouvez exécuter à nouveau les tests pour vérifier que:

1. Les clients de recherche s'initialisent correctement
2. La détection du client fonctionne (en particulier pour RONDOT)
3. La sélection des collections à interroger est adaptée au client et à la question
4. La recherche et la génération de réponses fonctionnent correctement

## 4. Points clés des correctifs

Les correctifs apportent les améliorations suivantes:

1. **Gestion robuste des erreurs** pour l'initialisation des clients
2. **Sélection intelligente des collections** en fonction du client et de la question
3. **Détection améliorée du client** avec gestion des cas particuliers (comme RONDOT)
4. **Configuration de secours** pour pallier les problèmes de variables d'environnement
"""
    
    with open("INSTRUCTIONS.md", "w") as f:
        f.write(instructions)
    
    print("\n✅ Instructions générées dans INSTRUCTIONS.md")

async def main():
    """Fonction principale"""
    try:
        print("🔍 Analyse et correction des dépendances manquantes...")
        
        # Initialiser les dépendances
        success = await init_dependencies()
        
        # Générer des instructions
        await generer_instructions()
        
        if success:
            print("\n✅ Dépendances initialisées avec succès")
            print("➡️ Suivez les instructions dans INSTRUCTIONS.md pour appliquer les correctifs")
        else:
            print("\n⚠️ Certaines dépendances n'ont pas pu être initialisées")
            print("➡️ Consultez le fichier dependencies_fix.log pour plus de détails")
            print("➡️ Vérifiez les variables d'environnement et réexécutez ce script")
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
