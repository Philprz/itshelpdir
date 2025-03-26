"""
Solution finale pour le chatbot

Ce script fournit une solution directe pour corriger les problèmes d'affichage 
et d'exécution du chatbot sans modifier sa structure existante.
"""

import os
import asyncio
import logging
from dotenv import load_dotenv
import json

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)

print("\nVariables d'environnement chargées.\n")

# Import après chargement des variables d'environnement
from gestion_clients import initialiser_base_clients, extract_client_name  # noqa: E402
from chatbot import ChatBot  # noqa: E402
from search_factory import search_factory  # noqa: E402

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("chatbot_fix.log", mode="w"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ITS_HELP.fix")

# Cette fonction exécute directement le test avec le client RONDOT
async def test_rondot_search():
    """
    Test direct de recherche pour RONDOT en utilisant les interfaces existantes
    """
    try:
        # 1. Initialisation
        print("Initialisation de la base des clients...")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée")
        
        # Initialisation du ChatBot
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        print("Initialisation du ChatBot...")
        chatbot = ChatBot(
            openai_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key
        )
        print("✅ ChatBot initialisé")
        
        # 2. Test direct de la recherche pour RONDOT
        print("\n🔍 Test direct de recherche pour RONDOT...")
        
        # Définir manuellement le client RONDOT
        client_info = {"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        
        # Définir les collections à interroger
        collections = ["jira", "zendesk", "confluence"]
        
        # Appel direct à recherche_coordonnee sans passer par process_web_message
        print("Appel à recherche_coordonnee...")
        resultats = await chatbot.recherche_coordonnee(
            collections=collections,
            question="Quels sont les derniers tickets de RONDOT?",
            client_info=client_info
        )
        
        # 3. Analyse des résultats
        print(f"Nombre de résultats: {len(resultats) if resultats else 0}")
        
        if resultats and len(resultats) > 0:
            print("\n✅ Des résultats ont été trouvés!")
            
            # Sauvegarde des résultats dans un fichier JSON
            simplified_results = []
            
            for i, result in enumerate(resultats[:5], 1):  # Limiter à 5 résultats
                print(f"\nRésultat {i}:")
                
                simplified = {}
                
                # Score
                if hasattr(result, 'score'):
                    simplified['score'] = result.score
                    print(f"Score: {result.score}")
                
                # Payload
                if hasattr(result, 'payload'):
                    payload = result.payload
                    simplified['payload'] = {}
                    
                    # Extraire les champs communs
                    for field in ['title', 'summary', 'subject', 'content', 'description', 'key', 
                                 'ticket_id', 'id', 'status', 'client', 'url', 'page_url']:
                        if field in payload:
                            value = payload.get(field)
                            simplified['payload'][field] = value
                            
                            # Limiter l'affichage pour les champs textuels longs
                            if field in ['content', 'description'] and isinstance(value, str) and len(value) > 100:
                                print(f"{field}: {value[:100]}...")
                            else:
                                print(f"{field}: {value}")
                
                simplified_results.append(simplified)
            
            # Sauvegarder dans un fichier JSON
            with open("rondot_results.json", "w", encoding="utf-8") as f:
                json.dump(simplified_results, f, ensure_ascii=False, indent=2)
            
            print("\n✅ Résultats sauvegardés dans rondot_results.json")
            
            return True
        else:
            print("\n❌ Aucun résultat trouvé pour RONDOT")
            return False
    
    except Exception as e:
        print(f"\n❌ Erreur lors du test: {str(e)}")
        logger.error(f"Erreur lors du test: {str(e)}", exc_info=True)
        return False

# Cette fonction crée un script de correction
def generate_correction_script():
    """
    Génère un script de correction pour chatbot.py
    """
    correction = '''
# Correction pour chatbot.py

# 1. Fonction pour déterminer les collections en fonction du client et de la question
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

# 2. Appliquer cette modification dans process_web_message:
# Dans la méthode process_web_message, remplacer l'appel à recherche_coordonnee par:
"""
client_info = await self.determiner_client(text)
client_name = client_info.get('source') if client_info else 'Non spécifié'
self.logger.info(f"Client trouvé: {client_name}")

# Déterminer les collections à interroger en fonction du client et de la question
collections = collections_par_client_et_question(client_name, text)
self.logger.info(f"Collections sélectionnées: {collections}")

# Effectuer la recherche coordonnée
resultats = await self.recherche_coordonnee(
    collections=collections,
    question=text,
    client_info=client_info
)
"""
'''
    
    # Écrire dans un fichier
    with open("correction_chatbot.py", "w", encoding="utf-8") as f:
        f.write(correction)
    
    print("\n✅ Script de correction généré dans correction_chatbot.py")

async def main():
    """
    Fonction principale
    """
    # 1. Exécuter le test direct pour RONDOT
    success = await test_rondot_search()
    
    # 2. Générer le script de correction
    generate_correction_script()
    
    # 3. Afficher les recommandations
    print("\n📋 RECOMMANDATIONS POUR CORRIGER LE CHATBOT:")
    print("1. Le problème principal est la sélection des collections dans process_web_message")
    print("2. La fonction extract_client_name doit être correctement intégrée")
    print("3. La sélection des collections doit être adaptée au client et à la question")
    print("4. Les modifications sont documentées dans correction_chatbot.py")
    
    if success:
        print("\n✅ La recherche directe fonctionne ! Appliquez les correctifs proposés.")
    else:
        print("\n⚠️ Des problèmes persistent. Vérifiez les logs pour plus de détails.")

if __name__ == "__main__":
    asyncio.run(main())
