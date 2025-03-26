# Guide d'installation et de configuration

## 1. Préparation de l'environnement

Avant d'installer le système, assurez-vous que vous disposez de :
- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)
- Git (pour cloner le dépôt)

### Variables d'environnement requises

Configurez les variables d'environnement suivantes :

```bash
# API OpenAI pour les embeddings et LLM
export OPENAI_API_KEY=votre_clé_api_openai

# Configuration Qdrant
export QDRANT_URL=votre_url_qdrant
export QDRANT_API_KEY=votre_clé_api_qdrant

# Autres configurations optionnelles
export LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
export CONFIG_PATH=/chemin/vers/config.py  # Optionnel, configuration supplémentaire
```

## 2. Installation

### Cloner le dépôt

```bash
git clone https://github.com/votre-organisation/itshelp_direct.git
cd itshelp_direct
```

### Installer les dépendances

```bash
pip install -r requirements.txt
```

## 3. Configuration des clients de recherche

La nouvelle architecture utilise une structure modulaire. Vous devez configurer chaque client de recherche selon vos besoins :

### Collections Qdrant

Assurez-vous que les collections suivantes existent dans votre instance Qdrant :
- JIRA
- ZENDESK
- CONFLUENCE
- NETSUITE
- NETSUITE_DUMMIES
- SAP
- ERP

Pour créer une collection si elle n'existe pas :

```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

client = QdrantClient(url="votre_url_qdrant", api_key="votre_clé_api_qdrant")

# Créer une collection
client.create_collection(
    collection_name="NOM_COLLECTION",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
)
```

### Configuration des clients

Vous pouvez personnaliser les clients de recherche en modifiant le fichier `search/factory/search_factory.py` :

```python
def _initialize_clients(qdrant_client, embedding_service, translation_service):
    """
    Initialise tous les clients de recherche.
    
    Args:
        qdrant_client: Client Qdrant partagé
        embedding_service: Service d'embedding partagé
        translation_service: Service de traduction partagé
        
    Returns:
        Dictionnaire des clients initialisés
    """
    clients = {}
    
    # Exemple pour personnaliser un client
    try:
        jira_client = JiraSearchClient(
            qdrant_client=qdrant_client,
            embedding_service=embedding_service,
            translation_service=translation_service,
            # Options spécifiques...
        )
        clients["JIRA"] = jira_client
        logger.info("Client JIRA initialisé avec succès")
    except Exception as e:
        logger.error(f"Erreur initialisation client JIRA: {str(e)}")
    
    # Ajoutez d'autres clients selon vos besoins...
    
    return clients
```

## 4. Vérification de l'installation

Pour vérifier que tout est correctement installé et configuré :

```bash
python test_search_clients.py
```

Ce script vérifiera l'initialisation de tous les clients de recherche et exécutera des requêtes de test.

## 5. Dépannage

Si vous rencontrez des problèmes, consultez la section "Dépannage commun" dans [DOCUMENTATION_ARCHITECTURE.md](DOCUMENTATION_ARCHITECTURE.md) et le [GUIDE_TECHNIQUE_CLIENTS_RECHERCHE.md](GUIDE_TECHNIQUE_CLIENTS_RECHERCHE.md).

### Problèmes courants

1. **Erreurs d'API OpenAI** :
   - Vérifiez que votre clé API est valide et correctement configurée
   - Assurez-vous que votre compte a suffisamment de crédits

2. **Problèmes de connexion à Qdrant** :
   - Vérifiez l'URL et la clé API
   - Assurez-vous que Qdrant est accessible depuis votre réseau

3. **Erreurs d'initialisation des clients** :
   - Vérifiez les logs pour identifier le problème spécifique
   - Assurez-vous que les collections Qdrant existent et sont correctement configurées

## 6. Déploiement en production

Pour un déploiement en production, nous recommandons :

1. Utiliser Docker pour containeriser l'application
2. Configurer les variables d'environnement via Docker ou un service de gestion de secrets
3. Mettre en place un monitoring des logs
4. Configurer des alertes en cas d'erreur critique

## 7. Conclusion

Cette nouvelle architecture modulaire facilite l'extension et la personnalisation du système. Pour ajouter de nouvelles sources de données, consultez le [GUIDE_TECHNIQUE_CLIENTS_RECHERCHE.md](GUIDE_TECHNIQUE_CLIENTS_RECHERCHE.md).

Pour toute question ou problème, veuillez contacter l'équipe de support.
