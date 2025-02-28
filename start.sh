#!/bin/bash
set -e  # Arrêt en cas d'erreur

# Configuration pour contourner les problèmes de Git LFS
export GIT_LFS_SKIP_SMUDGE=1

# Création du répertoire pour les fichiers volumineux si nécessaire
mkdir -p Lib/site-packages/lance
mkdir -p data  # Assurer que le répertoire data existe

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

# Installation des dépendances (une seule fois)
pip install -r requirements.txt
pip install gunicorn eventlet

# Exécuter une initialisation simplifiée de la base de données
echo "Initialisation de la base de données..."
python - <<EOF
import asyncio
import os
from pathlib import Path

# Assurer l'existence du répertoire data
Path('data').mkdir(exist_ok=True)

async def init_db_standalone():
    try:
        from base_de_donnees import init_db
        await init_db()
        print('Base de données initialisée avec succès')
    except Exception as e:
        print(f"Erreur lors de l'initialisation: {e}")
        import traceback
        traceback.print_exc()

# Exécution de l'initialisation
asyncio.run(init_db_standalone())
EOF

# Démarrer l'application avec Gunicorn
echo "Démarrage de l'application sur le port ${PORT:-5000}..."
# Utiliser --preload pour charger l'application et son contexte avant de créer les workers
gunicorn --worker-class eventlet --preload -w 1 'app:app' -b 0.0.0.0:${PORT:-5000}