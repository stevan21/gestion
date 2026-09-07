# Déploiement sur un serveur partagé

Ces fichiers déploient Flux Gestion **à côté** d'autres applications, sur un
serveur où nginx tient déjà les ports 80 et 443. Le `docker-compose.yml` de la
racine ne convient pas à ce cas : il réclame ces ports pour lui seul et
couperait les sites voisins. Il reste valable sur une machine dédiée.

## Ce que la disposition suppose

| Élément | Emplacement |
|---------|-------------|
| Code | `/opt/fluxgestion` (dépôt cloné) |
| Environnement Python | `/opt/fluxgestion/.venv` |
| Variables | `/etc/fluxgestion.env`, lu par les trois services |
| Socket gunicorn | `/run/fluxgestion/gunicorn.sock` |
| Statiques Django | `/opt/fluxgestion/backend/staticfiles/` |
| SPA | `/opt/fluxgestion/frontend/` |

PostgreSQL et Redis sont ceux de la machine, avec une base et un index Redis
qui n'appartiennent qu'à cette application.

## Installation

```bash
# 1. Le code
git clone https://github.com/stevan21/gestion.git /opt/fluxgestion
python3 -m venv /opt/fluxgestion/.venv
/opt/fluxgestion/.venv/bin/pip install -r /opt/fluxgestion/backend/requirements.txt

# 2. La base
sudo -u postgres createuser fluxgestion --pwprompt
sudo -u postgres createdb fluxgestion_db --owner=fluxgestion

# 3. Les variables — voir backend/.env.production pour la liste complète
sudo install -m 640 -o root -g www-data /dev/null /etc/fluxgestion.env
sudo nano /etc/fluxgestion.env

# 4. Base et statiques
cd /opt/fluxgestion/backend
set -a; . /etc/fluxgestion.env; set +a
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py collectstatic --noinput

# 5. Les services
sudo cp /opt/fluxgestion/deploy/fluxgestion*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fluxgestion fluxgestion-worker fluxgestion-beat

# 6. Le vhost, puis le certificat
sudo cp /opt/fluxgestion/deploy/nginx-fluxgestion.conf \
        /etc/nginx/sites-available/fluxgestion
sudo ln -s /etc/nginx/sites-available/fluxgestion /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d fluxgestion.76.13.146.34.sslip.io
```

`nginx -t` avant tout rechargement : sur un serveur partagé, une erreur de
syntaxe empêcherait nginx de redémarrer et emporterait les autres sites.

## Le nom de domaine

Faute de domaine propre, `<sous-domaine>.<IP>.sslip.io` et son équivalent
`nip.io` renvoient l'IP qu'ils portent dans leur nom : aucune zone DNS à
tenir, et Let's Encrypt y délivre un certificat.

**Tous les résolveurs ne les acceptent pas.** Certains FAI ne répondent pas
aux requêtes visant ces domaines génériques — la page devient injoignable
depuis ce réseau-là, alors que le serveur répond normalement partout ailleurs.
Pour distinguer les deux cas :

```bash
# Résout ailleurs mais pas ici : c'est le résolveur local, pas le serveur.
nslookup <hôte> 8.8.8.8

# Contourne le DNS et interroge le serveur directement.
curl -I --resolve '<hôte>:443:<IP>' https://<hôte>/login.html
```

Un sous-domaine d'un domaine que l'on possède déjà évite la question : un
enregistrement A vers l'IP, puis `certbot --nginx -d <sous-domaine>`.

## Le premier compte

Le premier compte créé sur une instance devient fondateur. Pour un gérant,
qui voit en plus la paie et le personnel :

```bash
cd /opt/fluxgestion/backend
set -a; . /etc/fluxgestion.env; set +a
../.venv/bin/python manage.py create_manager <identifiant> \
    --first-name <prénom> --last-name <nom>
```

Le mot de passe est engendré et affiché **une seule fois**.

Chargez l'environnement comme ci-dessus, ne passez pas par `sudo -u www-data` :
sudo vide l'environnement, Django retombe alors sur SQLite et crée une base
vide à côté de la vraie, sans rien signaler d'autre qu'une table manquante.

## Mettre à jour

```bash
cd /opt/fluxgestion
git pull
.venv/bin/pip install -r backend/requirements.txt
cd backend
set -a; . /etc/fluxgestion.env; set +a
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart fluxgestion fluxgestion-worker fluxgestion-beat
```

Le frontend est servi depuis le dépôt : un `git pull` suffit à le mettre à
jour, sans redémarrage.
