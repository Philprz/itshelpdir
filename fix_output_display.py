import os
import asyncio
import logging
import json
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional
import tempfile
import sys

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)

# Désactivation temporaire des logs standard pour éviter le désordre
logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])
logger = logging.getLogger('ITS_HELP')

print("\nVariables d'environnement chargées.\n")

# Import après chargement des variables d'environnement
from chatbot import ChatBot  # noqa: E402
from gestion_clients import initialiser_base_clients  # noqa: E402

class TestResult:
    """Classe pour stocker les résultats de test de manière structurée"""
    
    def __init__(self, question: str):
        self.question = question
        self.response = None
        self.success = False
        self.client_detected = None
        self.error = None
        self.execution_time = 0.0
        self.blocks_count = 0
        self.text_response = ""
    
    def to_dict(self) -> Dict:
        """Convertit le résultat en dictionnaire"""
        return {
            "question": self.question,
            "success": self.success,
            "client_detected": self.client_detected,
            "execution_time": f"{self.execution_time:.2f}s",
            "error": self.error,
            "blocks_count": self.blocks_count,
            "text_response": self.text_response[:150] + "..." if len(self.text_response) > 150 else self.text_response
        }

class ChatbotFixRunner:
    """Classe pour tester et corriger le chatbot avec une gestion propre des sorties"""
    
    def __init__(self):
        self.chatbot = None
        self.results = []
    
    async def initialize(self):
        """Initialise le chatbot et les dépendances nécessaires"""
        # Redirection temporaire des logs pour éviter la pollution de la console
        with open(os.devnull, 'w') as devnull:
            old_stdout = sys.stdout
            sys.stdout = devnull
            
            try:
                await initialiser_base_clients()
                
                # Récupération des clés API
                openai_key = os.getenv('OPENAI_API_KEY')
                qdrant_url = os.getenv('QDRANT_URL')
                qdrant_api_key = os.getenv('QDRANT_API_KEY')
                
                if not openai_key or not qdrant_url:
                    raise ValueError("Clés API manquantes: OPENAI_API_KEY ou QDRANT_URL")
                
                # Initialisation du ChatBot
                self.chatbot = ChatBot(
                    openai_key=openai_key,
                    qdrant_url=qdrant_url,
                    qdrant_api_key=qdrant_api_key
                )
            finally:
                sys.stdout = old_stdout
        
        print("✅ Chatbot et dépendances initialisés")
    
    async def run_test_query(self, question: str) -> TestResult:
        """
        Exécute une requête sur le chatbot et capture proprement la réponse
        """
        result = TestResult(question)
        
        try:
            # Redirection temporaire des logs
            with open(os.devnull, 'w') as devnull:
                old_stdout = sys.stdout
                sys.stdout = devnull
                
                # Mesure du temps d'exécution
                start_time = asyncio.get_event_loop().time()
                
                try:
                    # Création d'un objet conversation simulé
                    conversation = {"id": "test_conversation", "user_id": "test_user"}
                    
                    # Traitement de la question
                    response = await self.chatbot.process_web_message(
                        text=question,
                        conversation=conversation,
                        user_id="test_user",
                        mode="guide"  # Mode plus léger
                    )
                    
                    # Mesure du temps écoulé
                    end_time = asyncio.get_event_loop().time()
                    result.execution_time = end_time - start_time
                    
                    # Traitement de la réponse
                    if response:
                        result.success = True
                        result.response = response
                        
                        # Extraire les métadonnées importantes
                        if isinstance(response, dict):
                            # Client détecté
                            metadata = response.get("metadata", {})
                            result.client_detected = metadata.get("client", "Non spécifié")
                            
                            # Texte et blocs
                            result.text_response = response.get("text", "")
                            result.blocks_count = len(response.get("blocks", []))
                    else:
                        result.success = False
                        result.error = "Aucune réponse reçue"
                
                except Exception as e:
                    result.success = False
                    result.error = str(e)
                
                finally:
                    sys.stdout = old_stdout
        
        except Exception as e:
            result.success = False
            result.error = f"Erreur critique: {str(e)}"
        
        return result
    
    async def run_tests(self):
        """Exécute une série de tests sur le chatbot"""
        print("\nExécution des tests du chatbot...\n")
        
        # Questions de test
        test_questions = [
            # Test client spécifique
            "Quels sont les derniers tickets de RONDOT?",
            
            # Test avec date
            "Tickets ouverts chez RONDOT entre le 01/01/2025 et le 01/03/2025",
            
            # Test ERP
            "Comment paramétrer un compte fournisseur dans NetSuite?",
            
            # Test général
            "Comment résoudre un problème de connexion VPN?"
        ]
        
        # Exécution des tests
        for i, question in enumerate(test_questions, 1):
            print(f"Test {i}/{len(test_questions)}: {question}")
            result = await self.run_test_query(question)
            self.results.append(result)
            
            # Affichage du résultat
            status = "✅ RÉUSSI" if result.success else "❌ ÉCHEC"
            print(f"  {status} - Temps: {result.execution_time:.2f}s")
            print(f"  Client détecté: {result.client_detected}")
            
            if result.error:
                print(f"  Erreur: {result.error}")
            elif result.success:
                print(f"  Réponse reçue: {len(result.text_response)} caractères, {result.blocks_count} blocs")
            
            print()
            
            # Pause entre les requêtes
            await asyncio.sleep(1)
    
    def print_detailed_results(self):
        """Affiche les résultats détaillés des tests"""
        print("\n" + "="*80)
        print("RÉSULTATS DÉTAILLÉS DES TESTS")
        print("="*80 + "\n")
        
        if not self.results:
            print("Aucun test n'a été exécuté.")
            return
        
        success_count = sum(1 for r in self.results if r.success)
        print(f"Tests réussis: {success_count}/{len(self.results)}")
        
        for i, result in enumerate(self.results, 1):
            print(f"\nTest {i}: {result.question}")
            print("-" * 40)
            
            if result.success:
                print(f"✅ Statut: Réussi")
                print(f"⏱️ Temps d'exécution: {result.execution_time:.2f}s")
                print(f"👤 Client détecté: {result.client_detected}")
                print(f"📊 Nombre de blocs: {result.blocks_count}")
                print(f"💬 Réponse: {result.text_response[:150]}..." if len(result.text_response) > 150 else f"💬 Réponse: {result.text_response}")
            else:
                print(f"❌ Statut: Échec")
                print(f"⏱️ Temps d'exécution: {result.execution_time:.2f}s")
                print(f"❗ Erreur: {result.error}")
    
    def save_results_to_file(self, filename="chatbot_test_results.json"):
        """Sauvegarde les résultats dans un fichier JSON"""
        try:
            results_json = [result.to_dict() for result in self.results]
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results_json, f, ensure_ascii=False, indent=2)
            
            print(f"\nRésultats sauvegardés dans {filename}")
        except Exception as e:
            print(f"\nErreur lors de la sauvegarde des résultats: {str(e)}")

async def main():
    try:
        # Création et initialisation du runner
        runner = ChatbotFixRunner()
        await runner.initialize()
        
        # Exécution des tests
        await runner.run_tests()
        
        # Affichage des résultats détaillés
        runner.print_detailed_results()
        
        # Sauvegarde des résultats
        runner.save_results_to_file()
        
    except Exception as e:
        print(f"❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
