# Documentation de l'API REST

## Base URL

```
http://localhost:8000/api
```

## Authentification

L'API s'authentifie par token. Tous les endpoints hors `/auth/register/` et
`/auth/login/` exigent le header :

```
Authorization: Token VOTRE_TOKEN
```

Un appel non authentifié retourne `401 Unauthorized`. Un compte authentifié
mais sans profil d'équipe retourne `403 Forbidden`.

## Règle de visibilité

Deux rôles gouvernent tous les accès :

| Rôle | Ce qu'il voit |
|------|---------------|
| `member` | Ses objectifs, sa feuille de route, ses tâches et ses rapports, rien d'autre |
| `founder` | Les données de toute l'équipe, plus la vue de synthèse |

La règle est appliquée côté serveur sur chaque collection : demander
directement l'identifiant d'un objet appartenant à un collègue retourne `404`,
et non le contenu. Les vues réservées aux fondateurs retournent `403`.

Le **premier compte créé** sur une instance devient fondateur, sans quoi
personne ne pourrait consulter l'équipe. Les comptes suivants sont des membres.

## Réponses

Les collections sont paginées :

```json
{
    "count": 42,
    "next": "http://localhost:8000/api/tasks/?page=2",
    "previous": null,
    "results": []
}
```

Les erreurs suivent le format DRF : `{"detail": "..."}` ou
`{"champ": ["message"]}`.

---

## Endpoints

### 🔐 AUTHENTIFICATION

#### Créer un compte
```
POST /auth/register/
Content-Type: application/json

{
    "username": "karim",
    "email": "karim@example.com",
    "first_name": "Karim",
    "last_name": "Benali",
    "job_title": "Responsable commercial",
    "department": "commercial",
    "password": "MotDePasse-Solide1",
    "password_confirm": "MotDePasse-Solide1"
}
```

**Réponse (201) :**
```json
{
    "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
    "user": {
        "id": 2,
        "member_id": 2,
        "username": "karim",
        "display_name": "Karim Benali",
        "role": "member",
        "job_title": "Responsable commercial",
        "department": "Commercial",
        "is_founder": false
    }
}
```

`job_title` et `department` sont facultatifs. Les pôles acceptés :
`direction`, `commercial`, `marketing`, `produit`, `technique`, `finance`,
`operations`.

#### Se connecter
```
POST /auth/login/
{ "username": "karim", "password": "MotDePasse-Solide1" }
```

#### Profil, mot de passe, déconnexion
```
GET   /auth/me/
POST  /auth/change-password/    { "old_password": "...", "new_password": "..." }
POST  /auth/logout/
```

`change-password` révoque l'ancien token et en retourne un nouveau.

---

### 👥 MEMBRES

```
GET   /members/         Liste (soi-même, ou l'équipe pour un fondateur)
GET   /members/me/      Son propre profil
PATCH /members/me/      Modifier son profil
```

`PATCH /members/me/` accepte `first_name`, `last_name`, `job_title`,
`department`, `phone`, `joined_on`. **Le rôle n'est pas modifiable par l'API** :
il se change dans l'administration Django.

Le profil porte aussi ce qui gouverne le pointage et les congés, en **lecture
seule** pour son titulaire — seul un fondateur les modifie, depuis la page
*Utilisateurs* :

| Champ | Sens |
|-------|------|
| `work_starts_at` / `work_ends_at` | Journée de référence ; l'heure de début fixe le seuil de retard |
| `leave_entitlement` | Droit à congé annuel, en jours ouvrables (18 par défaut) |
| `leave_days_taken` | Congés payés accordés depuis le 1er janvier |
| `leave_balance` | Ce qu'il reste du droit annuel |

**Filtres :** `department`, `role`, `name`, `is_active`.

---

### 🎯 OBJECTIFS MENSUELS

Un objectif par membre et par mois. Le mois est toujours ramené à son premier
jour : saisir `2026-09-17` enregistre `2026-09-01`.

