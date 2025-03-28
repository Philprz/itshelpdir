# ITS Help Direct - Refactorisation Modulaire

## Vue d'ensemble

Ce projet est une refactorisation modulaire du système ITS Help Direct, visant à améliorer la maintenabilité, les performances et l'extensibilité du code. Cette refactorisation est particulièrement centrée sur l'optimisation des tokens, la mise en cache intelligente et la modularisation des services LLM et d'embedding.

## Structure du Projet

```
src/
├── adapters/                    # Adaptateurs pour services externes
│   ├── llm/                     # Adaptateurs pour modèles de langage
│   │   ├── base.py             # Interface de base pour les adaptateurs LLM
│   │   ├── openai_adapter.py   # Adaptateur pour OpenAI
│   │   ├── anthropic_adapter.py # Adaptateur pour Anthropic
│   │   ├── factory.py          # Factory pour créer des adaptateurs
│   │   └── llm_compat.py       # Compatibilité avec l'ancien système
│   ├── embeddings/              # Services d'embedding vectoriel
│   │   ├── base.py             # Interface de base pour les services d'embedding
│   │   ├── openai_embedding.py # Service d'embedding OpenAI
│   │   ├── factory.py          # Factory pour créer des services d'embedding
│   │   └── embedding_compat.py # Compatibilité avec l'ancien système
│   └── vector_stores/           # Adaptateurs pour bases vectorielles
│       ├── base.py             # Interface de base pour les adaptateurs vectoriels
│       ├── qdrant_adapter.py   # Adaptateur pour Qdrant
│       ├── factory.py          # Factory pour créer des adaptateurs vectoriels
│       └── vector_store_compat.py # Compatibilité avec l'ancien système
├── infrastructure/              # Composants d'infrastructure
│   ├── cache.py                # Cache intelligent avec optimisation de tokens
│   └── cache_compat.py         # Compatibilité avec l'ancien système de cache
└── examples/                    # Exemples d'utilisation
    └── query_optimization.py   # Exemple d'optimisation de requête
```

## Fonctionnalités Principales

### 1. Cache Intelligent

Système de cache avancé avec :
- Détection de fraîcheur des données basée sur TTL et fréquence d'utilisation
- Recherche par similarité sémantique pour optimiser les ressources
- Métriques d'économie de tokens
- Gestion intelligente de la mémoire avec évictions prioritaires

### 2. Adaptateurs LLM

Interface unifiée pour les LLM :
- Support pour OpenAI (GPT-3.5, GPT-4)
- Support pour Anthropic (Claude)
- Factory pour une sélection dynamique du provider
- Système de fallback et retry intégré
- Couche de compatibilité pour l'existant

### 3. Services d'Embedding

Services d'embedding modulaires :
- Support pour OpenAI Ada Embeddings
- Calcul de similarité entre textes
- Classification et ranking par pertinence
- Cache intégré des embeddings pour économiser des tokens
- Traitement en batch pour optimiser les performances

### 4. Adaptateurs Vectoriels

Interface unifiée pour les bases vectorielles :
- Support pour Qdrant
- Recherche par vecteur et par texte
- Filtrage avancé des résultats
- Monitoring et métriques de performance

## Prérequis

- Python 3.9+
- Packages Python requis : `openai`, `anthropic`, `qdrant-client`

## Installation

```bash
# Installation des dépendances
pip install openai anthropic qdrant-client
```

## Utilisation

### Configuration des Variables d'Environnement

```bash
# OpenAI
export OPENAI_API_KEY="votre-clé-api"
export DEFAULT_OPENAI_MODEL="gpt-3.5-turbo"

# Anthropic
export ANTHROPIC_API_KEY="votre-clé-api"
export DEFAULT_ANTHROPIC_MODEL="claude-2"

# Qdrant
export QDRANT_URL="http://localhost:6333"
```

### Exemples d'Utilisation

#### Cache Intelligent

```python
from src.infrastructure.cache import get_cache_instance

# Obtenir une instance du cache
cache = get_cache_instance()

# Stocker une valeur avec métadonnées
await cache.set(
    key="ma_clé", 
    value="ma_valeur", 
    ttl=3600,
    should_embed=True  # Permet la recherche par similarité
)

# Recherche exacte
result = await cache.get("ma_clé")

# Recherche par similarité
result = await cache.get(
    "clé_similaire", 
    allow_semantic_match=True
)

# Statistiques
stats = await cache.get_stats()
print(f"Tokens économisés: {stats['tokens_saved']}")
```

