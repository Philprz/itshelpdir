import asyncio
import logging
from dotenv import load_dotenv

# Désactiver les logs excessifs
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

# Chargement des variables d'environnement
load_dotenv(verbose=True)
print("\nVariables d'environnement chargées.\n")

# Import après chargement des variables d'environnement
from gestion_clients import extract_client_name, initialiser_base_clients  # noqa: E402
from base_de_donnees import SessionLocal, Client  # noqa: E402

async def test_client_detection():
    """
    Teste la détection des clients dans différents contextes
    """
    print("\n" + "="*80)
    print("INITIALISATION DE LA BASE DE DONNÉES")
    print("="*80 + "\n")
    
    # Initialiser la base de données avec les clients depuis le CSV
    print("Chargement des clients depuis ListeClients.csv...")
    await initialiser_base_clients()
    
    print("\n" + "="*80)
    print("TEST DE DÉTECTION DES CLIENTS")
    print("="*80 + "\n")
    
    # Connexion à la base de données pour obtenir la liste réelle des clients
    async with SessionLocal() as session:
        # Récupérer tous les clients pour vérifier les résultats
        from sqlalchemy import select
        stmt = select(Client)
        result = await session.execute(stmt)
        all_clients = result.scalars().all()
        
        print(f"Base de données contient {len(all_clients)} clients.")
        if all_clients:
            sample_clients = [c.client for c in all_clients[:10]]
            print("Exemples de clients en base: " + ", ".join(sample_clients) + "...\n")
            
            # Génération de phrases de test avec des clients réels
            client_test_phrases = []
            for i, client in enumerate(all_clients):
                if i >= 10:  # Limiter à 10 tests
                    break
                # Générer différentes phrases pour tester la détection
                if i % 3 == 0:
                    client_test_phrases.append(f"Tickets de {client.client} pour 2025.")
                elif i % 3 == 1:
                    client_test_phrases.append(f"Problème avec le client {client.client}")
                else:
                    client_test_phrases.append(f"Je cherche des informations sur {client.client}")
        else:
            print("⚠️ Aucun client n'a été chargé dans la base de données.")
            print("Vérifiez le fichier ListeClients.csv et la fonction d'importation.\n")
            return []
    
    # Phrases de test supplémentaires avec client RONDOT (cas spécifique)
    special_phrases = [
        "Tickets de RONDOT 2025.",
        "Tickets RONDOT de janvier",
        "Problèmes chez RONDOT"
    ]
    
    # Combiner toutes les phrases de test
    test_phrases = client_test_phrases + special_phrases
    
    # Tester chaque phrase
    results = []
    for i, phrase in enumerate(test_phrases, 1):
        print(f"\n{i}. Phrase de test: \"{phrase}\"")
        client_name, score, metadata = await extract_client_name(phrase)
        
        # Vérifier si le client détecté est bien celui mentionné dans la phrase
        expected_client = None
        for client in all_clients:
            if client.client in phrase:
                expected_client = client.client
                break
        
        if client_name:
            print(f"   ✅ Client détecté: {client_name} (score: {score:.1f}%)")
            print(f"   Métadonnées: {metadata}")
            
            # Vérifier si le client détecté correspond à celui attendu
            if expected_client and client_name == expected_client:
                print(f"   ✓ Détection correcte! (attendu: {expected_client})")
                results.append((phrase, client_name, score, True, True))
            elif expected_client:
                print(f"   ✗ Détection incorrecte! (attendu: {expected_client})")
                results.append((phrase, client_name, score, True, False))
            else:
                results.append((phrase, client_name, score, True, None))
        else:
            print(f"   ❌ Aucun client détecté")
            if expected_client:
                print(f"   ✗ Échec de détection! (attendu: {expected_client})")
            results.append((phrase, None, 0, False, False if expected_client else None))
    
    # Résumé des résultats
    print("\n" + "="*80)
    print("RÉSUMÉ DES TESTS")
    print("="*80)
    
    success_count = sum(1 for _, _, _, success, _ in results if success)
    correct_count = sum(1 for _, _, _, _, correct in results if correct is True)
    incorrect_count = sum(1 for _, _, _, _, correct in results if correct is False)
    
    print(f"\n✅ Clients détectés: {success_count}/{len(test_phrases)} ({success_count/len(test_phrases)*100:.1f}%)")
    print(f"✓ Détections correctes: {correct_count}/{len(test_phrases)} ({correct_count/len(test_phrases)*100:.1f}%)")
    
    if incorrect_count > 0:
        print("\nPhrases avec détection incorrecte:")
        for phrase, detected, score, success, correct in results:
            if correct is False:
                print(f"❌ \"{phrase}\" → détecté: {detected or 'Aucun'}")
    
    return results

if __name__ == "__main__":
    try:
        results = asyncio.run(test_client_detection())
        print("\nTest de détection des clients terminé.")
    except Exception as e:
        print(f"\nErreur lors du test: {str(e)}")