#### Lister et créer
```
GET  /objectives/
POST /objectives/
Content-Type: application/json

{
    "month": "2026-09-01",
    "revenue_target": "25000.00",
    "clients_target": 12,
    "focus": "Ouvrir le segment PME industrielles",
    "notes": "Deux dossiers glissent d'août."
}
```

Le membre est déduit du token : on ne pose que ses propres objectifs.
Au moins une cible (CA **ou** clients) doit être renseignée.

**Réponse :**
```json
{
    "id": 7,
    "member": 2,
    "member_name": "Karim Benali",
    "month": "2026-09-01",
    "month_label": "2026-09",
    "revenue_target": "25000.00",
    "revenue_achieved": "12000.00",
    "clients_target": 12,
    "clients_achieved": 5,
    "revenue_completion": 48.0,
    "clients_completion": 41.7,
    "completion": 44.9,
    "elapsed_ratio": 60.0,
    "is_at_risk": false,
    "revenue_gap": "13000.00",
    "roadmap_count": 4,
    "roadmap_done": 1,
    "status": "active",
    "focus": "Ouvrir le segment PME industrielles"
}
```

| Champ calculé | Sens |
|---------------|------|
| `revenue_completion` | Part du CA attendu déjà réalisée. `null` si aucune cible de CA |
| `clients_completion` | Idem pour les clients |
| `completion` | Moyenne des cibles réellement fixées |
| `elapsed_ratio` | Part du mois écoulée, pour comparer |
| `is_at_risk` | Vrai si `completion` accuse plus de 15 points de retard sur `elapsed_ratio` |
| `revenue_gap` | Montant restant à réaliser |

Une cible laissée à zéro est ignorée dans `completion` : un profil produit sans
objectif de CA n'est pas pénalisé.

#### Mois en cours
```
GET /objectives/current/
```
Retourne l'objectif du mois avec sa feuille de route, ou `404` s'il n'est pas
encore défini.

#### Clôturer un mois
```
PATCH /objectives/{id}/close/
```
Un mois clôturé n'est plus signalé comme en retard. Clôturer deux fois → `400`.

#### Historique mensuel
```
GET /objectives/history/?months=6
```
Série continue, un point par mois même sans objectif :
```json
[{"month": "2026-04", "revenue_target": 0.0, "revenue_achieved": 0.0,
  "clients_target": 0, "clients_achieved": 0}]
```

#### Export CSV
```
GET /objectives/export/?status=active&department=commercial
```
Respecte les filtres **et la visibilité** : un membre n'exporte jamais les
chiffres d'un collègue.

**Filtres :** `member`, `month`, `month_from`, `month_to`, `status`,
`department`, `revenue_min`, `revenue_max`.

---

### 🗺️ FEUILLE DE ROUTE

Les jalons se rattachent à un objectif mensuel.

```
GET    /roadmap/
POST   /roadmap/            { "objective": 7, "title": "...", "due_date": "2026-09-15" }
PATCH  /roadmap/{id}/
DELETE /roadmap/{id}/
PATCH  /roadmap/{id}/complete/
GET    /roadmap/overdue/
```

Rattacher un jalon à l'objectif d'un collègue retourne `400`.

Statut et avancement restent cohérents automatiquement : passer à `done` force
`progress` à 100 et horodate `completed_at` ; rouvrir un jalon efface la date
et ramène l'avancement sous 100.

**Filtres :** `objective`, `member`, `month`, `status`, `due_before`,
`due_after`, `has_due_date`.

---

### ✅ TÂCHES DU JOUR

```
GET    /tasks/
POST   /tasks/          { "title": "Relancer 10 prospects", "priority": 3 }
PATCH  /tasks/{id}/
DELETE /tasks/{id}/
PATCH  /tasks/{id}/complete/
```

`date` vaut aujourd'hui par défaut. `priority` va de 1 (basse) à 4 (urgente).
`roadmap_item` relie facultativement la tâche à un jalon — celui du membre
uniquement, sinon `400`.

#### Journée en cours
```
GET /tasks/today/
```
```json
{
    "date": "2026-09-02",
    "today": [],
    "late": [],
    "done_count": 3,
    "total_count": 5
}
```
`late` contient les tâches non terminées dont le jour est passé.

