import os
import asyncio
import logging
import pprint
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

async def extract_data_from_source(source_type, search_query, client_info=None, limit=5):
    """
    Extrait des données d'une source spécifique.
    
    Args:
        source_type: Type de source (jira, zendesk, etc.)
        search_query: Requête de recherche
        client_info: Informations sur le client (optionnel)
        limit: Nombre maximum de résultats
    
    Returns:
        Liste des résultats extraits (sous forme de dictionnaires simplifiés)
    """
    print(f"\n{'='*60}")
    print(f"EXTRACTION DEPUIS {source_type.upper()}")
    print(f"{'='*60}")
    print(f"Requête: {search_query}")
    if client_info:
        print(f"Client: {client_info.get('source', 'N/A')}")
    
    try:
        # Récupérer le client de recherche
        client = await search_factory.get_client(source_type)
        
        if not client:
            print(f"❌ Client {source_type} non disponible")
            return []
        
        # Exécuter la recherche
        results = await client.recherche_intelligente(
            question=search_query,
            client_name=client_info,
            limit=limit,
            score_threshold=0.0  # Pas de filtre de score pour maximiser les résultats
        )
        
        if not results:
            print(f"❌ Aucun résultat trouvé pour {source_type}")
            return []
        
        print(f"✅ {len(results)} résultats trouvés")
        
        # Extraction des champs essentiels uniquement
        simplified_results = []
        for i, result in enumerate(results, 1):
            simplified = {}
            
            # Score
            if hasattr(result, 'score'):
                simplified['score'] = result.score
            
            # Payload - nous n'extrayons que les champs textuels importants
            if hasattr(result, 'payload'):
                payload = result.payload
                
                # Essayer d'extraire les champs communs
                for field in ['title', 'summary', 'subject', 'content', 'description', 'key', 
                              'ticket_id', 'id', 'status', 'client', 'space_id', 'url', 'page_url']:
                    if field in payload:
                        simplified[field] = payload.get(field)
            
            simplified_results.append(simplified)
            
            # Afficher chaque résultat
            print(f"\nRésultat {i}:")
            for key, value in simplified.items():
                # Limiter la longueur d'affichage pour les champs de contenu
                if key in ['content', 'description'] and isinstance(value, str) and len(value) > 100:
                    print(f"  {key}: {value[:100]}...")
                else:
                    print(f"  {key}: {value}")
        
        return simplified_results
        
    except Exception as e:
        print(f"❌ Erreur lors de l'extraction depuis {source_type}: {str(e)}")
        return []

async def main():
    try:
        # Initialisation
        print("Initialisation des services...")
        await initialiser_base_clients()
        await search_factory.initialize()
        print("✅ Services initialisés\n")
        
        # 1. Extraire les tickets RONDOT de JIRA
        await extract_data_from_source(
            source_type="jira",
            search_query="RONDOT",
            client_info={"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"},
            limit=5
        )
        
        # 2. Extraire les tickets RONDOT de ZENDESK
        await extract_data_from_source(
            source_type="zendesk",
            search_query="RONDOT",
            client_info={"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"},
            limit=5
        )
        
        # 3. Extraire les éléments RONDOT de CONFLUENCE
        await extract_data_from_source(
            source_type="confluence",
            search_query="RONDOT",
            client_info={"source": "RONDOT", "jira": "RONDOT", "zendesk": "RONDOT"},
            limit=3
        )
        
        # 4. Extraire des résultats de NETSUITE
        await extract_data_from_source(
            source_type="netsuite",
            search_query="comment paramétrer le compte fournisseur",
            limit=5
        )
        
        # 5. Extraire des résultats de NETSUITE_DUMMIES
        await extract_data_from_source(
            source_type="netsuite_dummies",
            search_query="comment paramétrer le compte fournisseur",
            limit=5
        )
        
        # 6. Extraire des résultats de SAP
        await extract_data_from_source(
            source_type="sap",
            search_query="comment paramétrer le compte fournisseur",
            limit=5
        )
        
        print("\n" + "="*60)
        print("EXTRACTION TERMINÉE")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Erreur dans le programme principal: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
