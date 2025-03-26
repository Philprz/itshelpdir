import os
import asyncio
import logging
import json
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)

# Configuration du logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('ITS_HELP')

print("\nVariables d'environnement chargées.\n")

# Import après chargement des variables d'environnement
from chatbot import ChatBot  # noqa: E402
from gestion_clients import initialiser_base_clients, extract_client_name  # noqa: E402
from search_factory import search_factory  # noqa: E402

class ChatBotFixer:
    """Classe pour diagnostiquer et corriger les problèmes du ChatBot"""
    
    def __init__(self):
        self.chatbot = None
        self.initialized = False
    
    async def initialize(self):
        """Initialise le chatbot et les dépendances nécessaires"""
        # Initialisation de la base des clients
        print("Initialisation de la base des clients...")
        await initialiser_base_clients()
        print("✅ Base des clients initialisée")
        
        # Initialisation du search factory
        print("Initialisation du search factory...")
        await search_factory.initialize()
        print("✅ Search factory initialisé")
        
        # Récupération des clés API
        openai_key = os.getenv('OPENAI_API_KEY')
        qdrant_url = os.getenv('QDRANT_URL')
        qdrant_api_key = os.getenv('QDRANT_API_KEY')
        
        if not openai_key or not qdrant_url:
            raise ValueError("Clés API manquantes: OPENAI_API_KEY ou QDRANT_URL")
        
        # Initialisation du ChatBot
        print("Initialisation du ChatBot...")
        self.chatbot = ChatBot(
            openai_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key
        )
        print("✅ ChatBot initialisé")
        
        self.initialized = True
    
    async def test_client_detection(self, text: str):
        """Teste spécifiquement la détection de client pour un texte donné"""
        print(f"\nTest de détection de client pour: '{text}'")
        
        try:
            # Test direct de la fonction extract_client_name
            client_info = extract_client_name(text)
            print(f"Résultat de extract_client_name: {client_info}")
            
            # Test de la détection via le chatbot
            if self.chatbot and hasattr(self.chatbot, 'determiner_client'):
                client_chatbot = await self.chatbot.determiner_client(text)
                print(f"Résultat de ChatBot.determiner_client: {client_chatbot}")
            else:
                print("❌ La méthode determiner_client n'est pas disponible dans le chatbot")
        
        except Exception as e:
            print(f"❌ Erreur lors du test de détection: {str(e)}")
    
    async def test_search_coordination(self, question: str, client_info: Optional[Dict] = None):
        """Teste spécifiquement la coordination de recherche pour une question donnée"""
        print(f"\nTest de coordination de recherche pour: '{question}'")
        
        if not self.chatbot or not hasattr(self.chatbot, 'recherche_coordonnee'):
            print("❌ La méthode recherche_coordonnee n'est pas disponible dans le chatbot")
            return None
        
        try:
            # Si client_info n'est pas fourni, essayer de le détecter
            if client_info is None:
                client_info = extract_client_name(question)
                print(f"Client détecté: {client_info}")
            
            # Appel direct à la méthode recherche_coordonnee
            resultats = await self.chatbot.recherche_coordonnee(
                question=question,
                client_info=client_info,
                context_limit=20,
                top_k_zendesk=5
            )
            
            # Affichage des résultats
            print(f"Nombre de résultats: {len(resultats) if resultats else 0}")
            
            # Afficher un aperçu des résultats
            if resultats and len(resultats) > 0:
                print("\nAperçu des résultats:")
                for i, resultat in enumerate(resultats[:3], 1):  # Montrer jusqu'à 3 résultats
                    print(f"Résultat {i}:")
                    
                    # Essayer d'extraire des informations pertinentes
                    if hasattr(resultat, 'payload'):
                        payload = resultat.payload
                        for key in ['title', 'summary', 'subject', 'key']:
                            if key in payload:
                                print(f"  {key}: {payload[key]}")
                    
                    # Score
                    if hasattr(resultat, 'score'):
                        print(f"  score: {resultat.score}")
            
            return resultats
        
        except Exception as e:
            print(f"❌ Erreur lors du test de recherche: {str(e)}")
            return None
    
    async def patch_process_web_message(self):
        """Fournit un correctif pour process_web_message si nécessaire"""
        print("\nAnalyse de process_web_message:")
        
        if not self.initialized:
            print("❌ ChatBotFixer n'est pas initialisé")
            return
        
        # Vérifier l'implémentation actuelle
        import inspect
        
        try:
            source = inspect.getsource(ChatBot.process_web_message)
            
            # Analyse des problèmes potentiels
            issues = []
            
            # Vérifier le traitement du client
            if "client_info = await self.determiner_client(text)" not in source:
                issues.append("La détection de client pourrait être incorrecte")
            
            # Vérifier la coordination de recherche
            if "resultats = await self.recherche_coordonnee" not in source:
                issues.append("La coordination de recherche pourrait être incorrecte")
            
            # Vérifier le traitement des résultats vides
            if "if not resultats:" not in source:
                issues.append("Le traitement des résultats vides pourrait être incorrect")
            
            # Afficher les problèmes
            if issues:
                print("⚠️ Problèmes potentiels détectés:")
                for issue in issues:
                    print(f"  - {issue}")
                
                # Proposition de correctif
                print("\n🔧 Correctif proposé pour process_web_message:")
                print("""
                Ajoutez ce code pour corriger la méthode process_web_message:
                
                ```python
                async def process_web_message(self, text: str, conversation: Any, user_id: str, mode: str = "detail"):
                    self.logger.info(f"Traitement du message: {text}")
                    
                    try:
                        # 1. Analyser la question (déjà implémenté)
                        analysis = await asyncio.wait_for(self.analyze_question(text), timeout=60)
                        
                        # 2. Déterminer le client explicitement
                        client_info = await self.determiner_client(text)
                        self.logger.info(f"Client trouvé: {client_info.get('source') if client_info else 'Non spécifié'}")
                        
                        # 3. Effectuer la recherche avec le client détecté
                        self.logger.info(f"Lancement de la recherche pour: {text}")
                        resultats = await self.recherche_coordonnee(
                            question=text,
                            client_info=client_info,
                            context_limit=20,
                            top_k_zendesk=5
                        )
                        
                        # 4. Vérifier si des résultats ont été trouvés
                        if not resultats or len(resultats) == 0:
                            self.logger.warning(f"Aucun résultat trouvé pour: {text}")
                            return self._generate_empty_response()
                        
                        # 5. Générer la réponse avec les résultats trouvés
                        self.logger.info(f"{len(resultats)} résultats trouvés, génération de la réponse...")
                        
                        # Générer la réponse finale
                        # ... (reste du code inchangé)
                    
                    except Exception as e:
                        self.logger.error(f"Erreur lors du traitement du message: {str(e)}", exc_info=True)
                        return self._generate_error_response(str(e))
                    
                # Ajoutez également cette méthode utilitaire
                def _generate_empty_response(self):
                    return {
                        "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question.",
                        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Désolé, je n'ai trouvé aucun résultat pertinent pour votre question."}}],
                        "metadata": {"client": "Non spécifié"}
                    }
                ```
                """)
            else:
                print("✅ process_web_message semble correctement implémenté")
        
        except Exception as e:
            print(f"❌ Erreur lors de l'analyse: {str(e)}")
    
    async def run_diagnostic(self):
        """Exécute un diagnostic complet du chatbot"""
        if not self.initialized:
            await self.initialize()
        
        # 1. Test de la détection de client
        await self.test_client_detection("Quels sont les derniers tickets de RONDOT?")
        await self.test_client_detection("Tickets ouverts chez RONDOT entre le 01/01/2025 et le 01/03/2025")
        
        # 2. Test de la coordination de recherche
        await self.test_search_coordination(
            "Comment paramétrer un compte fournisseur dans NetSuite?",
            client_info=None  # Laisser la détection automatique
        )
        
        # 3. Test de la coordination de recherche avec client spécifié
        await self.test_search_coordination(
            "Quels sont les derniers tickets?",
            client_info={"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"}
        )
        
        # 4. Analyse de process_web_message
        await self.patch_process_web_message()

async def main():
    try:
        fixer = ChatBotFixer()
        await fixer.run_diagnostic()
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)
        print(f"❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