#### Reporter les retards
```
POST /tasks/carry_over/
```
Bascule sur aujourd'hui les tâches en retard **du membre appelant seulement**.

**Filtres :** `member`, `date`, `date_from`, `date_to`, `status`, `priority`,
`roadmap_item`, `department`, `linked`.

#### Chronomètre

```
PATCH /tasks/{id}/start/
PATCH /tasks/{id}/complete/
```

`start` pose `started_at` et passe la tâche en `in_progress` ; `complete` pose
`completed_at`. La lecture expose alors :

| Champ | Sens |
|-------|------|
| `duration_minutes` | Minutes écoulées ; une tâche en cours compte jusqu'à maintenant |
| `duration_label` | Durée lisible : « 45 min », « 2 h 05 » |
| `over_estimate` | Vrai au-delà d'un quart de plus que `estimated_minutes` |

Démarrer une tâche déjà en cours ou terminée retourne `400` : relancer le
chronomètre effacerait le temps déjà passé. Une tâche cochée sans avoir été
démarrée prend son achèvement comme départ — durée nulle plutôt qu'impossible.

---

### 📝 RAPPORTS

```
GET    /reports/
POST   /reports/
PATCH  /reports/{id}/
DELETE /reports/{id}/
PATCH  /reports/{id}/submit/
```

Bilan de période :

```json
{
    "period_type": "weekly",
    "period_start": "2026-08-31",
    "period_end": "2026-09-06",
    "summary": "Semaine correcte, deux dossiers avancent.",
    "achievements": "Trois rendez-vous tenus.",
    "blockers": "Attente de retour juridique.",
    "next_steps": "Relancer les devis en attente."
}
```

Rapport de mission ou de réunion :

```json
{
    "period_type": "mission",
    "period_start": "2026-08-24",
    "period_end": "2026-08-25",
    "title": "Mission de cadrage chez Aurore Industries",
    "location": "Lyon, siège du client",
    "participants": "Karim Ndiaye, Sophie Aubert (achats)",
    "summary": "Deux jours sur site pour cadrer le déploiement.",
    "achievements": "Périmètre arrêté, interlocuteurs identifiés.",
    "blockers": "Budget soumis à un arbitrage de fin de mois.",
    "decisions": "Priorité donnée au module de production.",
    "next_steps": "Envoyer la proposition chiffrée sous huit jours."
}
```

`period_type` : `daily`, `weekly`, `monthly`, `mission` ou `meeting`. La période
doit être ordonnée et ne pas dépasser un an.

`title`, `location`, `participants` et `decisions` sont facultatifs pour un
bilan de période. **`title` est obligatoire** pour `mission` et `meeting` :
sans objet, deux missions du même mois seraient indiscernables — l'omettre
retourne `400`. La lecture expose `is_event`, vrai pour ces deux types.

Une réunion tient sur une journée : le client envoie alors la même date en
`period_start` et `period_end`.

Un rapport est créé en `draft`. `submit` le passe en `submitted` et l'horodate ;
il devient alors **non modifiable par son auteur**. Soumettre un rapport au
bilan vide retourne `400`.

**Filtres :** `member`, `period_type`, `status`, `from_date`, `to_date`,
`department`.

---

### 💶 BULLETINS DE PAIE (gérant)

```
GET    /payslips/
POST   /payslips/
PATCH  /payslips/{id}/
DELETE /payslips/{id}/
GET    /payslips/summary/?month=AAAA-MM
```

```json
{
    "member": 4,
    "month": "2026-09-01",
    "base_salary": "450000.00",
    "worked_hours": "173.00",
    "overtime_hours": "6.00",
    "overtime_amount": "19500.00",
    "bonuses": "25000.00",
    "deductions": "15000.00",
    "contributions": "99000.00",
    "notes": "Prime de résultat du trimestre."
}
```

Les montants sont exprimés en **francs CFA**. Les deux décimales du champ
absorbent un arrondi de calcul ; l'interface n'en affiche aucune, le franc CFA
n'ayant pas de subdivision.

