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

# Exécuter l'initialisation
async def main():
    await init_db()
    print("Base de données initialisée avec succès!")

if __name__ == "__main__":
    asyncio.run(main())