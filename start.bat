@echo off
echo Démarrage simplifié de l'application ITS_HELP sur Windows...

REM Création des répertoires nécessaires
if not exist data mkdir data
echo Répertoire data vérifié

REM Création d'un script Python temporaire pour charger les variables d'environnement
echo import os > temp_env_loader.py
echo from dotenv import load_dotenv >> temp_env_loader.py
echo load_dotenv() >> temp_env_loader.py
echo with open('env_vars.bat', 'w') as f: >> temp_env_loader.py
echo     for key, value in os.environ.items(): >> temp_env_loader.py
echo         if key in ['OPENAI_API_KEY', 'QDRANT_URL', 'QDRANT_API_KEY', 'PORT', 'SECRET_KEY', 'LOG_LEVEL', 'ENVIRONMENT', 'DATABASE_URL', 'TIMEOUT_MULTIPLIER', 'QDRANT_COLLECTION_JIRA', 'QDRANT_COLLECTION_ZENDESK', 'QDRANT_COLLECTION_CONFLUENCE', 'QDRANT_COLLECTION_NETSUITE', 'QDRANT_COLLECTION_NETSUITE_DUMMIES', 'QDRANT_COLLECTION_SAP']: >> temp_env_loader.py
echo             f.write(f"set {key}={value}\n") >> temp_env_loader.py

REM Exécution du script pour générer le fichier de variables d'environnement
python temp_env_loader.py

REM Charger les variables d'environnement
call env_vars.bat

REM Ajouter manuellement les variables Flask
set FLASK_ENV=development
set FLASK_DEBUG=1
set PYTHONPATH=.
set FLASK_APP=app.py
set LOG_LEVEL=DEBUG

echo Variables d'environnement chargées

REM Nettoyage des fichiers temporaires
del temp_env_loader.py
del env_vars.bat

REM Création directe d'un fichier Python de test sans passer par echo
type NUL > run_app.py
echo # -*- coding: utf-8 -*- > run_app.py
echo import os >> run_app.py
echo import logging >> run_app.py
echo from flask import Flask, render_template, request, jsonify >> run_app.py
echo from dotenv import load_dotenv >> run_app.py
echo. >> run_app.py
echo logging.basicConfig(level=logging.DEBUG) >> run_app.py
echo load_dotenv() >> run_app.py
echo. >> run_app.py
echo app = Flask(__name__) >> run_app.py
echo. >> run_app.py
echo @app.route('/') >> run_app.py
echo def index(): >> run_app.py
echo     return render_template('index.html') >> run_app.py
echo. >> run_app.py
echo @app.route('/api/message', methods=['POST']) >> run_app.py
echo def process_message(): >> run_app.py
echo     data = request.json >> run_app.py
echo     return jsonify({"message": "Ceci est une version de test simplifiee. L'application complete necessite Socket.IO.", "blocks": []}) >> run_app.py
echo. >> run_app.py
echo if __name__ == '__main__': >> run_app.py
echo     app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000))) >> run_app.py

REM Démarrage de l'application Flask simplifiée
echo Démarrage de l'application simplifiée sur le port %PORT% (par défaut: 5000)
python run_app.py

echo Pour arrêter l'application, appuyez sur Ctrl+C
