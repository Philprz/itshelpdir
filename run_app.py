# -*- coding: utf-8 -*-

import os
import logging
import asyncio
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from dotenv import load_dotenv

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Chargement des variables d'environnement
load_dotenv()

# Initialisation de l'application Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_secret_key')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Liaison avec l'application principale
import app as main_app  # noqa: E402 - Import délibérément placé ici pour éviter les dépendances circulaires
main_app.app = app
main_app.socketio = socketio

# Route principale (page web)
@app.route('/')
def index():
    return render_template('index.html')

# API REST fallback (pour les clients sans Socket.IO)
@app.route('/api/message', methods=['POST'])
def process_message():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({"error": "Message requis"}), 400

        # Version synchrone simplifiée - pas besoin d'utiliser les variables
        return jsonify({
            "message": "Pour utiliser le chatbot complet, veuillez utiliser Socket.IO",
            "blocks": [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Pour utiliser le chatbot complet, veuillez utiliser Socket.IO"}
            }]
        })
    except Exception as e:
        logger.error(f"Erreur API: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Remplacement de before_first_request qui n'est plus disponible dans Flask 2.x
initialized = False

@app.before_request
def initialize_if_needed():
    global initialized
    if not initialized:
        logger.info("Initialisation de l'application...")
        try:
            # Exécution synchrone de l'initialisation dans le context de la requête
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main_app.initialize_app())
            loop.close()
            initialized = True
            logger.info("Initialisation terminée !")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # Continuer malgré l'erreur pour permettre le débogage

# Décorateur pour les évènements Socket.IO
@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connecté: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Client déconnecté: {request.sid}")

@socketio.on('message')
def handle_message(data):
    logger.info(f"Message reçu: {data}")
    # Relai à la fonction de traitement du message dans app.py
    user_id = request.sid
    message = data.get('message', '')
    mode = data.get('mode', 'detail')
    socketio.start_background_task(main_app.process_message, user_id, message, mode)

# Démarrage de l'application
if __name__ == '__main__': 
    port = int(os.getenv('PORT', 5000))
    is_render = os.getenv('RENDER', '0') == '1'
    
    if is_render:
        # Mode production pour RENDER
        logger.info(f"Démarrage du serveur en mode production (RENDER) sur port {port}...")
        app.config['DEBUG'] = False
        socketio.run(app, debug=False, host='0.0.0.0', port=port, 
                    allow_unsafe_werkzeug=False)
    else:
        # Mode développement local
        logger.info(f"Démarrage du serveur en mode développement sur port {port}...")
        socketio.run(app, debug=True, host='0.0.0.0', port=port)
