#!/bin/bash
# Déploiement par Docker Compose, sur une machine dédiée.
#
# Le proxy de la pile réclame les ports 80 et 443 : pour installer Flux Gestion
# à côté d'applications déjà servies par un nginx du système, voir deploy/.

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

if ! docker compose version &> /dev/null; then
    echo "✗ Docker Compose (plugin v2) n'est pas installé"
    exit 1
fi

# Une machine qui sert déjà un site verrait celui-ci coupé net.
if ss -tln 2>/dev/null | grep -qE ':(80|443) '; then
    echo "✗ Les ports 80 ou 443 sont déjà occupés sur cette machine."
    echo "  Pour déployer à côté d'applications existantes : deploy/README.md"
    exit 1
fi

# La clé n'a pas de valeur par défaut : une clé connue de tous ne signe rien.
if [ -z "${SECRET_KEY:-}" ]; then
    echo "✗ Définissez SECRET_KEY avant de déployer :"
    echo "  export SECRET_KEY=\"\$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')\""
    exit 1
fi

# Copier les fichiers .env si nécessaire
if [ ! -f backend/.env ]; then
    echo "✓ Copie du fichier .env du backend..."
    cp backend/.env.example backend/.env
fi

# Arrêter les conteneurs en cours
echo "✓ Arrêt des conteneurs existants..."
docker compose down || true

# Construire les images
echo "✓ Construction des images Docker..."
docker compose build

# Démarrer les services
echo "✓ Démarrage des services..."
docker compose up -d

# La base annonce elle-même qu'elle est prête (healthcheck du compose).
echo "✓ Attente de la base de données..."
docker compose exec -T db sh -c 'until pg_isready -q; do sleep 1; done'

# Appliquer les migrations
echo "✓ Application des migrations..."
docker compose exec -T backend python manage.py migrate --noinput

# Fichiers statiques de l'administration Django
echo "✓ Collecte des fichiers statiques..."
docker compose exec -T backend python manage.py collectstatic --noinput

# Premier compte : le mot de passe est engendré et affiché une seule fois.
# La commande échoue sans conséquence si le compte existe déjà.
echo "✓ Création du compte de direction..."
docker compose exec -T backend python manage.py create_manager admin || true

echo ""
echo "======================================"
echo "✅ Déploiement réussi!"
echo "======================================"
echo ""
echo "Services:"
echo "  Application: http://localhost"
echo "  API: http://localhost/api/"
echo "  Admin: http://localhost/admin/"
echo ""
echo "Logs:"
echo "  docker compose logs -f"
echo ""
echo "Arrêter:"
echo "  docker compose down"
