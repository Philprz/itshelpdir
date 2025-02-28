#!/bin/bash
set -e  # Arrêt en cas d'erreur

# Configuration pour contourner les problèmes de Git LFS
export GIT_LFS_SKIP_SMUDGE=1

# Création du répertoire pour les fichiers volumineux si nécessaire
mkdir -p Lib/site-packages/lance

# URL vers un stockage externe (à remplacer par l'URL réelle)
LANCE_PYD_URL="https://example-storage.com/path/to/lance.pyd"

# Téléchargement du fichier lance.pyd depuis un stockage externe si nécessaire
if [ ! -f "Lib/site-packages/lance/lance.pyd" ]; then
    echo "Téléchargement de lance.pyd..."
    curl -L "$LANCE_PYD_URL" -o "Lib/site-packages/lance/lance.pyd" || echo "AVERTISSEMENT: Impossible de télécharger lance.pyd"
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

# Installation des dépendances
pip install -r requirements.txt
pip install gunicorn eventlet

# Exécuter les migrations de base de données
echo "Initialisation de la base de données..."
python init_database.py

# Exécuter l'initialisation de la base de données en Python via un heredoc
python - <<EOF
# Importer et exécuter l'initialisation asynchrone de la base de données
try:
    from base_de_donnees import init_db  # Importation de la fonction d'initialisation
    import asyncio
    asyncio.run(init_db())  # Exécuter la fonction asynchrone
    print('Base de données initialisée avec succès')
except Exception as e:
    print(f"Erreur lors de l'initialisation: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
EOF

# Démarrer l'application avec Gunicorn
echo "Démarrage de l'application sur le port ${PORT:-5000}..."
gunicorn --worker-class gevent -w 1 app:app -b 0.0.0.0:${PORT:-5000}