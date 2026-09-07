#!/bin/bash
# Script de production - Démarrer le serveur avec Gunicorn

set -e

cd backend

# Activer l'environnement virtuel
source venv/bin/activate || . venv/Scripts/activate

# Appliquer les migrations
echo "Applying migrations..."
python manage.py migrate

# Collecter les fichiers statiques
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Démarrer Gunicorn
echo "Starting Gunicorn server..."
gunicorn \
    --config gunicorn_config.py \
    --bind 0.0.0.0:8000 \
    fluxgestion.wsgi:application
