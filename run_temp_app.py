import logging
from app import app, socketio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ITS_HELP')

print('Démarrage du serveur ITS HELP...')
port = 5000
print(f'Port utilisé: {port}')
socketio.run(app, host='0.0.0.0', port=port, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
