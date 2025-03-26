"""
Correctif pour la gestion des résultats Zendesk

Ce script fournit des améliorations pour la validation et le traitement
des résultats de recherche dans Zendesk, cruciale pour les tickets RONDOT.
"""

import logging

# Configuration du logging
logger = logging.getLogger("ITS_HELP.zendesk_fix")

# Fonction améliorée pour la validation des résultats Zendesk
def valider_resultat_zendesk(result):
    """
    Fonction améliorée pour valider un résultat de recherche Zendesk.
    Gère de manière robuste les différentes structures de données possibles.
    
    Args:
        result: Le résultat à valider
        
    Returns:
        bool: True si le résultat est valide, False sinon
    """
    try:
        # Vérifier si le résultat est None
        if result is None:
            logger.warning("Résultat null reçu")
            return False
        
        # Vérifier si le résultat a un attribut payload
        if not hasattr(result, 'payload'):
            logger.warning(f"Résultat sans payload: {type(result)}")
            return False
        
        # Vérifier si le payload est un dictionnaire
        if not isinstance(result.payload, dict):
            logger.warning(f"Payload n'est pas un dictionnaire: {type(result.payload)}")
            return False
        
        # Vérifier si le payload contient des champs essentiels
        essential_fields = ['subject', 'description', 'ticket_id']
        missing_fields = [field for field in essential_fields if field not in result.payload]
        
        if missing_fields:
            logger.warning(f"Champs manquants dans le payload: {missing_fields}")
            # On accepte quand même si au moins un champ essentiel est présent
            return len(missing_fields) < len(essential_fields)
        
        # Vérifier si le ticket est lié à RONDOT
        if 'client' in result.payload:
            client = result.payload['client']
            if isinstance(client, str) and 'RONDOT' in client.upper():
                # Priorité pour les tickets RONDOT
                logger.info(f"Ticket RONDOT trouvé: {result.payload.get('ticket_id', 'Unknown')}")
                return True
        
        return True
        
    except Exception as e:
        logger.error(f"Erreur validation résultat: {str(e)}")
        # En cas d'erreur, on préfère inclure le résultat plutôt que le rejeter
        # pour maximiser les chances de trouver des informations utiles
        return True

# Fonction pour extraire des informations RONDOT d'un résultat
def extraire_info_rondot(result):
    """
    Extrait les informations pertinentes d'un résultat Zendesk pour RONDOT.
    
    Args:
        result: Le résultat à analyser
        
    Returns:
        dict: Informations structurées sur le ticket
    """
    if not hasattr(result, 'payload'):
        return None
    
    try:
        info = {}
        
        # Extraire les champs de base
        for field in ['subject', 'description', 'ticket_id', 'status', 'created_at', 'updated_at', 'url']:
            if field in result.payload:
                info[field] = result.payload[field]
        
        # Ajouter le type
        info['type'] = 'zendesk'
        
        # Ajouter le client explicitement si c'est RONDOT
        if 'client' in result.payload:
            client = result.payload['client']
            if isinstance(client, str) and 'RONDOT' in client.upper():
                info['client'] = 'RONDOT'
                info['priority'] = 'high'  # Priorité élevée pour RONDOT
        
        # Ajouter le score si disponible
        if hasattr(result, 'score'):
            info['score'] = result.score
        
        return info
        
    except Exception as e:
        logger.error(f"Erreur extraction info RONDOT: {str(e)}")
        return None

# Comment intégrer ces fonctions:
"""
Pour intégrer ces fonctions dans qdrant_zendesk.py:

1. Remplacez la fonction `_validate_result` existante par `valider_resultat_zendesk`
2. Ajoutez la fonction `extraire_info_rondot` 
3. Modifiez la méthode de recherche pour utiliser ces fonctions:

```python
async def recherche_intelligente(self, query, limit=5):
    try:
        # Code existant pour obtenir les résultats
        # ...
        
        # Validation et filtrage des résultats
        valid_results = [r for r in results if valider_resultat_zendesk(r)]
        
        # Extraction d'informations spécifiques pour RONDOT si nécessaire
        if 'RONDOT' in query.upper():
            # Ajouter des métadonnées spécifiques à RONDOT
            for result in valid_results:
                rondot_info = extraire_info_rondot(result)
                if rondot_info:
                    # Stocker les informations supplémentaires dans le résultat
                    for key, value in rondot_info.items():
                        if key not in result.payload:
                            result.payload[key] = value
        
        return valid_results
    except Exception as e:
        self.logger.error(f"Erreur recherche_intelligente: {str(e)}")
        return []
```
"""
