# Flux Gestion — Suivi de performance d'équipe

Application de pilotage pour une équipe de startup. Chaque membre pose ses
objectifs du mois — chiffre d'affaires et nombre de clients attendus —, détaille
sa feuille de route, planifie ses tâches quotidiennes et rend ses rapports. Les
fondateurs disposent d'une vue d'ensemble de l'équipe.

## 🚀 Fonctionnalités

- **Objectifs mensuels** — CA et clients attendus contre réalisés, avancement
  comparé au temps écoulé, détection automatique du retard
- **Feuille de route** — jalons rattachés à l'objectif du mois, échéances,
  avancement, alerte sur les jalons dépassés
- **Tâches du jour** — planification quotidienne, priorités, report des retards
  en un clic, rattachement facultatif à un jalon, **chronomètre** : on démarre
  et on termine une tâche, la ligne montre l'heure de début, celle de fin et le
  temps passé, comparé à la durée estimée
- **Rapports** — bilans journaliers, hebdomadaires ou mensuels, rapports de
  mission et comptes rendus de réunion ; brouillon puis soumission, verrouillés
  une fois rendus, exportables en PDF
- **Congés et absences** — chacun pose ses dates et son motif, la direction
  accorde ou refuse ; congé payé, sans solde, maladie ou absence
  exceptionnelle. Le décompte porte sur les jours ouvrables, une demi-journée
  comprise, et seul le congé payé entame le droit annuel. Deux demandes ne
  peuvent pas se chevaucher, et une demande tranchée est figée
- **Pointage** — un bouton dans la barre du haut : on pointe son arrivée, puis
  son départ. Le retard se calcule contre l'heure de début du profil, dix
  minutes de tolérance déduites — il ne se saisit jamais à la main. Un départ
  oublié se referme la nuit suivante sur l'heure de fin prévue
- **Présences** (direction) — le mois membre par membre : journées pointées,
  heures, retards, congés et absences sans motif, plus la journée en cours
- **Utilisateurs** (fondateurs) — créer, modifier, désactiver ou supprimer un
  compte, lui attribuer son profil et réinitialiser son mot de passe
- **Panel** (fondateurs) — suivi en direct : qui travaille en ce moment et sur
  quoi, qui n'a rien entamé, qui est en congé, l'heure d'arrivée de chacun, le
  temps pointé du jour, les retards, et les derniers rapports reçus. La page se
  relit toutes les trente secondes tant qu'on la regarde
- **Vue d'équipe** — réservée aux fondateurs : avancement de chacun, cumuls de
  CA et de clients, membres en retard, classés du plus en difficulté au meilleur
- **Export CSV** des objectifs, filtres et visibilité respectés
- **Export PDF** d'un rapport ou d'un bulletin de paie, mis en page comme un
  document officiel
- **Montants en francs CFA**, sans décimale : la devise tient dans la constante
  `CURRENCY` de `frontend/js/utils.js` — `XAF` affiche « FCFA » (zone BEAC),
  `XOF` affiche « F CFA » (zone BCEAO)
- **Paie et personnel** (gérant) — bulletins de paie mensuels avec brut et net
  calculés et heures travaillées, reprenant les mises à pied, observations et
  retards du mois du salarié ; le suivi du personnel les saisit, et les heures
  pointées du mois se reportent d'un clic sur le bulletin
- **Mon profil** — sa fiche depuis la barre du haut : identité, poste, pôle,
  **salaire de base**, points du mois et prime acquise, solde de congés,
  présence du mois, bulletins établis (exportables en PDF) et changement de
  mot de passe
- **Points et réactions** — la direction salue ou rappelle : objectif atteint,
  bravo, entraide, initiative, rappel, manquement. Les points du mois ouvrent
  une prime, que le gérant reporte d'un clic sur le bulletin
- **Boîte à suggestions** — chacun dépose une idée, un problème ou une
  question ; la direction répond et clôt
- **Notifications** — une cloche qui relève les situations à traiter : objectif
  du mois manquant, retard sur le mois, tâches en retard, jalons dépassés,
  arrivée non pointée, journée restée ouverte, suggestions à lire et demandes
  de congé en attente
