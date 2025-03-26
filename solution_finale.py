"""
Solution finale pour le chatbot

Ce script génère les correctifs nécessaires pour résoudre les problèmes du chatbot,
notamment les dépendances manquantes et la détection de clients.
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
        logging.FileHandler("solution.log", mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ITS_HELP.solution")

print("\nVariables d'environnement chargées.\n")

# Import après chargement des variables d'environnement
from gestion_clients import initialiser_base_clients  # noqa: E402

async def generer_correctifs():
    """Génère les fichiers de correctifs nécessaires"""
    try:
        # 1. Initialisation
        print("Initialisation de la base des clients...")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée")
        
        # 2. Création du fichier de configuration
        print("\nCréation du fichier de configuration...")
        
        config = f"""
# Configuration pour les clients de recherche
# Généré automatiquement par solution_finale.py

import os

# Clés API
OPENAI_API_KEY = "{os.getenv('OPENAI_API_KEY')}"
QDRANT_URL = "{os.getenv('QDRANT_URL')}"
QDRANT_API_KEY = "{os.getenv('QDRANT_API_KEY')}"

# Collections pour chaque type de client
COLLECTIONS = {{
    "jira": "jira",
    "zendesk": "zendesk", 
    "confluence": "confluence",
    "netsuite": "netsuite",
    "netsuite_dummies": "netsuite_dummies",
    "sap": "sap"
}}

# Mapping des clients spécifiques
CLIENT_MAPPING = {{
    "RONDOT": ["jira", "zendesk", "confluence"]
}}
"""
        
        with open("config.py", "w") as f:
            f.write(config)
        
        print("✅ Fichier de configuration créé")
        
        # 3. Création du correctif pour search_factory
        print("\nCréation du correctif pour search_factory.py...")
        
        search_factory_fix = """
# Correctif pour search_factory.py

# Ajoutez ce code au début du fichier
from typing import Dict, Any, List, Optional
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

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

# Remplacez la méthode _initialize_client par celle-ci
async def _initialize_client(self, client_type: str, collection_name: str = None, fallback_enabled: bool = True) -> Optional[Any]:
    '''Initialisation sécurisée d'un client de recherche'''
    try:
        # Vérifier les variables d'environnement
        if not OPENAI_API_KEY or not QDRANT_URL:
            logger.error(f"Variables d'environnement manquantes pour {client_type}")
            return None
            
        # Déterminer la collection à utiliser
        actual_collection = collection_name or COLLECTIONS.get(client_type, client_type)
        
        # Créer le client en fonction du type
        if client_type in ["jira", "zendesk", "confluence", "netsuite", "netsuite_dummies", "sap"]:
            # Importer dynamiquement pour éviter les problèmes d'importation circulaire
            from qdrant_search_clients import QdrantSearchClientFactory
            
            factory = QdrantSearchClientFactory(
                qdrant_url=QDRANT_URL,
                qdrant_api_key=QDRANT_API_KEY,
                openai_api_key=OPENAI_API_KEY
            )
            
            client = factory.create_search_client(collection_name=actual_collection)
            
            if client:
                logger.info(f"Client {client_type} initialisé avec succès")
                # Mettre en cache
                self._clients_cache[client_type] = client
                return client
        
        logger.error(f"Échec de l'initialisation du client {client_type}")
        return None
            
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du client {client_type}: {str(e)}")
        return None
"""
        
        with open("search_factory_fix.py", "w") as f:
            f.write(search_factory_fix)
        
        print("✅ Correctif pour search_factory.py créé")
        
        # 4. Création du correctif pour chatbot.py
        print("\nCréation du correctif pour chatbot.py...")
        
        chatbot_fix = """
# Correctif pour chatbot.py

# Fonctions à ajouter au début du fichier
def collections_par_client(client_name, question):
    '''Détermine les collections à interroger en fonction du client et de la question'''
    # Importer la configuration si disponible
    try:
        from config import CLIENT_MAPPING
        if client_name in CLIENT_MAPPING:
            return CLIENT_MAPPING[client_name]
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
        logger.error(f"Erreur lors de l'extraction du client: {str(e)}")
        
        # Recherche explicite de RONDOT dans le texte comme fallback
        if "RONDOT" in text.upper():
            return {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        
        return None

# Remplacer la méthode process_web_message par cette version
async def process_web_message(self, text: str, conversation: Any, user_id: str, mode: str = "detail"):
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
        }
"""
        
        with open("chatbot_fix.py", "w") as f:
            f.write(chatbot_fix)
        
        print("✅ Correctif pour chatbot.py créé")
        
        # 5. Création du guide d'installation
        print("\nCréation du guide d'installation...")
        
        guide = """
# Guide d'installation des correctifs

## 1. Préparation

Avant d'appliquer les correctifs, assurez-vous que:
- Les variables d'environnement sont correctement configurées
- Le fichier `config.py` a été créé avec les bonnes valeurs

## 2. Application des correctifs

### Pour search_factory.py:

1. Ouvrez le fichier `search_factory.py`
2. Ajoutez les imports et la configuration au début du fichier (voir `search_factory_fix.py`)
3. Remplacez la méthode `_initialize_client` par la version corrigée

### Pour chatbot.py:

1. Ouvrez le fichier `chatbot.py`
2. Ajoutez les fonctions `collections_par_client` et `extract_client_name_robust` au début du fichier
3. Remplacez la méthode `process_web_message` par la version corrigée

## 3. Test

Pour tester les correctifs:

1. Créez un script de test qui utilise le chatbot avec la question "Quels sont les derniers tickets de RONDOT?"
2. Vérifiez que:
   - Le client est correctement détecté
   - Les collections appropriées sont sélectionnées
   - Les résultats sont correctement affichés

## 4. Résumé des problèmes corrigés

1. **Dépendances manquantes**: 
   - Utilisation d'une configuration centralisée pour les clés API
   - Gestion robuste des erreurs d'initialisation

2. **Détection de client**:
   - Méthode robuste pour extraire le client
   - Détection spécifique pour RONDOT

3. **Sélection des collections**:
   - Sélection intelligente basée sur le client et la question
   - Configuration centralisée des collections par client

4. **Gestion des erreurs**:
   - Logging amélioré
   - Messages d'erreur clairs pour l'utilisateur
"""
        
        with open("GUIDE_INSTALLATION.md", "w") as f:
            f.write(guide)
        
        print("✅ Guide d'installation créé")
        
        return True
        
    except Exception as e:
        logger.error(f"Erreur lors de la génération des correctifs: {str(e)}", exc_info=True)
        print(f"\n❌ Erreur critique: {str(e)}")
        return False

async def main():
    """Fonction principale"""
    try:
        print("🔧 Génération des correctifs pour le chatbot...")
        
        success = await generer_correctifs()
        
        if success:
            print("\n✅ Correctifs générés avec succès")
            print("➡️ Pour appliquer les correctifs, suivez les instructions dans GUIDE_INSTALLATION.md")
        else:
            print("\n⚠️ Des erreurs se sont produites lors de la génération des correctifs")
            print("➡️ Consultez le fichier solution.log pour plus de détails")
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)
        print(f"\n❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