`worked_hours` compte les heures faites dans le mois, hors heures
supplémentaires : elle informe, elle n'entre dans aucun calcul.

La lecture ajoute `gross` (base + heures supplémentaires + primes) et `net`
(brut moins retenues et cotisations), tous deux calculés par le serveur, ainsi
que `staff_events` — les retards, observations, mises à pied et heures
supplémentaires du mois pour ce salarié. Ces fiches sont **en lecture seule
ici** : elles se saisissent dans le suivi du personnel, le bulletin les reprend
pour que son décompte se relise.

Un seul bulletin par membre et par mois. Un net négatif est refusé : il traduit
une saisie erronée, pas une paie réelle.

**Pas de brouillon.** Enregistrer un bulletin, c'est l'établir : il est
horodaté (`issued_at`) dès sa création et reste corrigeable — sa période
comprise — ou supprimable tant que le gérant le décide. Le `month` reçu est
ramené au premier jour de son mois.

**Visibilité.** Elle ne suit pas la règle commune :

| Qui | Ce qu'il lit |
|-----|--------------|
| Gérant | toute la paie ; seul à écrire |
| Salarié | ses propres bulletins |
| Fondateur | rien — l'avancement de son équipe, pas ses salaires |

Les écritures (`POST`, `PATCH`, `DELETE`, `summary`) restent réservées au
gérant et retournent `403` pour tout le monde d'autre.

**Filtres :** `member`, `month` (`AAAA-MM`), `department`.

---

### 🧾 SUIVI DU PERSONNEL (gérant)

```
GET    /staff-events/
POST   /staff-events/
PATCH  /staff-events/{id}/
DELETE /staff-events/{id}/
GET    /staff-events/summary/?month=AAAA-MM
```

```json
{
    "member": 4,
    "kind": "suspension",
    "date": "2026-08-27",
    "end_date": "2026-08-29",
    "is_paid": false,
    "reason": "Absence injustifiée de trois jours consécutifs.",
    "decision": "Mise à pied sans solde, notifiée par courrier."
}
```

`kind` : `suspension`, `observation`, `lateness` ou `overtime`. Chaque nature
porte sa propre mesure, exigée à la création :

| Nature | Champ requis | Lecture |
|--------|--------------|---------|
| `suspension` | `end_date` | `days`, `summary` (« 3 jours ») |
| `observation` | — | — |
| `lateness` | `minutes` | `summary` (« 35 min ») |
| `overtime` | `hours` | `summary` (« 4,50 h ») |

`reason` est obligatoire quelle que soit la nature. `recorded_by` est renseigné
par le serveur avec le gérant qui saisit : une sanction doit rester imputable.

**Filtres :** `member`, `kind`, `from_date`, `to_date`, `department`.

---

### 🏖️ CONGÉS ET ABSENCES

```
GET    /leaves/
POST   /leaves/
PATCH  /leaves/{id}/
DELETE /leaves/{id}/
PATCH  /leaves/{id}/decide/
PATCH  /leaves/{id}/cancel/
GET    /leaves/balance/?year=2026
```

```json
{
    "kind": "paid",
    "start_date": "2026-11-02",
    "end_date": "2026-11-06",
    "half_day": false,
    "reason": "Congé annuel, relais assuré par le pôle."
}
```

`kind` : `paid` (congé payé), `unpaid` (sans solde), `sick` (maladie) ou
`special` (absence exceptionnelle). Seul `paid` **entame le droit annuel** —
`is_counted` le dit sur chaque demande.

**Qui pose, qui tranche.** La demande est toujours celle de son auteur : un
`member` transmis à la création est ignoré, personne ne pose un congé au nom
d'un collègue. `status` naît à `pending` et ne se force pas ; seule la
direction (fondateur ou gérant) le change, par `decide`.

| Action | Qui | Effet |
|--------|-----|-------|
| `PATCH /leaves/{id}/` | l'auteur | Corrige sa demande, **tant qu'elle est en attente** |
| `DELETE /leaves/{id}/` | l'auteur | Retire une demande en attente |
| `PATCH .../decide/` | direction | `{"status": "approved"\|"refused", "decision": "…"}` |
| `PATCH .../cancel/` | l'auteur ou la direction | Annule une demande en cours, si elle n'est pas écoulée |

