"""
Script de démarrage pour l'application ITS Help sur Windows
Ce script gère l'initialisation de l'environnement et lance l'application
en s'assurant que toutes les dépendances et configurations sont correctes.
"""
import os
import sys
import logging
import subprocess
import socket
import time
from pathlib import Path
from dotenv import load_dotenv

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('start_windows')

def ensure_directories():
    """Crée les répertoires nécessaires pour l'application"""
    logger.info("Vérification des répertoires nécessaires...")
    Path('data').mkdir(exist_ok=True)
    logger.info("Répertoires vérifiés")

def load_environment():
    """Charge les variables d'environnement depuis le fichier .env"""
    logger.info("Chargement des variables d'environnement...")
    load_dotenv()
    
    # Définition des variables d'environnement nécessaires
    os.environ['FLASK_ENV'] = 'development'
    os.environ['FLASK_DEBUG'] = '1'
    os.environ['PYTHONPATH'] = '.'
    os.environ['FLASK_APP'] = 'app.py'
    
    # Vérifier les variables critiques
    critical_vars = ['OPENAI_API_KEY', 'QDRANT_URL', 'QDRANT_API_KEY']
    missing = [var for var in critical_vars if not os.environ.get(var)]
    
    if missing:
        logger.error(f"Variables d'environnement manquantes: {', '.join(missing)}")
        logger.error("Vérifiez votre fichier .env")
        return False
    
    logger.info("Variables d'environnement chargées avec succès")
    return True

def patch_app_py():
    """Applique les correctifs nécessaires au fichier app.py"""
    logger.info("Application des correctifs à app.py...")
    
    # Vérifier si la fonction initialize_wrapper existe déjà
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Si le wrapper n'existe pas, l'ajouter
    if 'def initialize_wrapper()' not in content:
        logger.info("Ajout de la fonction initialize_wrapper...")
        
        # Trouver l'emplacement d'insertion après la fonction ensure_initialization
        lines = content.split('\n')
        insertion_point = 0
        
        for i, line in enumerate(lines):
            if line.strip() == 'def ensure_initialization():':
                # Trouver la fin de la fonction
                j = i + 1
                while j < len(lines) and (lines[j].startswith(' ') or lines[j].strip() == ''):
                    j += 1
                insertion_point = j
                break
        
        if insertion_point > 0:
            # Insérer le correctif
            wrapper_code = [
                "",
                "def initialize_wrapper():",
                "    \"\"\"Wrapper non-async pour lancer la fonction initialize dans un environnement asynchrone\"\"\"",
                "    loop = asyncio.new_event_loop()",
                "    asyncio.set_event_loop(loop)",
                "    loop.run_until_complete(initialize())",
                "    loop.close()",
                ""
            ]
            
            # Modifier la fonction ensure_initialization pour utiliser le wrapper
            for i, line in enumerate(lines):
                if 'socketio.start_background_task(initialize)' in line:
                    lines[i] = line.replace('initialize)', 'initialize_wrapper)')
            
            # Insérer le code du wrapper
            new_lines = lines[:insertion_point] + wrapper_code + lines[insertion_point:]
            
            # Écrire le fichier modifié
            with open('app.py', 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            logger.info("Correctif appliqué avec succès")
        else:
            logger.error("Impossible de trouver le point d'insertion dans app.py")
            return False
    else:
        logger.info("Le correctif initialize_wrapper existe déjà")
    
    return True

def find_free_port(default_port=5000, max_attempts=10):
    """Trouve un port libre pour l'application"""
    logger.info(f"Recherche d'un port libre (port par défaut: {default_port})...")
    
    # Essayer d'abord le port par défaut
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('0.0.0.0', default_port))
        s.close()
        logger.info(f"Le port par défaut {default_port} est disponible")
        return default_port
    except OSError:
        logger.warning(f"Le port {default_port} est déjà utilisé, recherche d'un port alternatif...")
    finally:
        s.close()
    
    # Chercher un port libre
    for attempt in range(max_attempts):
        port = default_port + attempt + 1
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(('0.0.0.0', port))
            s.close()
            logger.info(f"Port alternatif trouvé: {port}")
            return port
        except OSError:
            logger.debug(f"Port {port} déjà utilisé")
        finally:
            s.close()
    
    logger.error(f"Impossible de trouver un port libre après {max_attempts} tentatives")
    return None