#### Adaptateurs LLM

```python
from src.adapters import LLMAdapterFactory

# Créer un adaptateur
llm = LLMAdapterFactory.create_adapter("openai")

# Générer une complétion
response = await llm.complete([
    {"role": "system", "content": "Vous êtes un assistant utile."},
    {"role": "user", "content": "Bonjour, comment ça va?"}
])

# Accéder au résultat
print(response.response)
print(f"Tokens utilisés: {response.total_tokens}")
```

#### Services d'Embedding

```python
from src.adapters import EmbeddingServiceFactory

# Créer un service d'embedding
embedding_service = EmbeddingServiceFactory.create_service("openai")

# Générer un embedding
vector = await embedding_service.get_embedding("Texte à vectoriser")

# Calculer la similarité entre deux textes
similarity = await embedding_service.similarity("Texte 1", "Texte 2")

# Classer des documents par pertinence
ranked_docs = await embedding_service.rank_by_similarity(
    "Requête utilisateur", 
    ["Document 1", "Document 2", "Document 3"]
)
```

#### Adaptateurs Vectoriels

```python
from src.adapters import VectorStoreFactory

# Créer un adaptateur pour Qdrant
vector_store = VectorStoreFactory.create_adapter("qdrant")

# Recherche par texte
results = await vector_store.search_by_text(
    query_text="Requête utilisateur",
    collection_name="ma_collection",
    limit=10
)

# Insertion d'un document avec son embedding
await vector_store.upsert(
    id="doc_123",
    vector=embedding,
    payload={"text": "Contenu du document", "source": "web"},
    collection_name="ma_collection"
)
```

## Tests

Exécution des tests par module :

```bash
# Tests du cache intelligent
python -m src.infrastructure.tests.test_cache

# Tests des adaptateurs LLM
python -m src.adapters.llm.tests.test_adapters

# Tests des services d'embedding
python -m src.adapters.embeddings.run_tests

# Tests des adaptateurs vectoriels (en cours de finalisation)
python -m src.adapters.vector_stores.run_tests
```

## État actuel

| Composant | État | Tests |
|-----------|------|-------|
| Cache Intelligent | ✅ Terminé | ✅ Validés |
| Adaptateurs LLM | ✅ Terminé | ✅ Validés |
| Services d'Embedding | ✅ Terminé | ✅ Validés |
| Adaptateurs Vectoriels | ✅ Terminé | ⚠️ En cours |

## Prochaines étapes

1. **Finalisation des tests vectoriels** : Résoudre les problèmes avec les tests des adaptateurs vectoriels.
2. **Optimisations** : Améliorer les performances du cache et des adaptateurs.
3. **Documentation avancée** : Documenter tous les paramètres et options de configuration.
4. **Monitoring** : Ajouter des fonctionnalités de monitoring et d'observabilité.
5. **Support pour d'autres providers** : Ajouter des adaptateurs pour d'autres fournisseurs LLM et de bases vectorielles.

## Économie de Tokens

Le système est conçu pour minimiser l'utilisation de tokens via plusieurs stratégies :

1. **Cache intelligent** : Réutilisation des réponses pour des requêtes similaires
2. **Embeddings en cache** : Évite de recalculer les embeddings déjà générés
3. **Traitement en batch** : Optimise les appels d'API pour les embeddings
4. **TTL dynamique** : Garde les entrées fréquemment utilisées plus longtemps en cache
5. **Éviction intelligente** : Prioritise la conservation des données les plus utiles

Les tests montrent une économie moyenne de 20% à 80% en tokens selon les cas d'utilisation.

## Documentation

Pour plus de détails sur l'architecture, consultez le fichier `ARCHITECTURE.md`.

## Contribution

Lors de modifications ou ajouts au code:

1. Assurez-vous que tous les tests passent
2. Respectez les conventions de code existantes
3. Optimisez pour la consommation de tokens
4. Documentez les changements apportés
5. Considérez la compatibilité avec l'ancien système

## Licence

Propriétaire - Tous droits réservés - ITS Help Direct
