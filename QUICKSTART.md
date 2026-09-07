# 🚀 Guide de démarrage rapide

Flux Gestion suit la performance d'une équipe de startup : chaque membre pose
ses objectifs du mois, détaille sa feuille de route, planifie ses tâches et
rend ses rapports.

## Prérequis

- Python 3.11 ou supérieur
- Un navigateur moderne

---

## ⚙️ Backend

### 1. Environnement virtuel

**Windows :**
```bash
cd backend
python -m venv venv
venv\Scripts\activate
```

**macOS / Linux :**
```bash
cd backend
python -m venv venv
source venv/bin/activate
```

### 2. Dépendances
```bash
pip install -r requirements.txt
```

### 3. Configuration
```bash
cp .env.example .env
```
Ajustez `SECRET_KEY` si vous dépassez le cadre du développement local.

### 4. Base de données
```bash
python manage.py migrate
```

### 5. Jeu de démonstration (recommandé)
```bash
python manage.py seed_demo --months 6
```

Crée une équipe de cinq personnes avec six mois d'objectifs, une feuille de
route, trois semaines de tâches et des rapports.

| Option | Effet |
|--------|-------|
| `--months 12` | Profondeur d'historique |
| `--task-days 30` | Profondeur des tâches quotidiennes |
| `--reset` | Vide les données métier avant de peupler (les comptes restent) |

### 6. Serveur
```bash
python manage.py runserver
```

- API : http://127.0.0.1:8000/api/
- Administration : http://127.0.0.1:8000/admin/

Pour accéder à l'administration, créez un compte d'administration :
```bash
python manage.py createsuperuser
```
Un superutilisateur reçoit automatiquement le rôle fondateur.

---

## 🎨 Frontend

```bash
cd frontend
python -m http.server 8001
```

Ouvrez **http://localhost:8001/login.html**.

> Servez toujours le frontend par HTTP. Ouvrir `index.html` depuis le disque
> (`file://`) fait échouer les appels API : le navigateur refuse l'origine
> `null`.

Si le backend n'écoute pas sur le port 8000, modifiez `API_PORT` dans
`frontend/config.js` — ou, sans rien modifier, ouvrez la page une fois avec
l'adresse en paramètre :

```
http://localhost:8001/login.html?api=http://127.0.0.1:8765/api
```

Elle est retenue pour les visites suivantes ; `?api=` seul revient au port
configuré. Pratique quand le port 8000 sert déjà à un autre projet : sans cela
l'application semble muette alors qu'elle interroge simplement le voisin.

---

## 🔑 Comptes de démonstration

Mot de passe commun : `demo1234`

| Identifiant | Rôle | Ce qu'il voit |
|-------------|------|---------------|
| `awa` | Fondatrice, CEO | Toute l'équipe et la vue de synthèse |
| `karim` | Responsable commercial | Ses seules données |
| `lea` | Chargée d'acquisition | Ses seules données |
| `thomas` | Product Manager | Ses seules données |
| `sofia` | Business Developer | Ses seules données |
| `nadia` | Gérante | Toute l'équipe, la paie et le personnel |

Connectez-vous avec `awa` puis avec `karim` : l'entrée de menu **Équipe**
disparaît, et la liste des objectifs se réduit aux siens. Le cloisonnement est
appliqué côté serveur, pas seulement dans l'interface.

Sans `seed_demo`, créez un compte depuis la page d'inscription : **le premier
compte d'une instance devient fondateur**.

Pour un gérant — qui voit en plus les bulletins de paie et le suivi du
personnel :

```bash
python manage.py create_manager gerant
```

Le mot de passe est engendré et affiché une seule fois ; `--promote` passe
gérant un compte qui existe déjà.

---

## 📱 Prise en main

1. **Tableau de bord** — votre mois en cours, vos tâches du jour, l'évolution
   de votre chiffre d'affaires
2. **Objectifs** — définissez le CA et le nombre de clients visés pour le mois,
   mettez le réalisé à jour au fil de l'eau, clôturez le mois terminé
3. **Feuille de route** — découpez l'objectif en jalons datés
4. **Tâches du jour** — planifiez votre journée, reportez les retards en un clic
5. **Rapports** — rédigez un bilan de période, soumettez-le quand il est prêt
6. **Équipe** — pour un fondateur : qui décroche, qui n'a pas défini son mois

### Comment se lit l'avancement

La barre de progression porte un repère : la part du mois déjà écoulée. Si la
barre est nettement en retard sur le repère, l'objectif est signalé comme en
difficulté (au-delà de 15 points d'écart).

Une cible laissée à zéro est ignorée dans le calcul : un profil produit sans
objectif de chiffre d'affaires n'est pas pénalisé.

---

## 🧪 Tests

```bash
cd backend
python manage.py test api
```

---

## 🛠️ Dépannage

### Erreur de connexion à l'API

1. Vérifiez que le backend tourne
2. Vérifiez `http://localhost:8000/api/` dans le navigateur
3. Vérifiez que `frontend/config.js` pointe sur le bon port

### Redirection en boucle vers la page de connexion

Le token stocké est invalide. Videz-le puis reconnectez-vous :
```js
localStorage.removeItem('authToken');
localStorage.removeItem('authUser');
```

### « blocked by CORS policy »

L'origine du frontend doit figurer dans `CORS_ALLOWED_ORIGINS` (fichier `.env`).
`localhost` et `127.0.0.1` sont deux origines **distinctes** pour le navigateur.

### « Aucun profil d'équipe n'est rattaché à ce compte » (403)

Le compte a été créé avant la migration ou son profil a été supprimé.
Créez-le dans l'administration Django, section **Membres**.

### Port déjà utilisé

```bash
python manage.py runserver 8002
python -m http.server 8002
```

### Filtre de dates rejeté

Le `+` du décalage horaire ISO doit être encodé en `%2B` dans une URL.

---

## ⚡ Raccourcis

```bash
# Régénérer un jeu de démonstration complet
python manage.py seed_demo --months 6 --reset

# Réinitialiser la base
python manage.py flush

# Migrations
python manage.py makemigrations
python manage.py migrate

# Journaux
tail -f backend/logs/fluxgestion.log

# Shell Django
python manage.py shell
```

---

## 📚 Pour aller plus loin

- [README.md](README.md) — vue d'ensemble
- [docs/API.md](docs/API.md) — référence de l'API
- [CONFIG_GUIDE.md](CONFIG_GUIDE.md) — fichiers de configuration
