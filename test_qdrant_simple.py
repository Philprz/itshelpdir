"""
Test simple de connexion à Qdrant
"""
from qdrant_client import QdrantClient

print("Tentative de connexion à Qdrant...")
qdrant_client = QdrantClient(
    url="https://b361537d-20a3-4a84-b96f-9efb19837c15.us-east4-0.gcp.cloud.qdrant.io:6333", 
    api_key="85uYuWOgTLHtaPGJk8_irQOvctyEXPlME2RLb54n08EHNwTK8-6GsQ",
)

print("Obtention de la liste des collections...")
collections = qdrant_client.get_collections()
print(f"Collections disponibles: {collections}")

# Essayer de lister les collections attendues
expected_collections = [
    "JIRA",
    "ZENDESK",
    "CONFLUENCE",
    "NETSUITE",
    "NETSUITE_DUMMIES",
    "SAP"
]

# Obtenir les noms des collections
collection_names = [coll.name for coll in collections.collections] if hasattr(collections, 'collections') else []

# Vérifier quelles collections attendues sont présentes
print("\nVérification des collections attendues:")
for coll_name in expected_collections:
    if coll_name in collection_names:
        print(f"✅ Collection {coll_name} présente")
    else:
        print(f"❌ Collection {coll_name} manquante")
