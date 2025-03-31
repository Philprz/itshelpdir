"""
Script simple pour tester la connexion à Qdrant
"""
import asyncio
import os
import time
import socket
from dotenv import load_dotenv
from qdrant_client import QdrantClient

async def test_connection():
    """Teste la connexion à Qdrant avec les credentials configurés"""
    # Charger les variables d'environnement
    load_dotenv()
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    
    print(f"Test de connexion Qdrant avec l'URL: {qdrant_url}")
    print(f"Clé API: {qdrant_api_key[:5]}...{qdrant_api_key[-5:]}" if qdrant_api_key else "Pas de clé API configurée")
    
    # Extraire le nom d'hôte de l'URL
    hostname = qdrant_url.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    print(f"Tentative de résolution DNS pour l'hôte: {hostname}")
    
    try:
        # Tenter de résoudre l'adresse IP
        ip_address = socket.gethostbyname(hostname)
        print(f"✅ Résolution DNS réussie: {hostname} -> {ip_address}")
    except socket.gaierror:
        print(f"❌ Échec de la résolution DNS pour {hostname}")
        
        # Essayer une URL alternative (cloud.qdrant.io)
        alt_hostname = "cloud.qdrant.io"
        print(f"Tentative avec un nom d'hôte alternatif: {alt_hostname}")
        try:
            alt_ip = socket.gethostbyname(alt_hostname)
            print(f"✅ Le nom d'hôte alternatif {alt_hostname} est accessible: {alt_ip}")
        except socket.gaierror:
            print(f"❌ Le nom d'hôte alternatif {alt_hostname} n'est pas accessible")
    
    try:
        start_time = time.monotonic()
        print("Tentative de connexion à Qdrant...")
        
        # Créer le client Qdrant
        client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=10.0  # Timeout plus long pour être sûr
        )
        
        # Lister les collections
        collections = await asyncio.to_thread(client.get_collections)
        
        latency = time.monotonic() - start_time
        
        collection_count = len(collections.collections) if hasattr(collections, 'collections') else 0
        collection_names = [coll.name for coll in collections.collections] if hasattr(collections, 'collections') else []
        
        # Vérifier les collections attendues
        expected_collections = [
            os.getenv('QDRANT_COLLECTION_JIRA', 'JIRA'),
            os.getenv('QDRANT_COLLECTION_ZENDESK', 'ZENDESK'),
            os.getenv('QDRANT_COLLECTION_CONFLUENCE', 'CONFLUENCE'),
            os.getenv('QDRANT_COLLECTION_NETSUITE', 'NETSUITE'),
            os.getenv('QDRANT_COLLECTION_NETSUITE_DUMMIES', 'NETSUITE_DUMMIES'),
            os.getenv('QDRANT_COLLECTION_SAP', 'SAP')
        ]
        
        # Vérifier les collections manquantes
        missing_collections = []
        for coll_name in expected_collections:
            if coll_name and coll_name not in collection_names:
                missing_collections.append(coll_name)
        
        # Succès si au moins une collection est trouvée
        if collection_count > 0:
            print(f"✅ Connexion Qdrant réussie ({collection_count} collections, latence: {latency:.2f}s)")
            print(f"   Collections trouvées: {', '.join(collection_names)}")
            
            if missing_collections:
                print(f"⚠️ Collections attendues manquantes: {', '.join(missing_collections)}")
            else:
                print("✅ Toutes les collections attendues sont présentes")
                
            return True
        else:
            print("❌ Aucune collection trouvée dans Qdrant")
            return False
            
    except Exception as e:
        print(f"❌ Erreur de connexion Qdrant: {str(e)}")
        print("Détails de l'erreur:", repr(e))
        
        # Tests supplémentaires
        print("\nTests supplémentaires de connectivité:")
        alternate_url = "https://cloud.qdrant.io"
        print(f"Tentative avec une URL générique: {alternate_url}")
        try:
            alt_client = QdrantClient(
                url=alternate_url,
                timeout=5.0
            )
            # Vérifier le client en obtenant des informations de version
            status = alt_client.get_cluster_status()
            print(f"✅ Connexion de base au service Qdrant Cloud réussie (statut: {status.status})")
        except Exception as alt_e:
            print(f"❌ Échec de connexion au service Qdrant Cloud: {str(alt_e)}")
        
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())
