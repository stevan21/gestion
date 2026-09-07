#!/bin/bash
# Script de déploiement avec Docker Compose

set -e

echo "======================================"
echo "Déploiement de Flux Gestion"
echo "======================================"

# Vérifier Docker
echo "✓ Vérification de Docker..."
if ! command -v docker &> /dev/null; then
    echo "✗ Docker n'est pas installé"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "✗ Docker Compose n'est pas installé"
    exit 1
fi

# Copier les fichiers .env si nécessaire
if [ ! -f backend/.env ]; then
    echo "✓ Copie du fichier .env du backend..."
    cp backend/.env.example backend/.env
fi

# Arrêter les conteneurs en cours
echo "✓ Arrêt des conteneurs existants..."
docker-compose down || true

# Construire les images
echo "✓ Construction des images Docker..."
docker-compose build

# Démarrer les services
echo "✓ Démarrage des services..."
docker-compose up -d

# Attendre que la base de données soit prête
echo "✓ Attente de la base de données..."
sleep 5

# Appliquer les migrations
echo "✓ Application des migrations..."
docker-compose exec -T backend python manage.py migrate

# Charger les données de test
echo "✓ Chargement des données de test..."
docker-compose exec -T backend python manage.py loaddata fixtures/categories.json || true

# Créer un superutilisateur
echo "✓ Création d'un superutilisateur..."
docker-compose exec -T backend python manage.py createsuperuser --noinput \
  --username admin --email admin@example.com || true

echo ""
echo "======================================"
echo "✅ Déploiement réussi!"
echo "======================================"
echo ""
echo "Services:"
echo "  Frontend: http://localhost"
echo "  Backend API: http://localhost/api/"
echo "  Admin: http://localhost/admin/"
echo ""
echo "Logs:"
echo "  docker-compose logs -f"
echo ""
echo "Arrêter:"
echo "  docker-compose down"
