"""
Configuration Gunicorn pour le support WebSocket avec gevent
"""
import multiprocessing

# Bind to this socket
bind = "0.0.0.0:5000"

# Number of workers
workers = multiprocessing.cpu_count() * 2 + 1

# Use the GeventWebSocketWorker worker
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"

# Timeout settings
timeout = 120
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
