#!/bin/bash
set -e  # Arrêt en cas d'erreur

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
