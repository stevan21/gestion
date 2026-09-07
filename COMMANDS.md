# 📋 Commandes Essentielles

## Configuration initiale

```bash
# Cloner le projet (après initialisation Git)
git clone <url-repo>
cd fluxgestion

# Backend
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
cp .env.example .env

# Migrations
python manage.py migrate
python manage.py createsuperuser

# Démarrer le serveur
python manage.py runserver

# Frontend
cd ../frontend
python -m http.server 8001
```

## Développement

### Serveurs de développement
```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
python manage.py runserver

# Terminal 2: Frontend
cd frontend
python -m http.server 8001

# Terminal 3: (optionnel) Watcher pour fichiers statiques
python manage.py collectstatic --watch
```

### Gestion de la base de données
```bash
# Créer les migrations après modification des modèles
python manage.py makemigrations

# Appliquer les migrations
python manage.py migrate

# Réinitialiser complètement
python manage.py flush  # ⚠️ Supprime toutes les données

# Affichez les migrations appliquées
python manage.py showmigrations
```

### Shell Django
```bash
python manage.py shell
```

```python
from django.contrib.auth.models import User
from api.models import Member, MonthlyObjective, DailyTask, Report
from api.managers import month_start
from decimal import Decimal

# Promouvoir un membre au rang de fondateur
member = Member.objects.get(user__username='karim')
member.role = 'founder'
member.save()

# Poser les objectifs du mois pour un membre
MonthlyObjective.objects.create(
    member=member,
    month=month_start(),
    revenue_target=Decimal('25000'),
    clients_target=12,
    focus='Ouvrir le segment PME',
)

# Qui est en retard sur le mois en cours ?
for objectif in MonthlyObjective.objects.current_month().with_related():
    if objectif.is_at_risk:
        print(objectif.member.display_name, objectif.completion, '%')

# Taches non terminees dont le jour est passe
print(DailyTask.objects.late().count())

# Rapports non soumis
print(Report.objects.drafts().count())
```


### Tests
```bash
# Exécuter tous les tests
python manage.py test

# Exécuter les tests d'une app
python manage.py test api

# Exécuter un test spécifique
python manage.py test api.tests.MonthlyObjectiveModelTest

# Avec couverture
pip install coverage
coverage run --source='.' manage.py test
coverage report
coverage html  # Génère un rapport HTML
```

### Collecte des fichiers statiques
```bash
# En développement (généralement automatique)
python manage.py collectstatic --noinput

# Nettoyer les anciens fichiers
python manage.py collectstatic --clear --noinput
```

## Production

### Avec Gunicorn
```bash
pip install gunicorn
gunicorn fluxgestion.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### Avec Docker
```bash
# Construire l'image
docker build -t fluxgestion-backend ./backend

# Lancer le conteneur
docker run -p 8000:8000 fluxgestion-backend

# Ou avec docker-compose
docker-compose up -d
docker-compose down
```

### Nginx (reverse proxy)
```bash
# Tester la config
sudo nginx -t

# Recharger
sudo systemctl reload nginx

# Redémarrer
sudo systemctl restart nginx

# Logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

## Gestion du code

### Avec Git
```bash
# Initialiser Git
git init

# Ajouter tous les fichiers
git add .

# Commit initial
git commit -m "Initial commit: Flux Gestion v1.0"

# Créer une branche de feature
git checkout -b feature/new-feature

# Fusionner
git checkout main
git merge feature/new-feature

# Voir l'historique
git log --oneline
```

### Qualité du code
```bash
# Linting
pip install flake8
flake8 .

# Formatage
pip install black
black .

# Vérification de sécurité
pip install bandit
bandit -r .

# Complexité
pip install radon
radon cc api/ -a
radon mi api/
```

## Dépannage

### Problèmes courants
```bash
# Erreur de migration
python manage.py migrate --fake-initial

# Port en utilisation
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# macOS/Linux
lsof -i :8000
kill -9 <PID>

# Effacer le cache
rm -rf __pycache__
find . -type d -name __pycache__ -exec rm -rf {} +

# Réinstaller les dépendances
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### Logs
```bash
# Voir les logs Django
tail -f backend.log

# Logs du serveur HTTP
tail -f /var/log/apache2/access.log
tail -f /var/log/nginx/error.log

# Logs système
journalctl -u gunicorn -n 50
```

## API Testing

### Avec curl
```bash
# Recuperer un token
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"karim","password":"demo1234"}'

