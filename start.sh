#!/bin/bash
set -e  # Arrêt en cas d'erreur

# Configuration pour contourner les problèmes de Git LFS
export GIT_LFS_SKIP_SMUDGE=1

# Création du répertoire pour les fichiers volumineux si nécessaire
mkdir -p Lib/site-packages/lance
# Assurons-nous que les répertoires requis existent avec les permissions correctes
mkdir -p data
chmod 755 data
if [ -n "$DATABASE_URL" ] && [[ "$DATABASE_URL" == sqlite* ]]; then
    # Extraction du chemin de la base de données depuis l'URL
    DB_PATH=$(echo "$DATABASE_URL" | sed -E 's/sqlite.*:\/\///')
    DB_DIR=$(dirname "$DB_PATH")
    # Utilisation explicite de chemins relatifs
    mkdir -p ./data
    chmod 755 ./data
    echo "Répertoire data créé avec succès"
fi

# Activer l'environnement virtuel s'il existe
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Environnement virtuel activé"
elif [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "Environnement virtuel .venv activé"
fi

# Vérifier que Python est disponible
if ! command -v python &> /dev/null; then
    echo "Python n'est pas disponible. Vérifiez votre installation."
    exit 1
fi

# Vérifier si nous sommes en environnement de développement local
# Si oui, installer les dépendances, sinon elles sont déjà installées par Render
if [ -z "$IS_RENDER" ]; then
    # Installation des dépendances seulement en développement local
    echo "Vérification des dépendances essentielles..."
    
    # Vérifier l'installation de Flask
    if ! python -c "import flask" &> /dev/null; then
        echo "Installation de Flask et ses dépendances..."
        pip install -r requirements.txt
    elif ! python -c "import gevent" &> /dev/null; then
        echo "Installation de gevent..."
        pip install gevent
    fi
else
    # Même en environnement Render, vérifier si Flask est installé
    if ! python -c "import flask" &> /dev/null; then
        echo "Installation des dépendances manquantes sur Render..."
        pip install -r requirements.txt
    fi
fi

# Corriger le problème de before_first_request dans app.py
echo "Correction du code pour compatibilité Flask récent..."
sed -i 's/@app.before_first_request/# @app.before_first_request/g' app.py

# Exécuter une initialisation simplifiée de la base de données
# en s'assurant que le module base_de_donnees est bien disponible
echo "Initialisation de la base de données..."
if ! python -c "import base_de_donnees" &> /dev/null; then
    echo "ERREUR: Module base_de_donnees non trouvé. Vérifier l'installation."
    exit 1
fi

python - <<EOF
from pathlib import Path

# Assurer l'existence des répertoires nécessaires
Path('data').mkdir(exist_ok=True)
print('Répertoires vérifiés, l\'initialisation de la base sera effectuée au démarrage')
EOF

# Démarrer l'application avec Gunicorn
echo "Démarrage de l'application sur le port ${PORT:-5000}..."

# Variables d'environnement pour gevent
export GEVENT_SUPPORT=True

# On utilise worker_class=gevent sans --preload pour éviter les problèmes de fork
# Augmenter les timeouts pour l'initialisation
# Définition des variables d'environnement Flask
export FLASK_ENV=production
export PYTHONPATH=.
export FLASK_APP=app.py

# Augmentation du timeout à 300s (5 minutes) pour l'initialisation
gunicorn --worker-class gevent --workers 1 --timeout 300 --graceful-timeout 60 --keep-alive 5 --log-level info 'wsgi:application' -b 0.0.0.0:${PORT:-5000}