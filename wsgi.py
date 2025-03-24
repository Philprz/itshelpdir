#!/usr/bin/env python
# wsgi.py - Point d'entrée pour Gunicorn

"""
Point d'entrée WSGI pour l'application Flask.
IMPORTANT: Le patch gevent (monkey.patch_all) doit être effectué avant tout autre import
pour assurer un fonctionnement correct avec les opérations asynchrones.
"""

# Le patch de gevent DOIT être effectué avant tout autre import
# pylint: disable=wrong-import-position,wrong-import-order
from gevent import monkey
monkey.patch_all()

# Imports standards - après le patch gevent
# Note: Ces imports sont intentionnellement placés ici après le monkey patching
# pour assurer le bon fonctionnement de gevent avec les modules standards
# noqa: E402  # Désactive l'avertissement de linter pour l'import non situé en haut du fichier
import os  # noqa: E402
import sys  # noqa: E402
import logging  # noqa: E402
import traceback  # noqa: E402

# Configuration du logging basique
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('wsgi')
logger.info("Démarrage de l'application via wsgi.py")

# 4. Import de l'application Flask - après configuration de l'environnement
try:
    from app import app as application
    logger.info("Application Flask importée avec succès")
except Exception as e:
    logger.error(f"Erreur lors de l'import de l'application: {str(e)}")
    traceback.print_exc()
    sys.exit(1)

# Point d'entrée pour Gunicorn
if __name__ == "__main__":
    logger.info("Démarrage direct de wsgi.py - Pour développement uniquement")
    # Configuration du serveur de développement
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    
    logger.info(f"Démarrage du serveur sur {host}:{port} (debug={debug})")
    application.run(host=host, port=port, debug=debug)