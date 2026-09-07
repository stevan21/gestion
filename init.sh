#!/bin/bash
# Script d'initialisation du projet

set -e

echo "======================================"
echo "Initialisation de Flux Gestion"
echo "======================================"

# Vérifier Python
echo "✓ Vérification de Python..."
python --version

# Créer l'environnement virtuel
echo "✓ Création de l'environnement virtuel..."
cd backend
python -m venv venv

# Activer l'environnement virtuel
echo "✓ Activation de l'environnement virtuel..."
source venv/bin/activate || . venv/Scripts/activate

# Installer les dépendances
echo "✓ Installation des dépendances..."
pip install -r requirements.txt

# Copier le fichier .env s'il n'existe pas
if [ ! -f .env ]; then
    echo "✓ Copie du fichier .env..."
    cp .env.example .env
fi

# Appliquer les migrations
echo "✓ Application des migrations..."
python manage.py migrate

# Charger les données de test
echo "✓ Chargement des données de test..."
python manage.py loaddata fixtures/categories.json || true

# Créer un superuser
echo "✓ Création d'un superutilisateur..."
python manage.py createsuperuser || true

echo ""
echo "======================================"
echo "✅ Initialisation réussie!"
echo "======================================"
echo ""
echo "Pour démarrer le serveur:"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  python manage.py runserver"
echo ""
echo "Dans un autre terminal, pour le frontend:"
echo "  cd frontend"
echo "  python -m http.server 8001"
echo ""
echo "Accédez à l'application sur http://localhost:8001"