Une demande tranchée est **figée** : la modifier retourne `400`, elle s'annule
ou se repose. Une décision garde son auteur (`decided_by`) et sa date
(`decided_at`) : accorder un congé engage celui qui l'accorde.

**Validation.** Les dates s'ordonnent et ne dépassent pas un an ; une période
sans aucun jour ouvrable est refusée ; `half_day` tient sur un seul jour ; le
motif est obligatoire. Deux demandes du même membre **ne peuvent pas se
chevaucher** tant qu'elles sont en attente ou accordées — sans quoi les mêmes
jours seraient décomptés deux fois.

**Décompte.** `days` compte les jours ouvrables, bornes comprises : samedis et
dimanches ne pèsent pas, et une demi-journée vaut 0,5. `days_label` en donne la
forme lisible.

`balance` rend le solde de l'année — le sien pour un membre, celui de toute
l'équipe pour la direction :

```json
{
    "year": 2026,
    "members": [
        {
            "member_id": 2, "member_name": "Karim Benali", "department": "commercial",
            "entitlement": 18, "taken": 5.0, "pending": 0.5, "balance": 13.0
        }
    ]
}
```

`entitlement` vit sur le profil (18 jours par défaut, soit un jour et demi par
mois de service) et n'est modifiable que par un fondateur. `taken` ne compte
que les congés payés **accordés** ; `pending` montre à part ce qui attend une
réponse, puisque ce n'est pas encore pris.

**Filtres :** `member`, `kind`, `status`, `from_date`, `to_date`, `year`,
`department`. Les bornes retiennent tout ce qui chevauche la période : un congé
à cheval sur deux mois appartient aux deux.

---

### 🕘 POINTAGE

```
GET    /attendance/
GET    /attendance/today/
POST   /attendance/check_in/
POST   /attendance/check_out/
GET    /attendance/summary/?month=AAAA-MM
POST   /attendance/            (direction)
PATCH  /attendance/{id}/       (direction)
DELETE /attendance/{id}/       (direction)
```

Une ligne par membre et par jour. **L'équipe pointe, la direction corrige** :
créer ou retoucher un pointage à la main revient à corriger des heures payées,
un membre qui essaie reçoit `403`. Il agit par `check_in` et `check_out`, qui
n'acceptent aucune heure : l'horloge du serveur fait foi.

```json
{
    "id": 96, "member": 2, "member_name": "Karim Benali",
    "date": "2026-09-07",
    "check_in": "2026-09-07T08:05:00+02:00",
    "check_out": "2026-09-07T17:10:00+02:00",
    "minutes": 545, "hours": "9.08", "duration_label": "9 h 05",
    "late_minutes": 0, "is_open": false, "is_late": false
}
```

**Le retard se calcule, il ne se saisit pas.** Il compare l'arrivée à l'heure
de début du profil (`work_starts_at`, 8 h par défaut), tolérance de dix minutes
déduite. Le champ est en lecture seule : l'effacer sans corriger l'heure n'a
pas de sens. Corriger l'arrivée le recalcule.

**Une journée close ne se rouvre pas.** `check_in` répété rend le pointage déjà
ouvert (`200` au lieu de `201`) ; après un départ pointé, il retourne `400`.
`check_out` sans arrivée, ou deux fois, retourne `400`.

**Un départ oublié ne court pas indéfiniment** : une journée passée restée
ouverte s'arrête à l'heure de fin prévue (`work_ends_at`), et la tâche
`close_stale_attendance` la referme chaque nuit.

`today` rend sa journée, son congé du jour s'il y en a un, et ce que le mois
compte déjà :

```json
{
    "date": "2026-09-07",
    "attendance": {},
    "on_leave": null,
    "month": {"days": 5, "hours": 41.67, "late_minutes": 32}
}
```

`summary` rend le mois membre par membre — toute l'équipe pour la direction,
sa seule ligne pour un membre :