- **API REST** avec filtres, recherche et pagination
- **Interface** en JavaScript natif, thème clair/sombre, responsive ; bleu pour
  la structure, orange pour l'accent, et une navigation en bleu nuit qui ne se
  confond jamais avec la zone de travail

## 🔐 Rôles et visibilité

| Rôle | Périmètre |
|------|-----------|
| **Membre** | Ses objectifs, sa feuille de route, ses tâches, ses rapports, ses congés et ses pointages |
| **Fondateur** | Toute l'équipe, plus la vue de synthèse, les congés à trancher et les présences |
| **Gérant** | Tout ce que voit un fondateur, plus la paie et le personnel |

Les deux derniers forment les **profils administratifs** ; l'employé est le
profil simple. Le rôle s'attribue depuis la page **Utilisateurs**, réservée aux
fondateurs — un membre ne peut pas se l'attribuer, le sérialiseur ordinaire fige
le champ.

La paie et le suivi disciplinaire ne sont pas ouverts aux fondateurs : ces
données dépassent le pilotage de la performance. Un fondateur qui les demande
reçoit `403`.

Chacun consulte en revanche **ses propres bulletins**, depuis sa fiche de
profil, dès qu'ils sont établis.

Les congés, eux, relèvent du pilotage : un fondateur comme un gérant les
accorde ou les refuse. Le pointage se lit dans les deux sens — chacun voit ses
journées, la direction voit celles de l'équipe — mais **seule la direction
corrige un pointage** : retoucher son heure d'arrivée soi-même viderait le
suivi de son sens.

La règle est appliquée **côté serveur** sur chaque collection : masquer un
bouton ne suffit pas, l'API refuse la donnée. Demander l'identifiant d'un objet
appartenant à un collègue retourne `404`, jamais son contenu.

Le premier compte créé sur une instance devient fondateur. Le rôle de gérant s'attribue depuis l'administration Django.

## 📋 Stack technique

