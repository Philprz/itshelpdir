"""
Script de migration - Transition vers la nouvelle architecture

Ce script facilite la migration progressive de l'ancienne architecture (search/)
vers la nouvelle architecture modulaire (src/). Il configure les redirections
et adaptateurs nécessaires pour maintenir la compatibilité pendant la transition.
"""

import asyncio
import logging
import importlib
import sys
import os
from typing import Dict, List, Any, Optional

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ITS_HELP.migration")

async def setup_compatibility_layer():
    """
    Configure la couche de compatibilité entre l'ancienne et la nouvelle architecture
    
    Cette fonction:
    1. Met à jour sys.path pour inclure les nouveaux modules
    2. Configure les redirections d'imports
    3. Initialise les adaptateurs de compatibilité
    """
    logger.info("Configuration de la couche de compatibilité...")
    
    # Compatibilité pour les anciens imports
    try:
        from src.core.compat import search_factory_adapter, get_search_factory
        import search
        
        # Remplacer l'instance globale de search_factory
        search.search_factory = search_factory_adapter
        search.core.factory.search_factory = search_factory_adapter
        
        # Initialiser l'adaptateur
        await search_factory_adapter.initialize()
        
        logger.info("Couche de compatibilité configurée avec succès")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la configuration de la compatibilité: {str(e)}")
        return False

async def validate_migration():
    """
    Valide que la migration fonctionne correctement
    
    Cette fonction effectue des tests de base pour s'assurer que:
    1. Les nouveaux modules sont accessibles
    2. La couche de compatibilité fonctionne
    3. Les fonctionnalités de base sont opérationnelles
    
    Returns:
        Dictionnaire avec les résultats de validation
    """
    results = {
        "modules_access": False,
        "compatibility_layer": False,
        "pipeline_functional": False,
        "legacy_access": False
    }
    
    # Test d'accès aux nouveaux modules
    try:
        from src.core.pipeline import Pipeline
        from src.core.query_engine import QueryEngine
        from src.core.response_builder import ResponseBuilder
        
        results["modules_access"] = True
        logger.info("Accès aux nouveaux modules: OK")
    except Exception as e:
        logger.error(f"Erreur d'accès aux nouveaux modules: {str(e)}")
    
    # Test de la couche de compatibilité
    try:
        from src.core.compat import get_search_factory
        factory = await get_search_factory()
        assert factory is not None
        
        results["compatibility_layer"] = True
        logger.info("Couche de compatibilité: OK")
    except Exception as e:
        logger.error(f"Erreur dans la couche de compatibilité: {str(e)}")
    
    # Test du pipeline
    try:
        from src.core.pipeline import Pipeline, PipelineConfig
        
        config = PipelineConfig()
        pipeline = Pipeline(config)
        await pipeline.initialize()
        
        status = pipeline.get_status()
        assert status["initialized"] == True
        
        results["pipeline_functional"] = True
        logger.info("Pipeline fonctionnel: OK")
    except Exception as e:
        logger.error(f"Erreur dans le pipeline: {str(e)}")
    
    # Test d'accès legacy
    try:
        import search
        from search.core.factory import search_factory
        
        if hasattr(search_factory, 'initialize'):
            await search_factory.initialize()
            
        results["legacy_access"] = True
        logger.info("Accès legacy: OK")
    except Exception as e:
        logger.error(f"Erreur dans l'accès legacy: {str(e)}")
    
    return results

async def main():
    """Fonction principale du script de migration"""
    logger.info("Démarrage du processus de migration...")
    
    # Configuration de la couche de compatibilité
    compat_success = await setup_compatibility_layer()
    
    if not compat_success:
        logger.error("La configuration de la compatibilité a échoué. Migration interrompue.")
        return False
    
    # Validation de la migration
    validation_results = await validate_migration()
    
    # Afficher un résumé de la validation
    print("\n=== Résultats de la validation de migration ===")
    for key, value in validation_results.items():
        status = "✅ OK" if value else "❌ ÉCHEC"
        print(f"{key}: {status}")
    
    # Déterminer le résultat global
    migration_success = all(validation_results.values())
    
    if migration_success:
        print("\n✅ Migration réussie: Le système est prêt à fonctionner avec la nouvelle architecture")
    else:
        print("\n⚠️ Migration partiellement réussie: Certains tests ont échoué, vérifiez les erreurs")
    
    return migration_success

if __name__ == "__main__":
    # Exécuter la fonction principale de manière asynchrone
    import asyncio
    success = asyncio.run(main())
    
    # Code de sortie basé sur le succès
    sys.exit(0 if success else 1)
