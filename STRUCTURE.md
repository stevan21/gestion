# Structure du Projet - Flux Gestion

```
fluxgestion/
│
├── 📄 README.md                    # Documentation principale
├── 📄 QUICKSTART.md                # Guide de démarrage rapide
├── 📄 .gitignore                   # Fichiers à ignorer par Git
├── 📄 docker-compose.yml           # Configuration Docker
│
├── 📁 backend/                     # BACKEND DJANGO
│   ├── manage.py                   # Utilitaire Django
│   ├── requirements.txt            # Dépendances Python
│   ├── .env.example                # Exemple de fichier .env
│   ├── Dockerfile                  # Dockerfile pour le backend
│   │
│   ├── gunicorn_config.py          # Configuration du serveur WSGI
│   ├── conftest.py                 # Amorçage Django pour pytest
│   │
│   ├── 📁 fluxgestion/            # Configuration Django
│   │   ├── __init__.py             # Expose l'application Celery
│   │   ├── settings.py             # Configuration principale
│   │   ├── urls.py                 # Routage des URLs
│   │   ├── celery.py               # Application Celery et planification
│   │   ├── wsgi.py                 # WSGI (production)
│   │   └── asgi.py                 # ASGI (serveurs asynchrones)
│   │
│   ├── 📁 api/                     # Application API
│   │   ├── __init__.py
│   │   ├── models.py               # Member, MonthlyObjective, RoadmapItem,
│   │   │                           # DailyTask, Report, Payslip, StaffEvent,
│   │   │                           # LeaveRequest, Attendance, Suggestion
│   │   ├── managers.py             # QuerySets metier et regle de visibilite
│   │   ├── views.py                # ViewSets et actions
│   │   ├── auth_views.py           # Endpoints d'authentification
│   │   ├── serializers.py          # Serialisation et validation
│   │   ├── auth_serializers.py     # Inscription, connexion, profil
│   │   ├── filters.py              # Filtres exposes en query string
│   │   ├── permissions.py          # Membre / fondateur
│   │   ├── validators.py           # Validateurs metier
│   │   ├── signals.py              # Creation du profil, cache
│   │   ├── tasks.py                # Taches Celery
│   │   ├── urls.py                 # URLs de l'API
│   │   ├── admin.py                # Interface admin
│   │   ├── apps.py                 # Branchement des signaux
│   │   ├── 📁 management/commands/
│   │   │   ├── create_manager.py   # Cree ou promeut un gerant
│   │   │   └── seed_demo.py        # Equipe de demonstration
│   │   ├── tests.py                # Tests unitaires
│   │   └── test_integration.py     # Tests d'integration de l'API
│   │
│   └── 📁 staticfiles/             # Fichiers statiques (généré)
│
├── 📁 frontend/                    # FRONTEND SPA
│   ├── index.html                  # Page principale
│   │
│   ├── 📁 css/
│   │   └── style.css               # Feuille de styles (responsive)
│   │
│   ├── 📁 js/
│   │   ├── app.js                  # Logique principale
│   │   ├── api.js                  # Client API
│   │   ├── chart.js                # Gestion des graphiques
│   │   └── utils.js                # Fonctions utilitaires
│   │
│   └── 📁 assets/                  # Images et ressources
│       └── (à remplir)
│
├── 📁 docs/                        # DOCUMENTATION
│   └── API.md                      # Documentation API complète
│
└── 📁 nginx/                       # Configuration Nginx (optionnel)
    └── nginx.conf                  # Configuration reverse proxy
```

---

## 📊 Description des répertoires

### Backend (Django)

