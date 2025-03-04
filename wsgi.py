# wsgi.py - Point d'entrée pour Gunicorn
import os
import sys
import logging

# Configuration du logging basique
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('wsgi')
logger.info("Démarrage de l'application via wsgi.py")

# Import de l'application Flask
try:
    from app import app as application
    logger.info("Application Flask importée avec succès")
except Exception as e:
    logger.error(f"Erreur lors de l'import de l'application: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Point d'entrée pour Gunicorn
if __name__ == "__main__":
    logger.info("Démarrage direct de wsgi.py - Pour développement uniquement")
    application.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))