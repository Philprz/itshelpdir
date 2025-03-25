#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fix_source_collections.py
Script pour corriger les problèmes de casse dans les noms de collections ERP et harmoniser
l'utilisation des collections dans le code, notamment NETSUITE, NETSUITE_DUMMIES, et SAP.
"""

import os
import logging
import json
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Configuration du logging avec un format clair
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('ITS_HELP.fix_erp')

# Chargement des variables d'environnement
load_dotenv(verbose=True)

def validate_qdrant_connection():
    """Valide la connexion à Qdrant et récupère les collections disponibles."""
    qdrant_url = os.getenv('QDRANT_URL')
    qdrant_api_key = os.getenv('QDRANT_API_KEY')
    
    if not qdrant_url:
        logger.error("URL Qdrant manquante dans les variables d'environnement")
        return None
    
    try:
        qdrant_client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=30
        )
        
        # Récupérer la liste des collections
        collections_response = qdrant_client.get_collections()
        if not hasattr(collections_response, 'collections'):
            logger.error("Format de réponse inattendu pour get_collections()")
            return None
            
        collections = collections_response.collections
        
        # Vérifier que les collections existent
        collection_names = [col.name for col in collections]
        logger.info(f"Collections trouvées dans Qdrant: {', '.join(collection_names)}")
        
        return qdrant_client, collection_names
        
    except Exception as e:
        logger.error(f"Erreur lors de la connexion à Qdrant: {str(e)}")
        return None

def get_collection_info(qdrant_client, collection_name):
    """Récupère et affiche les informations sur une collection spécifique."""
    try:
        collection_info = qdrant_client.get_collection(collection_name)
        points_count = collection_info.points_count
        
        logger.info(f"Collection: {collection_name}")
        logger.info(f"  - Points: {points_count}")
        
        # Récupérer le schéma des vecteurs
        if hasattr(collection_info, 'config') and hasattr(collection_info.config, 'params'):
            vector_size = collection_info.config.params.vectors.size
            vector_distance = collection_info.config.params.vectors.distance
            logger.info(f"  - Vecteur: taille={vector_size}, distance={vector_distance}")
        
        # Récupérer un échantillon de données si la collection n'est pas vide
        if points_count > 0:
            try:
                # Créer un vecteur aléatoire pour la recherche
                vector = [0.1] * (vector_size if 'vector_size' in locals() else 1536)
                
                # Rechercher les points les plus proches
                point_sample = qdrant_client.query_points(
                    collection_name=collection_name,
                    query_vector=vector,
                    limit=1,
                    with_payload=True
                )
                
                if point_sample:
                    logger.info("  - Exemple de point:")
                    payload = point_sample[0].payload if hasattr(point_sample[0], 'payload') else {}
                    
                    # Afficher les clés du payload
                    if payload:
                        logger.info(f"    - Clés: {', '.join(payload.keys())}")
                        
                        # Afficher le titre ou un champ similaire si disponible
                        for key in ['title', 'name', 'subject', 'heading']:
                            if key in payload:
                                logger.info(f"    - {key}: {payload[key]}")
                                break
            except Exception as e:
                logger.warning(f"  - Impossible de récupérer un échantillon: {str(e)}")
        
        return collection_info
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des infos pour {collection_name}: {str(e)}")
        return None

def check_erp_collections(qdrant_client, collection_names):
    """Vérifie spécifiquement les collections ERP attendues."""
    erp_collections = ['NETSUITE', 'NETSUITE_DUMMIES', 'SAP']
    results = {}
    
    for collection in erp_collections:
        collection_upper = collection.upper()
        collection_lower = collection.lower()
        collection_title = collection.title()
        
        # Vérifier différentes casses possibles
        found_name = None
        if collection_upper in collection_names:
            found_name = collection_upper
        elif collection_lower in collection_names:
            found_name = collection_lower
        elif collection_title in collection_names:
            found_name = collection_title
        
        if found_name:
            logger.info(f"Collection {collection} trouvée comme {found_name}")
            
            # Récupérer les informations détaillées
            info = get_collection_info(qdrant_client, found_name)
            results[collection] = {
                'found_as': found_name,
                'exists': True,
                'info': info
            }
        else:
            logger.warning(f"Collection {collection} introuvable sous aucune casse")
            results[collection] = {
                'exists': False
            }
    
    return results

def write_recommendations(results):
    """Écrit un fichier de recommandations basé sur l'analyse des collections."""
    recommendations = []
    
    # Générer des recommandations spécifiques
    for collection, info in results.items():
        if info.get('exists'):
            found_as = info.get('found_as')
            
            # Si la collection existe mais avec une casse différente
            if found_as != collection:
                recommendations.append(
                    f"La collection {collection} existe sous le nom '{found_as}'. "
                    f"Utilisez TOUJOURS '{found_as}' comme nom de collection dans le code."
                )
            else:
                recommendations.append(
                    f"La collection {collection} existe avec la bonne casse. "
                    f"Continuez à utiliser '{collection}' dans le code."
                )
        else:
            recommendations.append(
                f"La collection {collection} n'existe pas. "
                f"Vérifiez la configuration et créez-la si nécessaire."
            )
    
    # Recommandations générales
    recommendations.append(
        "Assurez-vous que tous les appels à Qdrant utilisent la méthode query_points() "
        "plutôt que search() qui est dépréciée."
    )
    
    recommendations.append(
        "Dans la classe AbstractSearchClient, vérifiez que le nom de collection "
        "est correctement transmis aux méthodes de recherche Qdrant."
    )
    
    # Enregistrer les recommandations dans un fichier
    with open('erp_collections_recommendations.txt', 'w', encoding='utf-8') as f:
        f.write("RECOMMANDATIONS POUR LES COLLECTIONS ERP\n")
        f.write("=======================================\n\n")
        
        for i, rec in enumerate(recommendations, 1):
            f.write(f"{i}. {rec}\n\n")
    
    logger.info(f"Recommandations écrites dans erp_collections_recommendations.txt")

def main():
    """Fonction principale."""
    logger.info("Démarrage de la correction des collections ERP")
    
    # Validation de la connexion Qdrant
    connection_result = validate_qdrant_connection()
    if not connection_result:
        logger.error("Impossible de se connecter à Qdrant. Vérifiez la configuration.")
        return
    
    qdrant_client, collection_names = connection_result
    
    # Vérification des collections ERP
    logger.info("Analyse des collections ERP")
    results = check_erp_collections(qdrant_client, collection_names)
    
    # Générer des recommandations
    write_recommendations(results)
    
    logger.info("Fin de l'analyse des collections ERP")

if __name__ == "__main__":
    main()
