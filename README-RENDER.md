# Configuration pour RENDER

Ce document explique comment déployer l'application sur la plateforme RENDER.

## Prérequis

L'application est configurée pour fonctionner avec RENDER en utilisant:
- Gunicorn comme serveur WSGI
- GeventWebSocket pour le support des WebSockets
- Socket.IO pour la communication en temps réel

## Variables d'environnement à configurer

Définissez les variables d'environnement suivantes dans le tableau de bord RENDER:

```
RENDER=1                  # Indique l'exécution dans l'environnement RENDER
SECRET_KEY=votre_clé      # Clé secrète pour Flask
OPENAI_API_KEY=sk-xxx     # Clé API OpenAI
QDRANT_URL=xxx            # URL du service Qdrant
PORT=10000                # Port défini par RENDER (sera automatiquement configuré)
```

## Commande de démarrage

Le fichier `Procfile` définit déjà la commande de démarrage:

```
web: gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --timeout 120 run_app:app
```

## Notes importantes

1. **Workers**: Un seul worker est utilisé pour éviter les problèmes de synchronisation avec Socket.IO
2. **Timeout**: Configuré à 120 secondes pour gérer les requêtes longues
3. **Mode de débogage**: Automatiquement désactivé dans l'environnement RENDER
4. **Erreurs potentielles**: Vérifiez les journaux RENDER en cas de problème