```json
{
    "month": "2026-09",
    "working_days": 5,
    "totals": {"members": 6, "days": 29, "hours": 232.68, "late_minutes": 110,
               "leave_days": 5, "absences": 0},
    "members": [
        {
            "member_id": 2, "member_name": "Karim Benali",
            "department": "commercial", "job_title": "Responsable commercial",
            "days": 5, "hours": 41.83, "late_minutes": 37,
            "leave_days": 0, "absences": 0
        }
    ]
}
```

`working_days` borne le mois aux jours ouvrables **déjà écoulés** : un mois en
cours ne se juge pas sur des journées à venir. `absences` en découle — ce qui
n'est ni pointé ni couvert par un congé accordé. Le gérant reporte `hours` sur
le bulletin de paie d'un clic, sans que rien s'y inscrive tout seul.

**Filtres :** `member`, `date`, `from_date`, `to_date`, `late`, `open`,
`department`.

---

### ⭐ RÉACTIONS ET POINTS

```
GET    /reactions/
POST   /reactions/
DELETE /reactions/{id}/
GET    /reactions/scale/
```

```json
{
    "member": 4,
    "kind": "objectif",
    "points": 25,
    "reason": "Campagne livrée avant terme",
    "date": "2026-09-03"
}
```

`kind` : `objectif` (+20), `bravo` (+10), `initiative` (+15), `entraide` (+5),
`rappel` (−5), `manquement` (−15). `points` est **facultatif** : omis, il prend
la valeur du barème ; fourni, il la remplace — une même occasion ne pèse pas
toujours pareil. Une réaction à zéro point est refusée : elle ne dirait rien.

**Qui réagit.** Seule la direction accorde ou retire des points ; un membre qui
essaie reçoit `403`, y compris pour se créditer lui-même. Chacun relit en
revanche les réactions qu'il a reçues.

**Ce que les points ouvrent.** Le profil (`/members/me/`) expose :

| Champ | Sens |
|-------|------|
| `points_month` | Points du mois en cours, positifs ou négatifs |
| `points_total` | Cumul depuis l'arrivée |
| `bonus_earned` | Prime du mois : `max(points_month, 0) × POINT_VALUE` |

Un solde négatif **n'entame jamais le salaire** : il ramène la prime à zéro,
sans la rendre débitrice. La prime est mensuelle et ne se reporte pas : les
points du mois précédent comptent dans le cumul, pas dans la prime du mois.

`scale` publie le barème et la valeur du point (2 000 FCFA), pour que
l'interface n'en recopie aucune constante.

---

### 💡 BOÎTE À SUGGESTIONS

```
GET    /suggestions/
POST   /suggestions/
PATCH  /suggestions/{id}/
DELETE /suggestions/{id}/
PATCH  /suggestions/{id}/handle/
```

```json
{
    "category": "idea",
    "message": "Un rappel deux jours avant l'échéance d'un jalon."
}
```

`category` : `idea`, `problem` ou `question`. Le message fait au moins dix
caractères — une suggestion vide n'apprend rien à personne.

**Visibilité** : chacun relit ses propres dépôts, un fondateur ou un gérant lit
toute la boîte, puisqu'elle leur est adressée. L'auteur peut corriger ou retirer
son message **tant que personne ne l'a ouvert** ; une fois lu, il est figé.

`handle` (direction) passe la suggestion en `read` ou `done` et enregistre une
`reply` facultative, avec l'auteur de la réponse et son horodatage.

---

### 🔔 NOTIFICATIONS

```
GET /dashboard/notifications/
```

```json
{
    "count": 3,
    "items": [
        {
            "kind": "tasks_late",
            "level": "warning",
            "page": "tasks",
            "title": "2 tâche(s) en retard",
            "detail": "Reportez-les ou terminez-les.",
            "count": 2
        }
    ]
}
```

Les alertes **ne sont pas stockées** : chacune décrit une situation vérifiée à
l'appel. Une tâche rattrapée ou une suggestion traitée fait disparaître sa ligne
d'elle-même — il n'y a donc rien à « marquer comme lu », ce qui ne voudrait rien
dire pour un état vivant.

