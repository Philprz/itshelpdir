# Guide Technique des Clients de Recherche

Ce document fournit des instructions détaillées sur l'utilisation, l'extension et le dépannage des clients de recherche dans la nouvelle architecture.

## Utilisation des clients de recherche

### Recherche dans une source spécifique

```python
from search.factory.search_factory import get_client

# Obtenir un client spécifique
jira_client = get_client("JIRA")

# Exécuter une recherche
results = await jira_client.recherche_intelligente(
    question="Comment configurer une intégration SAP?",
    limit=5
)

# Formater les résultats pour l'affichage
formatted_message = await jira_client.format_for_message(results)
print(formatted_message)
```

### Recherche multi-sources

```python
from search.factory.search_factory import get_clients, search_all_sources

# Rechercher dans toutes les sources disponibles
all_results = await search_all_sources(
    question="Problème de connexion à NetSuite",
    client_name="ACME Corp",
    limit_per_source=3
)

# Ou spécifier des sources précises
sources = ["JIRA", "CONFLUENCE", "ZENDESK"]
specific_results = await search_multiple_sources(
    question="Problème de connexion à NetSuite",
    sources=sources,
    limit_per_source=3
)
```

## Personnalisation et extension

### Créer un nouveau client de recherche

1. Créer un nouveau fichier dans `search/clients/`, par exemple `custom_client.py`
2. Implémenter la classe du client en héritant de `GenericSearchClient`
3. Personnaliser le processeur de résultats si nécessaire

```python
from search.core.client_base import GenericSearchClient
from search.core.result_processor import DefaultResultProcessor

class CustomResultProcessor(DefaultResultProcessor):
    """Processeur personnalisé pour les résultats de la source Custom."""
    
    def extract_title(self, result):
        # Personnalisation de l'extraction du titre
        payload = self.extract_payload(result)
        return payload.get('custom_title_field', 'Sans titre')

class CustomSearchClient(GenericSearchClient):
    """Client de recherche pour la source Custom."""
    
    def __init__(self, collection_name=None, qdrant_client=None, embedding_service=None, translation_service=None):
        if not collection_name:
            collection_name = "CUSTOM"
            
        super().__init__(
            collection_name=collection_name,
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            processor=CustomResultProcessor()
        )
        
    def get_source_name(self):
        return "CUSTOM"
        
    def valider_resultat(self, result):
        if not super().valider_resultat(result):
            return False
            
        # Validation spécifique
        payload = getattr(result, 'payload', {})
        return 'custom_required_field' in payload
```

### Ajouter le nouveau client à la factory

Dans `search/factory/search_factory.py` :

```python
from search.clients.custom_client import CustomSearchClient

# Dans la méthode _initialize_clients
def _initialize_clients():
    # ... autres clients ...
    
    try:
        custom_client = CustomSearchClient(
            qdrant_client=qdrant_client,
            embedding_service=embedding_service
        )
        clients["CUSTOM"] = custom_client
        logger.info("Client CUSTOM initialisé avec succès")
    except Exception as e:
        logger.error(f"Erreur initialisation client CUSTOM: {str(e)}")
```

## Personnalisation du formatage des résultats

Chaque client peut personnaliser l'affichage de ses résultats en implémentant la méthode `format_for_message` :

```python
async def format_for_message(self, results):
    if not results:
        return "Aucun résultat trouvé."
        
    message = "📊 **Résultats Custom:**\n\n"
    
    for i, result in enumerate(results[:5], 1):
        title = self.processor.extract_title(result)
        url = self.processor.extract_url(result)
        
        message += f"{i}. **[{title}]({url})**\n"
        # Personnaliser le formatage selon vos besoins
        
    return message
```

## Performances et optimisation

### Mise en cache des embeddings

Pour éviter de recalculer les embeddings pour les questions fréquentes :

```python
from search.utils.cache import EmbeddingCache

# Dans votre service d'embedding
class EmbeddingService:
    def __init__(self):
        self.cache = EmbeddingCache(max_size=1000)
        
    async def get_embedding(self, text):
        # Vérifier si déjà en cache
        cached = self.cache.get(text)
        if cached:
            return cached
            
        # Sinon, calculer et mettre en cache
        embedding = await self._generate_embedding(text)
        self.cache.put(text, embedding)
        return embedding
```

### Optimisation des requêtes de recherche

Pour les recherches complexes ou fréquentes, utilisez des requêtes optimisées :

```python
async def recherche_optimisee(self, question, filters=None):
    # Préparer la requête une seule fois
    vector = await self.embedding_service.get_embedding(question)
    
    # Exécuter en parallèle si plusieurs collections
    search_tasks = []
    for collection in self.collections:
        task = self._search_collection(collection, vector, filters)
        search_tasks.append(task)
        
    # Attendre tous les résultats
    all_results = await asyncio.gather(*search_tasks)
    
    # Fusionner et dédupliquer
    merged_results = self._merge_results(all_results)
    return merged_results
```

## Dépannage

### Problèmes d'initialisation

Si un client ne s'initialise pas correctement :

1. Vérifiez les variables d'environnement requises
   ```bash
   echo $OPENAI_API_KEY
   echo $QDRANT_URL
   echo $QDRANT_API_KEY
   ```

2. Vérifiez l'accessibilité de Qdrant
   ```python
   from qdrant_client import QdrantClient
   
   client = QdrantClient(url="<votre_url>", api_key="<votre_clé>")
   collections = client.get_collections()
   print(collections)
   ```

3. Vérifiez que la collection existe
   ```python
   try:
       info = client.get_collection("<nom_collection>")
       print(f"Collection OK: {info}")
   except Exception as e:
       print(f"Erreur: {e}")
   ```

### Problèmes de recherche

Si les résultats de recherche sont incorrects ou vides :

1. Vérifiez les embeddings générés
   ```python
   embedding = await embedding_service.get_embedding("votre question test")
   print(f"Taille du vecteur: {len(embedding)}")
   ```

2. Testez une recherche directe dans Qdrant
   ```python
   results = client.search(
       collection_name="<nom_collection>",
       query_vector=embedding,
       limit=10
   )
   print(f"Résultats bruts: {results}")
   ```

3. Vérifiez la validation des résultats
   ```python
   for result in results:
       valid = client.valider_resultat(result)
       print(f"ID: {result.id}, Valide: {valid}")
       if not valid:
           # Analyser pourquoi
           print(f"Payload: {result.payload}")
   ```

## Journalisation

Pour activer le mode debug et voir plus de détails :

```python
import logging

# Dans votre fichier de configuration
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("ITS_HELP").setLevel(logging.DEBUG)
```

## Conseils pour les développeurs

1. **Suivez le modèle architectural** : Respectez la séparation des responsabilités entre client, processeur et services.
2. **Testez vos implémentations** : Créez des tests unitaires pour chaque client dans `tests/`.
3. **Documentez vos classes** : Ajoutez des docstrings détaillés pour faciliter la maintenance.
4. **Gérez correctement les erreurs** : Capturez et loggez les exceptions, fournissez des fallbacks.
5. **Optimisez les performances** : Évitez les opérations coûteuses répétées, utilisez le cache quand approprié.

Pour plus de détails sur l'architecture globale, consultez [DOCUMENTATION_ARCHITECTURE.md](DOCUMENTATION_ARCHITECTURE.md).
