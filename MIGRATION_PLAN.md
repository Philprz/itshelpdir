# Plan de Migration - ITS Help Direct

## État Actuel

La refactorisation a progressé avec l'implémentation de :
- ✅ Module cache intelligent (`src/infrastructure/cache.py`)
- ✅ Adaptateurs LLM (`src/adapters/llm/`)
- ✅ Service embedding (`src/adapters/embeddings/`)
- ✅ Adaptateurs vectoriels (`src/adapters/vector_stores/`)
- ✅ Orchestration centrale (`src/core/`)
  - ✅ `pipeline.py` : Orchestration générale du flux de traitement
  - ✅ `query_engine.py` : Analyse et recherche à travers les différentes sources
  - ✅ `response_builder.py` : Construction et formatage des réponses
  - ✅ `compat.py` : Couche de compatibilité avec l'ancienne architecture

## Couche de Compatibilité

Une couche de compatibilité (`src/core/compat.py`) a été mise en place pour assurer la transition sans interruption de service :
- Fournit des adaptateurs mimant l'interface de l'ancienne architecture
- Redirige les appels vers les nouveaux composants
- Permet une migration progressive

## Plan de Suppression des Fichiers Obsolètes

### Phase 1 - Fichiers remplacés directement
Les fichiers suivants sont directement remplacés par les nouveaux modules et peuvent être supprimés après validation :

| Fichier Obsolète | Remplacé Par | Statut |
|------------------|--------------|--------|
| `search/utils/cache.py` | `src/infrastructure/cache.py` | À supprimer |
| `search/utils/embedding_service.py` | `src/adapters/embeddings/` | À supprimer |

### Phase 2 - Fichiers partiellement remplacés
Ces fichiers sont partiellement remplacés et nécessitent une validation des dépendances avant suppression :

| Fichier Partiellement Obsolète | Remplacé Par | Statut |
|--------------------------------|--------------|--------|
| `search/core/factory.py` | `src/core/pipeline.py` + `src/core/compat.py` | À valider |
| `search/core/result_processor.py` | `src/core/response_builder.py` | À valider |

### Phase 3 - Migration des clients spécifiques
Les clients de recherche spécifiques seront migrés progressivement :

| Client | Nouveau Module | Statut |
|--------|---------------|--------|
| `search/clients/jira_client.py` | `src/adapters/vector_stores/qdrant_adapter.py` | En attente |
| `search/clients/zendesk_client.py` | `src/adapters/vector_stores/qdrant_adapter.py` | En attente |
| `search/clients/confluence_client.py` | `src/adapters/vector_stores/qdrant_adapter.py` | En attente |
| `search/clients/netsuite_client.py` | `src/adapters/vector_stores/qdrant_adapter.py` | En attente |
| `search/clients/netsuite_dummies_client.py` | `src/adapters/vector_stores/qdrant_adapter.py` | En attente |
| `search/clients/sap_client.py` | `src/adapters/vector_stores/qdrant_adapter.py` | En attente |
| `search/clients/erp_client.py` | `src/adapters/vector_stores/qdrant_adapter.py` | En attente |

## Procédure de Migration

1. **Validation initiale**
   - Exécuter `python src/migration.py` pour vérifier la compatibilité
   - S'assurer que tous les tests passent

2. **Sauvegarde préventive**
   - Créer un backup complet : `cp -r search/ backup_search_$(date +%Y%m%d%H%M%S)/`

3. **Phase 1 - Suppression des fichiers directement remplacés**
   - Après validation, supprimer les fichiers listés en Phase 1
   - Vérifier que le système reste opérationnel

4. **Phase 2 - Transition des fichiers partiellement remplacés**
   - Mettre à jour les imports dans le code existant pour utiliser les nouveaux modules
   - Tester chaque modification pour s'assurer de la compatibilité
   - Supprimer les fichiers une fois la transition complète

5. **Phase 3 - Migration des clients spécifiques**
   - Migrer progressivement chaque client vers la nouvelle architecture
   - Mettre à jour la documentation pour refléter la nouvelle implémentation

## Métriques de Validation

Pour chaque étape de migration, valider :
- ✅ Tests unitaires : Vérifier que tous les tests passent
- ✅ Tests d'intégration : Vérifier que le système complet fonctionne
- ✅ Métriques de performance : Comparer les performances avant/après
- ✅ Consommation de tokens : Vérifier que l'économie cible est atteinte (-70%)

## Fichiers à conserver temporairement

Ces fichiers doivent être conservés jusqu'à ce que la migration soit complètement validée :
- `search/__init__.py` : Point d'entrée pour la compatibilité
- `search/core/client_base.py` : Classes de base utilisées par plusieurs composants

## Répertoires à créer/compléter

- `src/api/endpoints.py` : À implémenter dans la phase finale
