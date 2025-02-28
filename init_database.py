# init_database.py
import os
from dotenv import load_dotenv
import asyncio
from base_de_donnees import init_db

# Chargement explicite des variables d'environnement
load_dotenv()

# Définir manuellement les variables manquantes si nécessaire
if not os.getenv('DATABASE_URL'):
    os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///data/database.db'

if not os.getenv('TIMEOUT_MULTIPLIER'):
    os.environ['TIMEOUT_MULTIPLIER'] = '1.0'

# Création du répertoire data si nécessaire
os.makedirs('data', exist_ok=True)

# Exécuter l'initialisation de façon indépendante
async def main():
    try:
        await init_db()
        print("Base de données initialisée avec succès!")
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la base de données: {e}")
        import traceback
        traceback.print_exc()
        return False
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    if not success:
        exit(1)