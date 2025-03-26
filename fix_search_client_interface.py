import os
import asyncio
import logging
import json
from dotenv import load_dotenv

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)

# Configuration du logging
log_file = "interface_fix.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    filename=log_file,
    filemode='w'
)
logger = logging.getLogger('ITS_HELP')

print(f"\nVariables d'environnement chargées. Logs écrits dans {log_file}\n")

# Import après chargement des variables d'environnement
from search_factory import search_factory  # noqa: E402
from gestion_clients import initialiser_base_clients  # noqa: E402

class SearchClientValidator:
    """
    Classe qui vérifie et corrige les problèmes d'interface des clients de recherche
    """
    
    def __init__(self):
        self.client_types = [
            "jira", "zendesk", "confluence", 
            "netsuite", "netsuite_dummies", "sap"
        ]
        self.issues = []
        self.fixes = []
    
    async def initialize(self):
        """Initialise les dépendances nécessaires"""
        await initialiser_base_clients()
        await search_factory.initialize()
        logger.info("Validator initialisé")
        print("✅ Validator initialisé")
    
    async def validate_client_interfaces(self):
        """
        Valide l'interface des clients de recherche
        """
        print("\nValidation des interfaces des clients de recherche:")
        
        for client_type in self.client_types:
            print(f"⏳ Validation du client {client_type}...")
            
            try:
                # Récupérer le client depuis le factory
                client = await search_factory.get_client(client_type)
                
                if not client:
                    issue = f"Client {client_type} non disponible"
                    self.issues.append(issue)
                    logger.error(issue)
                    print(f"  ❌ {issue}")
                    continue
                
                # Vérifier si le client a l'interface attendue
                has_search_method = hasattr(client, 'recherche_intelligente')
                client_class = type(client).__name__
                
                if not has_search_method:
                    issue = f"Client {client_type} ({client_class}) n'a pas la méthode 'recherche_intelligente'"
                    self.issues.append(issue)
                    logger.error(issue)
                    print(f"  ❌ {issue}")
                    continue
                
                # Vérifier la méthode recherche_intelligente est callable
                if not callable(getattr(client, 'recherche_intelligente')):
                    issue = f"La méthode 'recherche_intelligente' de {client_type} n'est pas callable"
                    self.issues.append(issue)
                    logger.error(issue)
                    print(f"  ❌ {issue}")
                    continue
                
                # Tester si le client retourne bien des résultats avec une requête simple
                try:
                    results = await client.recherche_intelligente(
                        question="test",
                        limit=1
                    )
                    
                    if results is None:
                        issue = f"Client {client_type} retourne None au lieu d'une liste"
                        self.issues.append(issue)
                        logger.error(issue)
                        print(f"  ⚠️ {issue}")
                    elif not isinstance(results, list):
                        issue = f"Client {client_type} retourne {type(results)} au lieu d'une liste"
                        self.issues.append(issue)
                        logger.error(issue)
                        print(f"  ⚠️ {issue}")
                    else:
                        logger.info(f"Client {client_type} validé avec succès")
                        print(f"  ✅ Client {client_type} validé avec succès")
                
                except Exception as e:
                    issue = f"Erreur lors de l'appel à recherche_intelligente sur {client_type}: {str(e)}"
                    self.issues.append(issue)
                    logger.error(issue)
                    print(f"  ❌ {issue}")
            
            except Exception as e:
                issue = f"Erreur lors de la validation du client {client_type}: {str(e)}"
                self.issues.append(issue)
                logger.error(issue)
                print(f"  ❌ {issue}")
    
    async def patch_chatbot_search_coordination(self):
        """
        Vérifie si la méthode recherche_coordonnee du chatbot fonctionne correctement
        et propose des corrections
        """
        print("\nAnalyse de la méthode recherche_coordonnee:")
        
        try:
            # Import local pour éviter les imports circulaires
            from chatbot import ChatBot
            
            # Examiner le code source de recherche_coordonnee
            import inspect
            source = inspect.getsource(ChatBot.recherche_coordonnee)
            
            # Vérifier si la méthode contient certains patterns problématiques
            issues = []
            
            if "await search_factory.get_client" in source and "if client and not isinstance(client, Exception)" in source:
                # C'est correct - le code vérifie déjà correctement
                print("  ✅ Vérification du client retourné par get_client: OK")
            else:
                issues.append("Le code ne vérifie pas correctement si le client est une Exception")
                print("  ⚠️ Vérification du client retourné par get_client: MANQUANTE")
            
            if "if not clients:" in source and "return []" in source:
                # C'est correct - le code gère le cas où aucun client n'est disponible
                print("  ✅ Gestion des clients vides: OK")
            else:
                issues.append("Le code ne gère pas correctement le cas où aucun client n'est disponible")
                print("  ⚠️ Gestion des clients vides: MANQUANTE")
            
            if issues:
                self.issues.extend(issues)
                
                # Proposition de correction
                fix = """
                # Correction proposée pour la méthode recherche_coordonnee:
                
                1. Assurez-vous que le code vérifie si le client est une Exception:
                ```python
                client = await search_factory.get_client(source_type)
                if client and not isinstance(client, Exception):
                    # ...
                ```
                
                2. Assurez-vous que le code gère correctement le cas où aucun client n'est disponible:
                ```python
                if not clients:
                    self.logger.error("Aucun client de recherche disponible pour cette requête.")
                    return []
                ```
                """
                self.fixes.append(("recherche_coordonnee", fix))
                print(f"  ⚠️ Des corrections sont proposées pour recherche_coordonnee")
            else:
                print(f"  ✅ La méthode recherche_coordonnee semble correctement implémentée")
        
        except Exception as e:
            issue = f"Erreur lors de l'analyse de recherche_coordonnee: {str(e)}"
            self.issues.append(issue)
            logger.error(issue)
            print(f"  ❌ {issue}")
    
    async def patch_search_factory(self):
        """
        Vérifie et corrige les problèmes potentiels dans le search_factory
        """
        print("\nAnalyse du search_factory:")
        
        try:
            # Vérifier si l'initialisation est correcte
            import inspect
            source = inspect.getsource(search_factory.__class__.initialize)
            
            # Vérifier si async with asyncio.timeout et asyncio.wait_for sont utilisés
            issues = []
            
            if "async with asyncio.timeout" in source or "asyncio.wait_for" in source:
                print("  ✅ Protection par timeout: OK")
            else:
                issues.append("Pas de protection par timeout dans l'initialisation du search_factory")
                print("  ⚠️ Protection par timeout: MANQUANTE")
            
            if "asyncio.gather" in source and "return_exceptions=True" in source:
                print("  ✅ Gestion des exceptions avec asyncio.gather: OK")
            else:
                issues.append("Pas de gestion correcte des exceptions avec asyncio.gather")
                print("  ⚠️ Gestion des exceptions avec asyncio.gather: MANQUANTE ou INCORRECTE")
            
            # Vérifier si le get_client a une bonne gestion des erreurs
            source = inspect.getsource(search_factory.__class__.get_client)
            
            if "fallback_enabled" in source and "return self._create_fallback_client" in source:
                print("  ✅ Mécanisme de fallback: OK")
            else:
                issues.append("Pas de mécanisme de fallback dans get_client")
                print("  ⚠️ Mécanisme de fallback: MANQUANT")
            
            if issues:
                self.issues.extend(issues)
                
                # Proposition de correction
                fix = """
                # Corrections proposées pour search_factory:
                
                1. Ajoutez une protection par timeout dans la méthode initialize:
                ```python
                async def initialize(self):
                    try:
                        async with asyncio.timeout(30):  # 30 secondes max
                            # Code d'initialisation
                    except asyncio.TimeoutError:
                        self.logger.error("Timeout lors de l'initialisation du search_factory")
                ```
                
                2. Assurez-vous d'utiliser asyncio.gather avec gestion d'exceptions:
                ```python
                results = await asyncio.gather(
                    self._initialize_client("jira", "jira"),
                    # autres clients
                    return_exceptions=True
                )
                ```
                
                3. Vérifiez que get_client a un mécanisme de fallback:
                ```python
                if fallback_enabled:
                    return self._create_fallback_client(client_type, collection_name)
                ```
                """
                self.fixes.append(("search_factory", fix))
                print(f"  ⚠️ Des corrections sont proposées pour search_factory")
            else:
                print(f"  ✅ Le search_factory semble correctement implémenté")
                
        except Exception as e:
            issue = f"Erreur lors de l'analyse du search_factory: {str(e)}"
            self.issues.append(issue)
            logger.error(issue)
            print(f"  ❌ {issue}")
    
    def print_summary(self):
        """Affiche un résumé des problèmes et des corrections proposées"""
        print("\n" + "="*60)
        print("RÉSUMÉ DU DIAGNOSTIC")
        print("="*60)
        
        if not self.issues:
            print("\n✅ Aucun problème détecté!")
            return
        
        print(f"\nProblèmes détectés ({len(self.issues)}):")
        for i, issue in enumerate(self.issues, 1):
            print(f"{i}. ❌ {issue}")
        
        if self.fixes:
            print(f"\nCorrections proposées ({len(self.fixes)}):")
            for i, (component, fix) in enumerate(self.fixes, 1):
                print(f"{i}. 🔧 Pour {component}:")
                print(f"{fix}")
        
        print("\nPour plus de détails, consultez le fichier log:", log_file)

async def main():
    try:
        validator = SearchClientValidator()
        await validator.initialize()
        
        # Valider les interfaces des clients
        await validator.validate_client_interfaces()
        
        # Vérifier la méthode recherche_coordonnee
        await validator.patch_chatbot_search_coordination()
        
        # Vérifier le search_factory
        await validator.patch_search_factory()
        
        # Afficher le résumé
        validator.print_summary()
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)
        print(f"❌ Erreur critique: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
