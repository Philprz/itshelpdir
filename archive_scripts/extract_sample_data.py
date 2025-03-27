import os
import asyncio
import logging
import json
from dotenv import load_dotenv
from typing import Dict, List, Any

# Chargement des variables d'environnement AVANT toute importation
load_dotenv(verbose=True)
print("\nVariables d'environnement chargées.\n")

# Configuration du logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('ITS_HELP')

# Import après chargement des variables d'environnement
from search_factory import search_factory  # noqa: E402
from gestion_clients import initialiser_base_clients  # noqa: E402

class DataExtractor:
    """Classe pour extraire des données d'exemple de Qdrant"""
    
    def __init__(self):
        self.results = {}
    
    async def initialize(self):
        """Initialise les composants nécessaires"""
        await initialiser_base_clients()
        await search_factory.initialize()
        logger.info("DataExtractor initialisé")
    
    async def extract_client_data(self, client_name: str, source_types: List[str], query: str, limit: int = 5):
        """
        Extrait les données pour un client depuis plusieurs sources
        
        Args:
            client_name: Nom du client (ex: RONDOT)
            source_types: Liste des types de sources (ex: ['jira', 'zendesk'])
            query: Requête à utiliser pour les recherches ERP
            limit: Nombre maximum de résultats à extraire
        """
        logger.info(f"Extraction des données pour {client_name} depuis {', '.join(source_types)}")
        
        # Créer un dictionnaire pour stocker les résultats par source
        self.results[client_name] = {}
        
        for source_type in source_types:
            try:
                # Récupérer le client de recherche
                client = await search_factory.get_client(source_type)
                
                if not client:
                    logger.error(f"Client {source_type} non disponible")
                    continue
                
                logger.info(f"Extraction depuis {source_type} pour {client_name}")
                
                # Pour les clients ERP, utiliser la requête spécifiée
                if source_type in ['netsuite', 'netsuite_dummies', 'sap']:
                    search_query = query
                    client_info = None  # Pas de filtre client pour ERP
                else:
                    # Pour JIRA, ZENDESK, CONFLUENCE, rechercher le client spécifié
                    search_query = client_name
                    client_info = {"source": client_name, "jira": client_name, "zendesk": client_name}
                
                # Exécuter la recherche
                results = await client.recherche_intelligente(
                    question=search_query,
                    client_name=client_info,
                    limit=limit,
                    score_threshold=0.0  # Pas de filtre de score pour maximiser les résultats
                )
                
                if results:
                    logger.info(f"✅ {len(results)} résultats trouvés pour {source_type}")
                    
                    # Convertir les résultats en format sérialisable
                    formatted_results = []
                    for result in results:
                        # Extraire les attributs importants
                        result_dict = {}
                        
                        # Attributs communs
                        if hasattr(result, 'payload'):
                            result_dict['payload'] = result.payload
                        if hasattr(result, 'score'):
                            result_dict['score'] = result.score
                        if hasattr(result, 'id'):
                            result_dict['id'] = result.id
                            
                        # Pour le debug, ajoutons tous les attributs disponibles
                        for attr in dir(result):
                            if not attr.startswith('_') and attr not in ['payload', 'score', 'id']:
                                try:
                                    value = getattr(result, attr)
                                    # Ne prendre que les valeurs simples (pas les méthodes ou objets complexes)
                                    if not callable(value) and isinstance(value, (str, int, float, bool, list, dict)):
                                        result_dict[attr] = value
                                except Exception:
                                    pass
                        
                        formatted_results.append(result_dict)
                    
                    # Stocker les résultats formatés
                    self.results[client_name][source_type] = formatted_results
                else:
                    logger.warning(f"❌ Aucun résultat trouvé pour {source_type} avec la requête '{search_query}'")
                    self.results[client_name][source_type] = []
                    
            except Exception as e:
                logger.error(f"Erreur lors de l'extraction depuis {source_type}: {str(e)}")
                self.results[client_name][source_type] = []
    
    def save_results(self, output_file: str = "extracted_data.json"):
        """Sauvegarde les résultats dans un fichier JSON"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            logger.info(f"Résultats sauvegardés dans {output_file}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des résultats: {str(e)}")
    
    def print_summary(self):
        """Affiche un résumé des données extraites"""
        print("\n" + "="*80)
        print("RÉSUMÉ DES DONNÉES EXTRAITES")
        print("="*80)
        
        for client_name, sources in self.results.items():
            print(f"\nClient: {client_name}")
            for source_type, results in sources.items():
                count = len(results)
                if count > 0:
                    # Afficher un échantillon du premier résultat
                    first_result = results[0]
                    score = first_result.get('score', 'N/A')
                    
                    # Récupérer des champs pertinents selon la source
                    title = None
                    if source_type in ['jira', 'zendesk']:
                        if 'payload' in first_result:
                            payload = first_result['payload']
                            title = payload.get('summary', '') or payload.get('subject', '')
                            if not title:
                                title = payload.get('title', 'Sans titre')
                    elif source_type in ['confluence']:
                        if 'payload' in first_result:
                            payload = first_result['payload']
                            title = payload.get('title', 'Sans titre')
                    elif source_type in ['netsuite', 'netsuite_dummies', 'sap']:
                        if 'payload' in first_result:
                            payload = first_result['payload']
                            title = payload.get('title', 'Sans titre')
                    
                    print(f"  {source_type}: {count} résultats")
                    print(f"    Premier résultat - Score: {score}")
                    if title:
                        print(f"    Titre: {title}")
                else:
                    print(f"  {source_type}: Aucun résultat")
        
        print("\n" + "="*80)

async def main():
    try:
        # Créer l'extracteur
        extractor = DataExtractor()
        await extractor.initialize()
        
        # 1. Extraire les données pour RONDOT
        await extractor.extract_client_data(
            client_name="RONDOT",
            source_types=["jira", "zendesk", "confluence"],
            query="",  # Non utilisé pour ces sources
            limit=5
        )
        
        # 2. Extraire les données ERP
        await extractor.extract_client_data(
            client_name="ERP_DATA",  # Nom arbitraire pour regrouper les données ERP
            source_types=["netsuite", "netsuite_dummies", "sap"],
            query="comment paramétrer le compte fournisseur",
            limit=5
        )
        
        # Afficher un résumé
        extractor.print_summary()
        
        # Sauvegarder les résultats
        extractor.save_results()
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
