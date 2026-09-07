#!/bin/bash
# Script de test

set -e

echo "======================================"
echo "Exécution des tests"
echo "======================================"

cd backend

# Activer l'environnement virtuel
source venv/bin/activate || . venv/Scripts/activate

# Exécuter les tests
echo "✓ Exécution des tests..."
python manage.py test api

# Exécuter avec couverture
if command -v coverage &> /dev/null; then
    echo "✓ Exécution avec couverture..."
    coverage run --source='.' manage.py test api
    coverage report
    coverage html
    echo "✓ Rapport de couverture généré dans htmlcov/index.html"
fi

echo ""
echo "======================================"
echo "✅ Tests terminés!"
echo "======================================"
