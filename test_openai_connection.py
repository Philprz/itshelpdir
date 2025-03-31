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

async def test_embedding():
    """Teste la fonctionnalité d'embedding d'OpenAI avec le modèle text-embedding-ada-002"""
    # Charger les variables d'environnement
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    print(f"\nTest d'embedding OpenAI avec la clé: {api_key[:10]}...{api_key[-4:]}")
    
    # Créer le client OpenAI
    client = AsyncOpenAI(api_key=api_key)
    
    try:
        # Tester avec un appel à l'API d'embedding
        print("Tentative de génération d'embedding avec text-embedding-ada-002...")
        response = await client.embeddings.create(
            model="text-embedding-ada-002",
            input="Test embedding"
        )
        
        # Vérifier la réponse
        if response and response.data and len(response.data) > 0:
            embedding = response.data[0].embedding
            embedding_dim = len(embedding)
            print(f"✅ Embedding généré avec succès. Dimension: {embedding_dim}")
            print(f"   Premiers éléments: {embedding[:3]}...")
            return True
        else:
            print("❌ Réponse d'embedding vide ou invalide")
            return False
            
    except Exception as e:
        print(f"❌ Erreur lors de la génération d'embedding: {str(e)}")
        return False

async def run_tests():
    """Exécute tous les tests de connexion OpenAI"""
    completion_test = await test_connection()
    embedding_test = await test_embedding()
    
    if completion_test and embedding_test:
        print("\n✅ Tous les tests de connexion OpenAI ont réussi!")
    else:
        print("\n❌ Certains tests de connexion OpenAI ont échoué.")

if __name__ == "__main__":
    asyncio.run(run_tests())