def kill_python_processes():
    """Arrête tous les processus Python en cours d'exécution sauf le processus actuel"""
    logger.info("Tentative d'arrêt des processus Python existants...")
    
    try:
        if os.name == 'nt':  # Windows
            # Obtenir l'ID du processus actuel pour l'exclure
            current_pid = os.getpid()
            logger.info(f"PID actuel (à exclure): {current_pid}")
            
            # Obtenir la liste des processus Python
            tasklist_process = subprocess.run(
                'tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH', 
                shell=True, 
                stdout=subprocess.PIPE, 
                text=True
            )
            
            # Analyser la sortie pour obtenir les PIDs
            for line in tasklist_process.stdout.strip().split('\n'):
                if line:
                    # Format de la ligne CSV: "python.exe","PID",...
                    parts = line.strip('"').split('","')
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])
                            if pid != current_pid:  # Ne pas tuer le processus actuel
                                logger.info(f"Arrêt du processus Python avec PID {pid}")
                                subprocess.run(f'taskkill /F /PID {pid}', shell=True, 
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Erreur lors de l'analyse du PID: {e}")
            
            time.sleep(1)  # Laisser le temps aux processus de se terminer
            logger.info("Processus Python arrêtés")
        else:
            logger.warning("Fonction d'arrêt des processus non implémentée pour ce système")
    except Exception as e:
        logger.warning(f"Erreur lors de l'arrêt des processus Python: {e}")

def start_application():
    """Démarre l'application avec la configuration optimale pour Windows"""
    logger.info("Préparation du démarrage de l'application...")
    
    # Arrêter les processus Python existants
    try:
        kill_python_processes()
    except Exception as e:
        logger.error(f"Erreur lors de l'arrêt des processus Python: {str(e)}")
    
    # Trouver un port libre
    try:
        logger.info("Recherche d'un port disponible...")
        port = find_free_port()
        if not port:
            logger.error("Impossible de démarrer l'application sans port disponible")
            return None
        logger.info(f"Port disponible trouvé: {port}")
    except Exception as e:
        logger.error(f"Erreur lors de la recherche d'un port: {str(e)}")
        return None
    
    # Mettre à jour la variable d'environnement PORT
    try:
        os.environ['PORT'] = str(port)
        logger.info(f"Variable d'environnement PORT définie à {port}")
    except Exception as e:
        logger.error(f"Erreur lors de la définition de PORT: {str(e)}")
        return None
    
    logger.info(f"Démarrage de l'application sur le port {port}...")
    
    # Créer un script Python autonome
    try:
        logger.info("Création d'un script Python temporaire...")
        with open('run_temp_app.py', 'w', encoding='utf-8') as f:
            f.write("""
import os
import logging
from app import app, socketio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ITS_HELP')

print('Démarrage du serveur ITS HELP...')
port = {0}
print(f'Port utilisé: {{port}}')
socketio.run(app, host='0.0.0.0', port=port, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
""".format(port))
    except Exception as e:
        logger.error(f"Erreur lors de la création du script temporaire: {str(e)}")
        return None
    
    # Création du fichier batch pour lancer le script Python
    try:
        with open('run_app_temp.bat', 'w', encoding='utf-8') as f:
            f.write('@echo off\n')
            f.write('echo Demarrage de ITS Help...\n')
            f.write(f'"{sys.executable}" run_temp_app.py\n')
            f.write('pause\n')
    except Exception as e:
        logger.error(f"Erreur lors de la création du fichier batch: {str(e)}")
        return None
    
    # Exécuter le batch en mode détaché
    try:
        logger.info("Démarrage du processus en mode détaché...")
        
        # Exécution du fichier batch en mode détaché
        if os.name == 'nt':  # Windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            process = subprocess.Popen(
                ['cmd', '/c', 'start', 'cmd', '/k', 'run_app_temp.bat'], 
                shell=True,
                startupinfo=startupinfo
            )
            logger.info("Processus de la commande 'start' démarré")
        else:
            logger.error("Cette méthode de démarrage n'est pas implémentée pour ce système d'exploitation")
            return None
    except Exception as e:
        logger.error(f"Erreur lors du démarrage du processus: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None
    
    logger.info("Application démarrée en mode détaché")
    logger.info(f"Vous pouvez accéder à l'application sur http://localhost:{port}")
    logger.info("Vous pouvez fermer cette fenêtre. L'application continuera à s'exécuter dans une autre fenêtre.")
    
    # Attendre un peu pour permettre à l'application de démarrer
    time.sleep(2)
    
    return process

def main():
    """Fonction principale"""
    print("=== Démarrage de ITS Help sur Windows ===")
    
    try:
        ensure_directories()
        
        if not load_environment():
            print("Erreur lors du chargement des variables d'environnement. Arrêt.")
            return 1
        
        if not patch_app_py():
            print("Erreur lors de l'application des correctifs. Arrêt.")
            return 1
        
        try:
            logger.info("Appel de start_application()...")
            process = start_application()
            if not process:
                print("Erreur lors du démarrage de l'application. Arrêt.")
                return 1
        except Exception as e:
            logger.error(f"Exception lors du démarrage de l'application: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"Exception lors du démarrage de l'application: {str(e)}")
            return 1
        
        return 0
    except Exception as e:
        logger.error(f"Exception dans la fonction principale: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"Exception dans la fonction principale: {str(e)}")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Exception non capturée: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"Exception non capturée: {str(e)}")
        sys.exit(1)