`kind` : `objective_missing`, `objective_at_risk`, `tasks_late`,
`roadmap_overdue`, `attendance_missing` et `attendance_open` ; `suggestions_new`
et `leaves_pending` sont réservées à la direction. `page` indique l'entrée de
menu à ouvrir, ou `null` quand l'alerte s'ouvre ailleurs.

Le pointage n'est rappelé qu'un **jour ouvré**, et jamais à quelqu'un dont le
congé est accordé : lui reprocher son absence n'aurait aucun sens.

---

### 👤 ADMINISTRATION DES COMPTES (fondateurs)

```
POST   /members/
PATCH  /members/{id}/
DELETE /members/{id}/
PATCH  /members/{id}/set_active/
PATCH  /members/{id}/reset_password/
```

```json
{
    "username": "amina",
    "first_name": "Amina",
    "last_name": "Sow",
    "email": "amina@fluxgestion.local",
    "role": "manager",
    "department": "direction",
    "job_title": "Responsable administrative"
}
```

`base_salary` est la rémunération de référence : elle vit sur le profil et se
consulte sans attendre qu'un bulletin ait été établi. Comme le rôle, elle n'est
modifiable que par un fondateur — sur `/members/me/`, les deux champs sont en
lecture seule.

`role` : `member` (profil employé), `manager` ou `founder` (profils
administratifs). Le champ n'est modifiable que par un fondateur ; pour tout le
monde d'autre il est en lecture seule, y compris sur `/members/me/`.

**Mot de passe.** `password` est facultatif : omis, le serveur en engendre un et
le retourne dans `generated_password`, **une seule fois**. Un mot de passe
fourni par l'appelant n'est jamais réémis — il le connaît déjà. `reset_password`
en engendre un nouveau et le retourne de la même façon.

**Désactiver plutôt que supprimer.** `set_active` avec `{"active": false}`
empêche la connexion et laisse l'historique intact — objectifs, tâches,
rapports, bulletins. `DELETE` supprime le compte **et tout ce qui s'y rattache**.

Trois garde-fous, tous vérifiés côté serveur :

| Refus | Raison |
|-------|--------|
| Supprimer ou désactiver son propre compte | On ne se ferme pas la porte |
| Rétrograder ou supprimer le dernier fondateur | L'instance ne serait plus administrable |
| Identifiant déjà pris (à la casse près) | Deux comptes indiscernables |

---

### 📡 PANEL (fondateurs)

```
GET /dashboard/panel/
```

```json
{
    "generated_at": "2026-09-03T00:12:41Z",
    "date": "2026-09-03",
    "totals": {
        "team_size": 7, "working": 2, "idle": 1, "no_tasks": 3, "on_leave": 1,
        "checked_in": 5, "late_arrivals": 1,
        "minutes_logged": 169, "tasks_total": 5, "tasks_done": 1, "tasks_late": 37
    },
    "members": [
        {
            "member_id": 3, "member_name": "Léa Moreau", "job_title": "Chargée d'acquisition",
            "department": "marketing", "status": "idle",
            "tasks_total": 2, "tasks_done": 0, "tasks_late": 5,
            "minutes_logged": 0, "current_task": null, "on_leave": "",
            "attendance": {
                "check_in": "2026-09-07T08:05:00+02:00", "check_out": null,
                "is_open": true, "late_minutes": 0, "duration_label": "3 h 12"
            }
        }
    ],
    "recent_reports": []
}
```

`status` décrit la journée du membre :

| Valeur | Sens |
|--------|------|
| `working` | Une tâche est en cours à l'instant ; `current_task` la décrit |
| `idle` | Des tâches sont planifiées, aucune n'a été entamée |
| `no_tasks` | Aucune tâche planifiée aujourd'hui |
| `done` | Toutes les tâches du jour sont terminées |
| `on_leave` | Congé accordé couvrant aujourd'hui ; `on_leave` en donne la nature |

Un congé prime sur tout le reste : il explique l'absence de tâche comme de
pointage. `attendance` porte la journée pointée, ou `null` si le membre n'a pas
encore pointé.

