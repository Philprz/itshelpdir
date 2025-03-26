"""
Module filter_builder - Utilitaires pour construire des filtres de recherche
"""

import logging
from typing import Optional, Any
from datetime import datetime

# Import des classes Qdrant en veillant à éviter les importations circulaires
# Ces imports sont placés à l'intérieur d'une fonction pour éviter les problèmes 
try:
    from qdrant_client.http.models.models import (
        Filter, 
        FieldCondition, 
        Range, 
        MatchValue
    )
except ImportError:
    logging.warning("Impossible d'importer les modèles Qdrant, les filtres seront limités")

logger = logging.getLogger('ITS_HELP.filter_builder')

def build_qdrant_filter(client_name: Optional[str] = None, 
                      date_debut: Optional[datetime] = None, 
                      date_fin: Optional[datetime] = None) -> Optional[Any]:
    """
    Construit un filtre Qdrant basé sur les paramètres fournis.
    
    Args:
        client_name: Nom du client pour filtrer les résultats (optionnel)
        date_debut: Date de début pour filtrage (optionnel)
        date_fin: Date de fin pour filtrage (optionnel)
    
    Returns:
        Filtre Qdrant configuré ou None si pas de filtre nécessaire
    """
    try:
        # Vérifier que le module Qdrant est disponible
        if 'Filter' not in globals():
            logger.warning("Modèles Qdrant non disponibles pour construire le filtre")
            return None
            
        # Si aucun critère n'est spécifié, retourner None
        if not client_name and not date_debut and not date_fin:
            return None
            
        # Collecter les conditions
        must_conditions = []
        
        # Ajouter la condition de client si spécifiée
        if client_name:
            try:
                # Permettre de filtrer par client avec différentes variations de nom de champ
                client_condition = FieldCondition(
                    key="client",
                    match=MatchValue(value=client_name)
                )
                must_conditions.append(client_condition)
            except Exception as e:
                logger.warning(f"Erreur construction filtre client: {str(e)}")
        
        # Ajouter les conditions de date si spécifiées
        if date_debut or date_fin:
            try:
                date_range = {}
                if date_debut:
                    date_range["gte"] = date_debut.timestamp()
                if date_fin:
                    date_range["lte"] = date_fin.timestamp()
                    
                # Créer une condition pour chaque champ de date possible
                for date_field in ["created", "created_at", "date"]:
                    date_condition = FieldCondition(
                        key=date_field,
                        range=Range(**date_range)
                    )
                    must_conditions.append(date_condition)
            except Exception as e:
                logger.warning(f"Erreur construction filtre date: {str(e)}")
        
        # Si des conditions sont définies, créer le filtre
        if must_conditions:
            return Filter(must=must_conditions)
            
        return None
        
    except Exception as e:
        logger.error(f"Erreur build_qdrant_filter: {str(e)}")
        return None