# Creer un compte
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com",
       "job_title":"Business Developer","department":"commercial",
       "password":"MotDePasse-Solide1","password_confirm":"MotDePasse-Solide1"}'

# Poser ses objectifs du mois
curl -X POST http://localhost:8000/api/objectives/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"month":"2026-09-01","revenue_target":"25000","clients_target":12,
       "focus":"Ouvrir le segment PME"}'

# Mettre a jour le realise
curl -X PATCH http://localhost:8000/api/objectives/1/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"revenue_achieved":"12000","clients_achieved":5}'

# Ajouter un jalon
curl -X POST http://localhost:8000/api/roadmap/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"objective":1,"title":"Tenir 20 rendez-vous","due_date":"2026-09-20"}'

# Ajouter une tache du jour
curl -X POST http://localhost:8000/api/tasks/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Relancer 10 prospects","priority":3}'

# Journee en cours
curl -H "Authorization: Token YOUR_TOKEN" \
  http://localhost:8000/api/tasks/today/

# Reporter les taches en retard
curl -X POST http://localhost:8000/api/tasks/carry_over/ \
  -H "Authorization: Token YOUR_TOKEN"

# Soumettre un rapport
curl -X PATCH http://localhost:8000/api/reports/1/submit/ \
  -H "Authorization: Token YOUR_TOKEN"

# Export CSV des objectifs
curl -H "Authorization: Token YOUR_TOKEN" \
  -o objectifs.csv \
  "http://localhost:8000/api/objectives/export/?status=active"

# Synthese d'equipe (fondateur uniquement)
curl -H "Authorization: Token YOUR_TOKEN" \
  "http://localhost:8000/api/dashboard/team/?month=2026-09"

# Revoquer le token
curl -X POST http://localhost:8000/api/auth/logout/ \
  -H "Authorization: Token YOUR_TOKEN"
```

### Avec Postman
1. Creer une collection
2. Variable `base_url` = `http://localhost:8000`
3. Variable `token` alimentee par la reponse de `/api/auth/login/`
4. Importer les endpoints depuis `docs/API.md`


## Performance & Optimisation

### Database
```bash
# Analyser les requetes
pip install django-debug-toolbar

# Compter les requetes d'un endpoint depuis le shell
python manage.py shell
```

```python
from django.db import connection, reset_queries
from api.models import MonthlyObjective

reset_queries()
list(MonthlyObjective.objects.with_related())   # prefetch en place
print(len(connection.queries), 'requetes')
```

### Cache
```bash
# Redis
pip install django-redis

# Configuration dans settings.py:
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
    }
}

# Utilisation
from django.views.decorators.cache import cache_page

@cache_page(60 * 5)  # Cache 5 minutes
def view(request):
    pass
```

## Maintenance

### Backups
```bash
# Exporter la base de données
python manage.py dumpdata > backup.json

# Importer
python manage.py loaddata backup.json

# PostgreSQL
pg_dump fluxgestion_db > backup.sql
psql fluxgestion_db < backup.sql
```

### Monitoring
```bash
# Voir les processus
ps aux | grep python

# Voir l'usage memoire du serveur
top

# Voir les connexions DB
python manage.py dbshell
\dt  # PostgreSQL: voir les tables
```

## Déploiement

### Checklist pré-déploiement
```bash
# [ ] Vérifier les tests
python manage.py test

# [ ] Linter le code
flake8 .

# [ ] Vérifier la sécurité
python manage.py check --deploy

# [ ] Activer DEBUG = False
# [ ] Changer SECRET_KEY
# [ ] Configurer ALLOWED_HOSTS
# [ ] Mettre à jour les variables d'env

# [ ] Exécuter les migrations
python manage.py migrate

# [ ] Collecter les fichiers statiques
python manage.py collectstatic --noinput

# [ ] Vérifier les permissions
chmod 755 /path/to/project

# [ ] Recharger Gunicorn
sudo systemctl restart gunicorn
```

## Raccourcis utiles

```bash
# Alias utiles à ajouter dans .bashrc ou .zshrc
alias djrun='python manage.py runserver'
alias djshell='python manage.py shell'
alias djmigrate='python manage.py migrate'
alias djmake='python manage.py makemigrations'
alias djtest='python manage.py test'
alias djstatic='python manage.py collectstatic --noinput'
```

---

**Note**: Remplacez les chemins et ports selon votre configuration locale.
