#!/bin/bash
set -e  # Arrêt en cas d'erreur

# Activer l'environnement virtuel s'il existe
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Environnement virtuel activé"
fi

# Vérifier que Python est disponible
if ! command -v python &> /dev/null; then
    echo "Python n'est pas disponible. Vérifiez votre installation."
    exit 1
fi

# Exécuter les migrations de base de données
echo "Initialisation de la base de données..."
python -c "from base_de_donnees import init_db; import asyncio; asyncio.run(init_db())"

# Vérifier que Gunicorn est disponible
if ! command -v gunicorn &> /dev/null; then
    echo "Gunicorn n'est pas disponible. Installation..."
    pip install gunicorn
fi

# Démarrer l'application avec Gunicorn
echo "Démarrage de l'application sur le port ${PORT:-5000}..."
gunicorn --worker-class eventlet -w 1 app:app -b 0.0.0.0:${PORT:-5000}