**fluxgestion/**: Configuration centrale Django
- `settings.py`: Configuration de la base de données, apps, middlewares, etc.
- `urls.py`: Routage des URLs globales
- `wsgi.py`/`asgi.py`: Points d'entrée pour les serveurs web
- `celery.py`: Application Celery et planification des tâches périodiques

**api/**: Application principale
- `models.py`: Définit les structures de données (Member, MonthlyObjective,
  RoadmapItem, DailyTask, Report, Payslip, StaffEvent, LeaveRequest,
  Attendance, Suggestion, Reaction)
- `managers.py`: QuerySets métier et règle de visibilité membre / fondateur
- `permissions.py`: Contrôle d'accès par objet
- `views.py`: Endpoints REST API avec les logiques métier
- `serializers.py`: Convertit les modèles en JSON
- `urls.py`: Routes spécifiques de l'API
- `admin.py`: Interface d'administration Django
- `tests.py`: Tests automatisés

### Frontend (Vanilla JS)

**index.html**: 
- Structure HTML complète de l'application
- Modales pour formulaires
- Navigation et sidebars
- Zones pour les graphiques et données

**css/style.css**:
- Design responsive (mobile-first)
- Thème clair/sombre
- Variables CSS
- Animations et transitions
- Breakpoints media queries

**js/**:
- `app.js`: Gestion de l'application, événements, navigation
- `api.js`: Wrapper pour requêtes API REST
- `chart.js`: Intégration Chart.js pour graphiques
- `utils.js`: Utilitaires (formatage, notifications, etc.)

### Documentation

**API.md**: 
- Endpoints détaillés
- Paramètres de requête
- Exemples cURL
- Codes d'erreur

---

## 🔄 Architecture

```
CLIENT (HTML/CSS/JS)
    ↓
FETCH API (http://localhost:8001)
    ↓
NGINX/HTTP Server (Frontend)
    ↓ (Reverse Proxy)
DJANGO Rest API (http://localhost:8000/api)
    ↓
REST Framework Views
    ↓
ORM Django
    ↓
SQLite/PostgreSQL
```

---

## 📝 Modèles de Données

### Member
- Profil métier d'un compte utilisateur
- Rôle : `member`, `founder` ou `manager` — c'est lui qui gouverne la visibilité
- `is_founder` vaut vrai pour un fondateur **et** un gérant : la propriété dit
  « voit toute l'équipe », pas le titre porté. `is_manager` ouvre en plus la
  paie et le suivi du personnel
- Poste, pôle, date d'arrivée
- Créé automatiquement à l'inscription ; le premier compte devient fondateur
- Porte le salaire de base : il se lit sur le profil, sans bulletin de paie
- Porte aussi la journée de référence (`work_starts_at`, `work_ends_at`), qui
  fixe le seuil de retard du pointage, et le droit à congé annuel
  (`leave_entitlement`), dont se déduisent `leave_days_taken` et
  `leave_balance`

### MonthlyObjective
- Objectifs d'un membre pour un mois : CA et clients attendus contre réalisés
- Un seul jeu par membre et par mois (contrainte d'unicité en base)
- Le mois est toujours ramené à son premier jour
- Calcule l'avancement, le compare au temps écoulé et signale le retard
- Les montants sont des `Decimal`, jamais des flottants

### RoadmapItem
- Jalon rattaché à un objectif mensuel
- Titre, échéance, statut, avancement, ordre d'affichage
- Maintient seul la cohérence entre statut, avancement et date d'achèvement

### DailyTask
- Tâche qu'un membre se fixe pour une journée
- Priorité numérique (1 à 4) pour permettre un tri par importance
- Rattachement facultatif à un jalon, relie le quotidien à la feuille de route
- `started_at` et `completed_at` bornent le temps réellement passé ; la durée
  est calculée, jamais stockée, et se compare à l'estimation

### Report
- Bilan de période (journalier, hebdomadaire, mensuel), rapport de mission ou
  compte rendu de réunion
- Bilan, réalisations, difficultés, décisions, prochaines étapes ; objet, lieu
  et participants pour une mission ou une réunion
- Brouillon puis soumission ; verrouillé pour son auteur une fois soumis

### Payslip
- Bulletin de paie d'un membre pour un mois — réservé au gérant
- Salaire de base, heures travaillées, heures supplémentaires, primes,
  retenues, cotisations
- Brut et net calculés, jamais stockés : ils ne peuvent pas diverger
- Reprend les évènements du mois du salarié (retards, observations, mises à
  pied) sans les porter : le suivi du personnel reste leur seule source
- Un seul bulletin par membre et par mois ; pas de brouillon — l'enregistrer,
  c'est l'établir, et il reste corrigeable

### Reaction
- Points accordés ou retirés par la direction, avec leur motif et leur auteur
- Un barème donne les points par défaut, ajustables à la saisie
- Le cumul du mois ouvre une prime ; un solde négatif la ramène à zéro sans
  jamais entamer le salaire

### Suggestion
- Message déposé dans la boîte à suggestions : idée, problème ou question
- Chacun relit les siens, la direction lit toute la boîte
- Figé dès qu'il est lu : l'auteur ne réécrit pas un message déjà relevé
- La réponse et son auteur sont conservés

### StaffEvent
- Mise à pied, observation, retard ou heures supplémentaires — réservé au gérant
- Chaque nature porte sa mesure : jours pour une mise à pied, minutes pour un
  retard, heures pour des heures supplémentaires
- L'auteur de la fiche est conservé : une sanction doit rester imputable

### LeaveRequest
- Demande de congé ou d'absence : congé payé, sans solde, maladie, absence
  exceptionnelle
- Posée par son auteur, tranchée par la direction ; la décision garde son
  auteur et sa date
- La durée se compte en jours ouvrables, bornes comprises, une demi-journée
  valant 0,5 — le calendrier n'existant pas en base, le décompte se fait en
  Python
- Deux demandes en attente ou accordées ne peuvent pas se chevaucher : les
  mêmes jours seraient décomptés deux fois
- Seul le congé payé accordé entame le droit annuel du profil

### Attendance
- Pointage d'une journée : arrivée, départ, temps de présence
- Une seule ligne par membre et par jour (contrainte d'unicité en base)
- Le retard est **dérivé** de l'arrivée, contre l'heure de début du profil et
  dix minutes de tolérance, mais conservé : les synthèses du mois l'agrègent en
  une requête
- La durée se calcule, jamais ne se stocke ; une journée passée restée ouverte
  s'arrête à l'heure de fin prévue, sans quoi un départ oublié compterait la
  nuit entière
- L'équipe pointe par `check_in` / `check_out` ; seule la direction crée ou
  corrige une ligne

## 🔐 Règle de visibilité

Elle traverse toute l'application et se lit dans `managers.py` :

```python
def visible_to(self, member):
    if member is None:
        return self.none()
    if member.is_founder:
        return self.all()
    return self.owned_by(member)
```

Chaque ViewSet construit son queryset à partir de cet appel. Un endpoint qui
interrogerait un modèle directement, sans ce filtrage, exposerait les chiffres
d'un collègue — la suite de tests couvre chaque modèle sur ce point.

## 🔐 Sécurité

- ✅ CORS configuré
- ✅ Authentification par Token
- ✅ CSRF protection (Django)
- ✅ Validation des données (serializers)
- ✅ Permissions par endpoint
- ⚠️ À implémenter: HTTPS, JWT avancé, Rate limiting

---

## 🚀 Déploiement

### Développement
```bash
cd backend && python manage.py runserver
cd frontend && python -m http.server 8001
```

### Production (Docker)
```bash
docker-compose up -d
```

### Production (Manuel)
```bash
gunicorn fluxgestion.wsgi:application --bind 0.0.0.0:8000
# Nginx en reverse proxy
```

---

## 📦 Dépendances Principales

### Backend
- Django 5.0
- Django REST Framework
- django-cors-headers
- Gunicorn
- PostgreSQL (ou SQLite)

### Frontend
- Chart.js (graphiques)
- Font Awesome (icônes)
- Vanilla JavaScript (ES6+)

---

## 🎯 Fonctionnalités Principales

✅ Dashboard avec statistiques
✅ CRUD complet (performances, catégories, alertes)
✅ Graphiques interactifs (Chart.js)
✅ Filtrage et recherche
✅ Thème clair/sombre
✅ Responsive design
✅ API REST complète
✅ Admin Django intégré
✅ Authentification
✅ Export CSV/JSON

---

## 📈 À ajouter

- [ ] Authentication JWT avancée
- [ ] WebSockets pour mises à jour en temps réel
- [ ] Intégration avec sources de données externes
- [ ] Machine Learning pour prédictions
- [ ] Tests automatisés complets
- [ ] Cache Redis
- [ ] Message queue (Celery)
- [ ] Logging structuré
- [ ] Monitoring (Prometheus, Grafana)

---

## 📚 Fichiers clés à connaître

1. **settings.py**: Point central de configuration
2. **models.py**: Structure des données
3. **views.py**: Logique métier
4. **api.js**: Communication avec le backend
5. **app.js**: Orchestration du frontend
6. **style.css**: Design et responsive

---

**Dernière mise à jour:** 2024-08-31
**Version:** 1.0.0
**Auteur:** Flux Gestion Team
