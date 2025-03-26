# Script PowerShell pour démarrer l'application sur Windows

# Vérifier si l'environnement virtuel existe
if (Test-Path -Path ".venv") {
    Write-Host "Activation de l'environnement virtuel .venv"
    # Activation de l'environnement virtuel
    .\.venv\Scripts\Activate.ps1
} elseif (Test-Path -Path "venv") {
    Write-Host "Activation de l'environnement virtuel venv"
    .\venv\Scripts\Activate.ps1
} else {
    Write-Host "Aucun environnement virtuel trouvé. Création d'un nouvel environnement .venv"
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
}

# Création du répertoire data
if (-not (Test-Path -Path "data")) {
    New-Item -Path "data" -ItemType Directory
    Write-Host "Répertoire data créé avec succès"
}

# Vérification des dépendances
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python n'est pas disponible. Vérifiez votre installation."
    exit 1
}

# Tester les modules Python de manière plus idiomatique pour PowerShell
$moduleFlask = python -c "try:
    import flask
    print('True')
except ImportError:
    print('False')
"

$moduleGevent = python -c "try:
    import gevent
    print('True')
except ImportError:
    print('False')
"

$moduleGeventWebsocket = python -c "try:
    import geventwebsocket
    print('True')
except ImportError:
    print('False')
"

if ($moduleFlask -ne "True") {
    Write-Host "Installation de Flask et ses dépendances..."
    pip install -r requirements.txt
} elseif ($moduleGevent -ne "True") {
    Write-Host "Installation de gevent..."
    pip install gevent
} elseif ($moduleGeventWebsocket -ne "True") {
    Write-Host "Installation de gevent-websocket..."
    pip install gevent-websocket==0.10.1
}

# Définition des variables d'environnement
$env:FLASK_ENV = "development"
$env:PYTHONPATH = "."
$env:FLASK_APP = "app.py"
$env:GEVENT_SUPPORT = "True"

# Démarrage de l'application avec Gunicorn
Write-Host "Démarrage de l'application sur le port 5000..."
python -m gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --timeout 300 --graceful-timeout 60 --keep-alive 5 --log-level info 'wsgi:application' -b 0.0.0.0:5000
