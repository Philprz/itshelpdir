"""
Script simple pour tester la connexion à OpenAI
"""
import asyncio
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

async def test_connection():
    """Teste la connexion à OpenAI avec la clé API configurée"""
    # Charger les variables d'environnement
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    print(f"Test de connexion OpenAI avec la clé: {api_key[:10]}...{api_key[-4:]}")
    
    # Créer le client OpenAI
    client = AsyncOpenAI(api_key=api_key)
    
    try:
        # Tester avec un appel simple à l'API
        print("Tentative de connexion à OpenAI...")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Test connection"}],
            max_tokens=5,
            temperature=0
        )
        
        # Vérifier la réponse
        if response and response.choices and len(response.choices) > 0:
            print(f"✅ Connexion OpenAI réussie. Réponse: {response.choices[0].message.content}")
            return True
        else:
            print("❌ Réponse OpenAI vide ou invalide")
            return False
            
    except Exception as e:
        print(f"❌ Erreur de connexion OpenAI: {str(e)}")
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())
