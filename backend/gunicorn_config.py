"""
Configuration Gunicorn pour la production.

Utilisée par run_server.sh, docker-compose et l'unité systemd. Elle vit dans
`backend/` car c'est le répertoire de travail du processus.
"""

import multiprocessing
import os

# Adresse d'écoute
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')

# Nombre de workers : règle usuelle 2 × cœurs + 1, surchargeable.
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
threads = int(os.environ.get('GUNICORN_THREADS', 1))

# Un worker est recyclé régulièrement pour contenir les fuites mémoire.
max_requests = 1000
max_requests_jitter = 100

timeout = 120
graceful_timeout = 30
keepalive = 5

# Journalisation sur la sortie standard : le superviseur (systemd, Docker)
# se charge de la collecte.
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

proc_name = 'fluxgestion'