**Backend** — Python 3.11+ (testé jusqu'à 3.14), Django 5.2, Django REST
Framework, django-filter, Celery et Redis (optionnels), SQLite en développement
et PostgreSQL en production.

**Frontend** — HTML5, CSS3 responsive, JavaScript natif (ES2020+), Chart.js.

## 🔧 Installation

```bash
cd backend

python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # ajustez SECRET_KEY si besoin
python manage.py migrate

# Jeu de démonstration : une équipe de 5 personnes sur 6 mois
python manage.py seed_demo --months 6

python manage.py runserver
```

Dans un second terminal :

```bash
cd frontend
python -m http.server 8001
```

Ouvrez `http://localhost:8001/login.html`.

> Servez le frontend par HTTP. Ouvrir `index.html` depuis le disque (`file://`)
> fait échouer les appels : le navigateur refuse l'origine `null`.

Comptes créés par `seed_demo` (mot de passe `demo1234` pour tous) :

| Identifiant | Rôle | Ce qu'il voit |
|-------------|------|---------------|
| `awa` | Fondatrice, CEO | Toute l'équipe |
| `nadia` | Gérante | Toute l'équipe, la paie et le personnel |
| `karim` | Responsable commercial | Ses seules données |
| `lea` | Chargée d'acquisition | Ses seules données |
| `thomas` | Product Manager | Ses seules données |
| `sofia` | Business Developer | Ses seules données |

Sans `seed_demo`, créez simplement un compte depuis la page d'inscription : le
premier devient fondateur.

### Nommer un gérant

Depuis l'interface : **Utilisateurs**, puis le profil « Gérant ». En ligne de
commande, pour amorcer une instance ou dépanner un accès :

```bash
# Nouveau compte : le mot de passe est engendré et affiché une seule fois
python manage.py create_manager gerant --first-name Aline --last-name Kouassi

# Ou avec un mot de passe choisi (il passe les règles de robustesse du projet)
python manage.py create_manager gerant --password 'MotDePasseSolide!42'

# Promouvoir quelqu'un qui a déjà un compte, sans toucher à son mot de passe
python manage.py create_manager karim --promote
```

`--promote` laisse le pôle et le poste en place ; `--department` et
`--job-title` les changent si besoin. L'administration Django reste l'autre
porte d'entrée.

Si le backend n'écoute pas sur le port 8000, ajustez `API_PORT` dans
[frontend/config.js](frontend/config.js), ou passez l'adresse en paramètre à la
première ouverture — `?api=http://127.0.0.1:8765/api` — le navigateur la
retient ensuite. `?api=` seul rend la main au port configuré.

## 📁 Structure

```
fluxgestion/
├── backend/
│   ├── fluxgestion/            # Configuration du projet
│   │   ├── settings.py         # Réglages par variables d'environnement
│   │   ├── celery.py           # Application Celery et planification
│   │   └── wsgi.py / asgi.py
│   ├── api/
│   │   ├── models.py           # Member, MonthlyObjective, RoadmapItem,
│   │   │                       # DailyTask, Report, Payslip, StaffEvent,
│   │   │                       # LeaveRequest, Attendance, Suggestion, Reaction
│   │   ├── managers.py         # QuerySets métier et règle de visibilité
│   │   ├── serializers.py      # Sérialisation et validation
│   │   ├── auth_serializers.py # Inscription, connexion, profil
│   │   ├── views.py            # ViewSets et actions
│   │   ├── auth_views.py       # Endpoints d'authentification
│   │   ├── filters.py          # Filtres exposés en query string
│   │   ├── permissions.py      # Membre / fondateur
│   │   ├── validators.py       # Validateurs métier
│   │   ├── signals.py          # Création du profil, invalidation du cache
│   │   ├── tasks.py            # Tâches Celery
│   │   ├── management/commands/create_manager.py
│   │   ├── management/commands/seed_demo.py
│   │   ├── tests.py            # Tests unitaires
│   │   └── test_integration.py # Tests d'intégration de l'API
│   ├── gunicorn_config.py
│   └── requirements.txt
├── frontend/
│   ├── index.html              # Application
│   ├── login.html              # Connexion et inscription
│   ├── config.js               # Adresse de l'API
│   ├── css/style.css
│   └── js/
│       ├── api.js              # Client API, session, pagination
│       ├── auth.js             # Page de connexion
│       ├── app.js              # Rendu et navigation
│       ├── chart.js            # Graphiques
│       └── utils.js            # Utilitaires et échappement HTML
├── docs/API.md
└── docker-compose.yml
```

## 🔌 Principaux endpoints

| Méthode | Endpoint | Rôle |
|---------|----------|------|
| `POST` | `/api/auth/register/` | Créer un compte |
| `POST` | `/api/auth/login/` | Se connecter |
| `GET` | `/api/members/me/` | Son profil |
| `GET/POST` | `/api/objectives/` | Objectifs mensuels |
| `GET` | `/api/objectives/current/` | Objectifs du mois en cours |
| `PATCH` | `/api/objectives/{id}/close/` | Clôturer un mois |
| `GET` | `/api/objectives/history/` | Évolution mensuelle |
| `GET` | `/api/objectives/export/` | Export CSV |
| `GET/POST` | `/api/roadmap/` | Jalons |
| `GET` | `/api/tasks/today/` | Journée en cours et retards |
| `PATCH` | `/api/tasks/{id}/start/` | Démarrer une tâche |
| `POST` | `/api/tasks/carry_over/` | Reporter les retards |
| `GET/POST` | `/api/reports/` | Rapports |
| `PATCH` | `/api/reports/{id}/submit/` | Soumettre un rapport |
| `GET/POST` | `/api/payslips/` | Bulletins de paie (gérant) |
| `GET` | `/api/payslips/summary/` | Masse salariale du mois |
| `GET/POST` | `/api/staff-events/` | Suivi du personnel (gérant) |
| `GET` | `/api/staff-events/summary/` | Évènements du mois, par nature |
| `GET/POST` | `/api/leaves/` | Demandes de congé |
| `PATCH` | `/api/leaves/{id}/decide/` | Accorder ou refuser (direction) |
| `PATCH` | `/api/leaves/{id}/cancel/` | Annuler une demande |
| `GET` | `/api/leaves/balance/` | Solde de congés de l'année |
| `GET` | `/api/attendance/` | Pointages |
| `GET` | `/api/attendance/today/` | Sa journée et son mois |
| `POST` | `/api/attendance/check_in/` | Pointer l'arrivée |
| `POST` | `/api/attendance/check_out/` | Pointer le départ |
| `GET` | `/api/attendance/summary/` | Présence du mois, membre par membre |
| `GET/POST` | `/api/suggestions/` | Boîte à suggestions |
| `PATCH` | `/api/suggestions/{id}/handle/` | Répondre et clore (direction) |
| `GET` | `/api/dashboard/notifications/` | Alertes du moment |
| `GET` | `/api/dashboard/overview/` | Vue personnelle |
| `GET` | `/api/dashboard/team/` | Vue d'équipe (fondateurs) |
| `GET` | `/api/dashboard/panel/` | Activité en direct (fondateurs) |
| `GET/POST` | `/api/reactions/` | Points accordés ou retirés |
| `GET` | `/api/reactions/scale/` | Barème des réactions |
| `POST` | `/api/members/` | Créer un compte (fondateurs) |
| `PATCH` | `/api/members/{id}/` | Modifier un compte, son rôle compris |
| `PATCH` | `/api/members/{id}/set_active/` | Activer ou désactiver |
| `PATCH` | `/api/members/{id}/reset_password/` | Réinitialiser le mot de passe |
| `DELETE` | `/api/members/{id}/` | Supprimer définitivement |

Référence complète : [docs/API.md](docs/API.md).

## 📐 Comment se calcule l'avancement

Chaque cible réellement fixée donne un pourcentage ; l'avancement global est
leur moyenne. Une cible laissée à zéro est **ignorée** : un profil produit sans
objectif de chiffre d'affaires n'est pas pénalisé.

Ce pourcentage est comparé à la part du mois déjà écoulée. Au-delà de
**15 points de retard**, l'objectif est signalé comme en difficulté. La marge
évite d'alarmer sur un simple décalage de quelques jours, courant en début de
mois. Un mois clôturé n'est jamais signalé.

## 🔄 Tâches asynchrones

Celery gère l'ouverture des objectifs du mois, la clôture du mois précédent, les
alertes de retard, les rappels de rapport, le report des tâches en retard et la
fermeture des pointages laissés ouverts.

| Tâche | Quand |
|-------|-------|
| `close_previous_month` | Le 1er du mois, 0 h 05 |
| `open_monthly_objectives` | Le 1er du mois, 0 h 10 |
| `carry_over_late_tasks` | Chaque jour, 6 h |
| `close_stale_attendance` | Chaque nuit, 3 h |
| `notify_objectives_at_risk` | Du lundi au vendredi, 8 h 30 |
| `remind_missing_reports` | Lundi 9 h (hebdomadaire), le 3 du mois 9 h (mensuel) |
| `cleanup_old_data` | Dimanche, 4 h |

Le calendrier vit dans [backend/fluxgestion/celery.py](backend/fluxgestion/celery.py)
et les heures sont locales (`CELERY_TIMEZONE` suit `TIME_ZONE`).

**Sans broker configuré, aucun worker n'est nécessaire** : les tâches
s'exécutent en local. Pour activer un vrai worker :

```bash
# .env
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_TASK_ALWAYS_EAGER=False
```

```bash
celery -A fluxgestion worker -l info
celery -A fluxgestion beat -l info
```

## 🧪 Tests

```bash
cd backend
python manage.py test api
```

La suite couvre le cycle métier complet et, surtout, le cloisonnement : qu'un
membre ne puisse ni lire, ni exporter, ni modifier les données d'un collègue.

## 🚀 Déploiement

```bash
export SECRET_KEY="votre-cle-secrete"
docker compose up -d
```

Démarre PostgreSQL, Redis, l'API sous Gunicorn, un worker et un planificateur
Celery, le frontend et le reverse proxy. Voir [CONFIG_GUIDE.md](CONFIG_GUIDE.md).

## 🔐 Sécurité

- Authentification par token, révoquée à la déconnexion
- Cloisonnement appliqué côté serveur, pas seulement dans l'interface
- Contenu utilisateur échappé avant tout rendu HTML
- Validation serveur des montants, périodes et avancements
- CORS restreint à une liste d'origines explicite
- HTTPS, HSTS et cookies sécurisés activés dès `DEBUG=False`

## 📄 Licence

MIT — voir [LICENSE](LICENSE).
