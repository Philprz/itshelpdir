# init_database.py
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import asyncio
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('init_database')

# Chargement explicite des variables d'environnement
load_dotenv()

# Création du répertoire data si nécessaire
data_dir = Path('data')
data_dir.mkdir(exist_ok=True)

# Définir manuellement les variables manquantes si nécessaire
if not os.getenv('DATABASE_URL'):
    os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///data/database.db'

if not os.getenv('TIMEOUT_MULTIPLIER'):
    os.environ['TIMEOUT_MULTIPLIER'] = '1.0'

# Exécuter l'initialisation de façon indépendante
async def main():
    try:
        # Import conditionnel pour éviter les erreurs d'importation circulaires
        logger.info("Importation des modules nécessaires...")
        try:
            from base_de_donnees import init_db
        except ImportError as e:
            logger.error(f"Erreur d'importation: {str(e)}")
            # Ajout du répertoire courant au path si nécessaire
            sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
            try:
                from base_de_donnees import init_db
                logger.info("Import réussi après ajustement du path")
            except ImportError as e2:
                logger.error(f"Erreur d'importation persistante: {str(e2)}")
                return False
        
        logger.info("Démarrage de l'initialisation de la base de données...")
        await init_db()
        logger.info("Base de données initialisée avec succès!")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Utilisation d'une nouvelle boucle événementielle pour éviter les conflits
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        success = loop.run_until_complete(main())
        loop.close()
        
        if not success:
            logger.error("Échec de l'initialisation de la base de données")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Erreur critique lors de l'initialisation: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)