Les membres sont triés par ce qui appelle une réaction : `idle` d'abord, puis
`no_tasks`, `working` et `done` ; un congé accordé ne cloche pas, il ferme la
liste. À égalité, les plus en retard en tête.

Tout est **recalculé à l'appel** : rien n'est mis en cache, démarrer une tâche
change la réponse suivante. Le client relit la vue toutes les trente secondes,
et cesse dès qu'il quitte la page.

---

### 📊 TABLEAUX DE BORD

#### Vue personnelle
```
GET /dashboard/overview/
```
```json
{
    "member": {},
    "month": "2026-09-01",
    "objective": {},
    "tasks": {"total": 5, "done": 3, "blocked": 0, "late": 2, "items": []},
    "roadmap": {"total": 4, "done": 1, "blocked": 0, "overdue": 1},
    "attendance": {},
    "on_leave": null,
    "leave_balance": 13.0,
    "last_report": {},
    "reports_this_month": 1
}
```
`objective` vaut `null` si le mois n'est pas encore défini. `attendance` porte
la journée pointée du jour, `on_leave` le congé accordé qui la couvre, l'un et
l'autre `null` le cas échéant.

#### Vue d'équipe (fondateurs)
```
GET /dashboard/team/?month=2026-09
```
`403` pour un membre. Sans `month`, le mois en cours.

```json
{
    "month": "2026-09-01",
    "team_size": 5,
    "members_with_objective": 4,
    "members_at_risk": 1,
    "revenue_target": 85000.0,
    "revenue_achieved": 42000.0,
    "revenue_completion": 49.4,
    "clients_target": 54,
    "clients_achieved": 21,
    "members": []
}
```

`members` est trié du plus en retard au plus avancé : ceux qui décrochent
apparaissent en tête. Chaque ligne porte `open_tasks` et `reports_submitted`
**bornés au mois affiché** — un rapport à cheval sur deux mois compte pour les
deux.

Les membres sans objectif défini apparaissent avec `has_objective: false`
plutôt que d'être absents : c'est justement l'information utile.

#### Activité
```
GET /dashboard/activity/?days=14
```
Série continue de tâches prévues et terminées, un point par jour.

---

## Codes d'erreur

| Code | Sens |
|------|------|
| `200` / `201` | Succès |
| `204` | Suppression effectuée |
| `400` | Données invalides ou action impossible (double clôture, rapport vide) |
| `401` | Token absent ou invalide |
| `403` | Profil manquant, ou vue réservée aux fondateurs |
| `404` | Objet inexistant **ou hors de votre périmètre de visibilité** |

---

## Recherche, tri, pagination

```
GET /tasks/?search=prospect          # titre et description
GET /objectives/?ordering=-month     # tri, préfixe - pour décroissant
GET /reports/?page=2
```

> Les dates ISO portent un `+` dans leur décalage horaire : encodez-le en
> `%2B` dans une URL, sinon il arrive comme une espace et sera rejeté.

---

## Exemples cURL

```bash
# Connexion
curl -X POST http://localhost:8000/api/auth/login/ \
     -H "Content-Type: application/json" \
     -d '{"username":"karim","password":"demo1234"}'

# Poser ses objectifs du mois
curl -X POST http://localhost:8000/api/objectives/ \
     -H "Authorization: Token VOTRE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"month":"2026-09-01","revenue_target":"25000","clients_target":12}'

# Ajouter une tâche du jour
curl -X POST http://localhost:8000/api/tasks/ \
     -H "Authorization: Token VOTRE_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"title":"Relancer 10 prospects","priority":3}'

# Journée en cours
curl -H "Authorization: Token VOTRE_TOKEN" \
     http://localhost:8000/api/tasks/today/

# Export CSV des objectifs
curl -H "Authorization: Token VOTRE_TOKEN" \
     -o objectifs.csv \
     "http://localhost:8000/api/objectives/export/?status=active"

# Synthèse d'équipe (fondateur)
curl -H "Authorization: Token VOTRE_TOKEN" \
     "http://localhost:8000/api/dashboard/team/?month=2026-09"
```
