# Changelog

Toutes les évolutions notables de Flux Gestion sont consignées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/) et le
projet respecte le [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

### Ajouté
- **Congés et absences** : chacun pose ses dates et son motif depuis la page
  *Congés*, la direction accorde ou refuse avec sa réponse. Quatre natures —
  congé payé, sans solde, maladie, absence exceptionnelle —, un décompte en
  jours ouvrables, demi-journée comprise, et un droit annuel porté par le
  profil (dix-huit jours par défaut) que seul le congé payé entame. Deux
  demandes du même membre ne peuvent pas se chevaucher, une demande tranchée
  est figée, et un congé accordé s'annule tant qu'il n'est pas écoulé
- **Pointage** : un bouton dans la barre du haut, dont l'état dit où en est la
  journée — arrivée à pointer, journée en cours avec son compteur, journée
  close. Le retard se calcule contre l'heure de début du profil, dix minutes de
  tolérance déduites, et reste en lecture seule : l'effacer sans corriger
  l'heure n'aurait pas de sens. Un départ oublié ne court plus jusqu'au
  lendemain, il s'arrête à l'heure de fin prévue et la tâche
  `close_stale_attendance` referme la journée dans la nuit
- **Page *Présences*** (direction) : le mois membre par membre — journées
  pointées, heures, retards, congés et absences sans motif — puis la journée en
  cours, arrivée par arrivée. Les jours ouvrables **déjà écoulés** servent de
  repère : un mois en cours ne se juge pas sur des journées à venir
- **Heures pointées reportées sur le bulletin de paie** : le décompte du mois
  se rappelle sous le champ « Heures travaillées » et s'inscrit d'un clic,
  comme la prime des points — le gérant reste maître du chiffre porté
- **Le panel dit qui est en congé et qui a pointé** : un congé accordé prime
  sur l'état des tâches, et chaque ligne porte l'heure d'arrivée, celle du
  départ et le retard éventuel. Une journée d'absence ne ressemble plus à une
  journée sans tâches
- **Deux alertes de plus à la cloche** : arrivée non pointée un jour ouvré, et
  journée restée ouverte ; la direction voit en outre les demandes de congé en
  attente. Le rappel de pointage ne part jamais à quelqu'un dont le congé est
  accordé
- **Journée de référence et droit à congé sur le profil** : `work_starts_at`,
  `work_ends_at` et `leave_entitlement`, modifiables par un fondateur seul,
  comme le rôle et le salaire de base
- **Heures travaillées sur le bulletin de paie** : le décompte du mois portait
  les heures supplémentaires sans jamais dire sur quel volume elles s'ajoutaient.
  Le champ informe — il n'entre dans aucun calcul — et remonte en synthèse de
  la page *Bulletins de paie*
- **Retards, observations et mises à pied repris sur le bulletin** : une retenue
  s'explique par une absence, une prime par des heures faites ; le décompte seul
  ne se relisait pas. Les évènements du mois du salarié apparaissent sous le
  décompte, dans la fiche « Ma rémunération » et sur le PDF, et se rappellent au
  gérant pendant qu'il chiffre. Ils restent **en lecture seule** : le suivi du
  personnel demeure leur seule source de saisie

### Modifié
- **Le bulletin de paie n'a plus de brouillon** : l'enregistrer, c'est
  l'établir. Le bouton « Émettre », le filtre d'état et le badge disparaissent,
  ainsi que `PATCH /payslips/{id}/issue/`. Le salarié voit son bulletin dès
  qu'il est établi, sans seconde manipulation du gérant

### Corrigé
- **Le planificateur Celery appelait trois tâches qui n'existaient plus** :
  `generate_daily_report`, `check_performance_alerts` et `refresh_metrics`,
  vestiges du domaine infrastructure abandonné en 2.0.0. Le calendrier ne
  connaissait donc que `cleanup_old_data`, et aucune des cinq tâches réellement
  écrites — ouverture des objectifs du mois, clôture du mois précédent, alertes
  de retard, rappels de rapport, report des tâches — n'était planifiée : elles
  ne partaient jamais, et beat consignait une erreur toutes les cinq minutes.
  Le calendrier reprend les vraies tâches, à des heures fixes plutôt qu'à
  intervalle depuis le démarrage du worker — un rappel de rapport doit tomber
  le lundi matin
- **La période d'un bulletin ne se corrigeait plus une fois celui-ci
  enregistré** : le champ « Mois » était verrouillé à la modification et n'était
  de toute façon jamais transmis. Un mois saisi de travers obligeait à supprimer
  le bulletin pour le ressaisir. Il se corrige désormais comme n'importe quel
  autre champ, l'unicité par membre et par mois restant garantie

## [2.0.0] - 2026-09-02

**Changement de domaine.** Le produit suivait des mesures d'infrastructure
(CPU, mémoire, latence). Il suit désormais la performance d'une équipe de
startup : chaque membre pose ses objectifs du mois, détaille sa feuille de
route, planifie ses tâches et rend ses rapports.

Version majeure : l'API et le modèle de données changent entièrement.

### Ajouté
- **Points et réactions** : la direction salue ou rappelle un membre — objectif
  atteint, bravo, initiative, entraide, rappel, manquement — depuis le panel de
  suivi. Chaque réaction pèse en points, ajustables à la saisie, et le cumul du
  mois ouvre une prime à 2 000 FCFA le point, que le gérant reporte d'un clic
  sur le bulletin. Un solde négatif ramène la prime à zéro sans jamais entamer
  le salaire, et la prime ne se reporte pas d'un mois sur l'autre
- **Salaire de base sur le profil** : il vit désormais sur la fiche du membre et
  s'affiche sans qu'un bulletin ait été établi. Comme le rôle, il n'est
  modifiable que par un fondateur
- **Fiche « Mon profil »** : depuis le menu utilisateur de la barre du haut —
  identité, poste, pôle, date d'arrivée, **sa propre rémunération** (le net du
  mois, son décompte et les bulletins précédents, exportables en PDF) et le
  **changement de mot de passe**, qui n'avait jusqu'ici aucun écran malgré une
  API existante
- **Administration des comptes** : une page *Utilisateurs* pour créer, modifier,
  désactiver ou supprimer un compte et lui attribuer son profil — employé, ou
  administratif (gérant, fondateur). Le mot de passe est engendré et affiché une
  seule fois, jamais stocké en clair ; la désactivation coupe l'accès sans rien
  perdre de l'historique, là où la suppression emporte tout. Trois garde-fous :
  on ne supprime pas son propre compte, on ne retire pas le dernier fondateur,
  et deux identifiants ne peuvent pas se confondre
- **Panel du fondateur** : une page de suivi en direct. Qui travaille et sur
  quelle tâche, depuis quand, qui n'a rien entamé de sa journée, le temps pointé
  par chacun, les retards, et les derniers rapports reçus — un clic ouvre le
  document imprimable. Les lignes sont triées par ce qui appelle une réaction.
  La vue se relit toutes les trente secondes tant qu'elle est affichée, et cesse
  dès qu'on la quitte : rien n'interroge le serveur depuis une page qu'on ne
  regarde plus
- **Chronomètre des tâches** : deux boutons, « Démarrer » et « Terminer », qui
  posent l'heure de départ et celle de fin. La ligne affiche les deux heures et
  le temps passé — « 21:21 → 22:56 · 1 h 35 » — plutôt que de les cacher dans
  une infobulle. Au-delà d'un quart de plus que la durée estimée, le temps passe
  à l'orange
- **Boîte à suggestions** : chacun dépose une idée, un problème ou une question
  depuis la barre du haut ; la direction relit toute la boîte, répond et clôt.
  Un message est figé dès qu'il a été lu
- **Cloche de notifications** : objectif du mois manquant, retard sur le mois,
  tâches en retard, jalons dépassés, suggestions à lire. Les alertes ne sont pas
  stockées — chacune décrit une situation vérifiée à l'appel et disparaît quand
  elle est réglée, ce qui évite un « marquer comme lu » vide de sens
- **Identité et déconnexion dans la barre du haut** : le bloc utilisateur quitte
  le pied du rail pour la barre supérieure, avec le nom, le rôle et le menu de
  déconnexion
- **`create_manager`** : commande d'administration qui crée un gérant ou
  promeut un compte existant. Le mot de passe omis est engendré et affiché une
  seule fois ; `--promote` laisse en place le pôle, le poste et le mot de passe
- **Profil gérant** : un troisième rôle qui reprend la visibilité d'équipe du
  fondateur et y ajoute la gestion du personnel. La paie et le disciplinaire
  lui restent réservés — un fondateur qui les demande reçoit `403`
- **Bulletins de paie** : un par membre et par mois, salaire de base, heures
  supplémentaires, primes, retenues et cotisations ; brut et net calculés par
  le serveur, émission qui rend le bulletin définitif, export PDF avec cadres
  de signature
- **Suivi du personnel** : mises à pied, observations, retards et heures
  supplémentaires dans une même main courante. Chaque nature porte sa mesure
  (jours, minutes, heures) et l'auteur de la fiche est conservé
- **Rapports de mission et de réunion** : deux types s'ajoutent aux bilans de
  période, avec objet, lieu et participants. Le formulaire et l'affichage
  s'adaptent au type choisi — « Déroulé de la mission » pour une mission,
  « Compte rendu » et « Décisions » pour une réunion, qui tient sur une seule
  date
- **Export PDF d'un rapport** : le document est mis en page comme une pièce
  officielle (en-tête, cartouche auteur/dates/lieu/participants, sections) et
  part à l'impression, que le navigateur sait enregistrer en PDF. Aucune
  bibliothèque tierce : le texte du fichier reste sélectionnable
- **Modèle métier** : `Member`, `MonthlyObjective`, `RoadmapItem`, `DailyTask`,
  `Report`
- **Objectifs mensuels** : CA et clients attendus contre réalisés, un jeu par
  membre et par mois, avancement comparé au temps écoulé
- **Détection du retard** : un objectif est signalé au-delà de 15 points
  d'écart avec la part du mois écoulée ; un mois clôturé ne l'est jamais
- **Feuille de route** : jalons rattachés à l'objectif du mois, échéances,
  avancement, détection des dépassements
- **Tâches du jour** : priorités, rattachement facultatif à un jalon, report
  des retards en un appel
- **Rapports** : périodes journalière, hebdomadaire ou mensuelle ; brouillon
  puis soumission, verrouillés une fois rendus
- **Rôles et visibilité** : un membre voit ses données, un fondateur voit
  l'équipe ; règle appliquée sur chaque collection côté serveur
- **Vue d'équipe** : cumuls de CA et de clients, membres sans objectif, membres
  en retard, triés du plus en difficulté au plus avancé
- **Profil automatique** : tout compte créé reçoit un profil d'équipe ; le
  premier compte d'une instance devient fondateur
- **`frontend/config.js`** : adresse de l'API configurable, nom d'hôte déduit
  de la page pour éviter le piège `localhost` ≠ `127.0.0.1`. Elle se redirige
  aussi à l'ouverture — `?api=http://127.0.0.1:8765/api`, retenue ensuite —
  pour les machines où le port 8000 appartient déjà à un autre projet
- **220 tests** unitaires et d'intégration

### Corrigé
- **Adresse de l'API figée sur le port 8000** : sur une machine où ce port sert
  déjà à un autre projet, la SPA interrogeait le voisin et paraissait muette,
  sans rien dire de compréhensible. L'adresse se redirige maintenant à
  l'ouverture (`?api=…`, retenue ensuite), sans modifier de fichier versionné
- **Salaire de base non reporté sur un bulletin neuf** : depuis que le salaire
  vit sur le profil, choisir un membre n'en reportait que la prime. Le champ
  restait à zéro et devait être retapé, au risque que la fiche et le bulletin
  affichent deux montants différents. Un bulletin déjà établi garde le sien
- **Personnel mis en cache pour toute la session** : un employé fraîchement
  créé n'apparaissait ni dans le sélecteur de la paie ni dans celui du
  personnel avant un rechargement complet, et un salaire corrigé y restait
  périmé. Toute modification de compte oublie désormais la liste
- **Suite de tests immobilisée par le hachage** : 636 comptes créés à travers
  la suite, chacun haché en PBKDF2 à un million d'itérations, occupaient 91 %
  des 32 minutes d'exécution. Un exécuteur dédié substitue un hachage rapide
  pendant les seuls tests — le réglage de production est inchangé. La suite
  passe de **1 940 s à 10 s**
- **Faille XSS stockée** : le contenu utilisateur (tâches, jalons, bilans)
  était injecté dans `innerHTML` sans échappement. Un membre pouvait faire
  exécuter du script chez ses collègues. Tout passe désormais par `escapeHtml`
- **Débordement horizontal** de la page : `flex: 1` sans `min-width: 0`
  empêchait la barre de navigation et les tuiles de se contracter
- **Décalage de date** : `toISOString()` sur une date à minuit local renvoyait
  la veille pour tout fuseau à l'est de Greenwich, dont `Europe/Paris`
- **Attribut `hidden` sans effet** : un `display` d'auteur l'emporte sur celui
  de l'agent utilisateur. Le badge des tâches restait affiché à zéro et
  l'entrée « Équipe », réservée aux fondateurs, était visible de tous
- **Bouton « Annuler » des modales** : il porte la classe `modal-close`, dont
  la mise en forme de la croix (police doublée, largeur figée à 40 px) écrasait
  celle du bouton. Cette mise en forme est désormais limitée à l'en-tête
- **Surcharges de fin de feuille de style** : placées après les media queries,
  elles reprenaient la main sur elles ; les tuiles gardaient leur largeur de
  bureau sur mobile. Elles sont repliées dans leurs sections d'origine
- **API injoignable sans retour visible** : chaque vue affiche désormais
  « Chargement impossible » et un bouton de relance, au lieu de rester vide
- **Chargements en double** : un clic répété sur une entrée de menu relançait
  la requête déjà en cours
- **Icône du bouton « Réessayer »** : `.empty-state i` habillait aussi les
  icônes de bouton, qui débordaient de leur cadre
- **Compteurs de la vue d'équipe** incohérents : les tâches ouvertes étaient
  comptées toutes dates confondues et les rapports seulement s'ils finissaient
  dans le mois. Les deux sont désormais bornés au mois affiché, et un rapport
  à cheval sur deux mois compte pour les deux
- L'indicateur de chargement disparaissait dès la première requête terminée
  alors que d'autres étaient en cours

### Modifié
- **Chacun voit sa propre paie** : les bulletins qui lui ont été remis, et eux
  seuls. La règle qui réservait toute la paie au gérant tenait pour les
  bulletins des autres, pas pour les siens. Les brouillons restent invisibles à
  l'intéressé, et l'écriture reste au gérant
- **Le profil d'un tiers se modifie depuis l'API**, plus seulement depuis
  l'administration Django : la direction en a besoin au quotidien. La permission
  correspondante s'appelle désormais `IsSelfOrFounder`
- **Navigation en rail latéral** : les six entrées de menu passent de la barre
  horizontale à une colonne de gauche, groupées par famille (Pilotage,
  Exécution, Direction), avec le résumé du mois et la carte utilisateur dans
  le même rail. La barre supérieure ne garde qu'un fil d'Ariane et les actions
  de session. Sous 1024 px, le rail devient un tiroir escamotable
- **Palette bleu et orange** : le bleu porte la structure et les actions,
  l'orange l'accent. Le rail et la barre du haut passent en bleu nuit — ils ne
  se confondent plus avec la zone de travail, en clair comme en sombre. Les
  dégradés en style inline des tuiles cèdent la place à quatre aplats de la
  palette
- **Monnaie** : tous les montants passent du franc CFA. Aucune décimale n'est
  affichée — le franc CFA n'a pas de subdivision — et les emplacements étroits
  (tuiles, axes de graphique, barre latérale, tableau d'équipe) montrent un
  montant abrégé, « 12,5 M FCFA » plutôt que « 12 500 000 FCFA »
- **Densité des contrôles** : champs, listes déroulantes et boutons adoptent la
  hauteur d'une application de gestion ; les filtres se rangent à gauche à leur
  largeur utile au lieu de s'étirer sur toute la ligne
- **Chargement des pages** : la vue bascule aussitôt, garnie de blocs d'attente
  le temps de la requête ; au retour sur une page déjà vue, les données
  précédentes restent affichées pendant le rafraîchissement
- **Requêtes en parallèle** : le démarrage enchaînait quatre appels (profil,
  synthèse, historique, activité), la page Tâches trois. Ceux qui ne dépendent
  pas les uns des autres partent désormais ensemble : une latence réseau au
  lieu de quatre
- **Indicateur de chargement** : un bandeau en haut de la fenêtre remplace le
  disque au centre de l'écran, que l'œil ne croisait jamais
- **Barres de défilement** : curseur fin et arrondi, piste transparente, sur
  les quatre zones qui défilent (page, résumé du rail, corps des modales,
  tableau d'équipe) ; les couleurs suivent le thème clair ou sombre
- Les montants passent de `FloatField` à `DecimalField` : un chiffre d'affaires
  ne se stocke pas en flottant
- Les jalons et les tâches maintiennent seuls la cohérence entre statut,
  avancement et date d'achèvement
- Les tâches Celery suivent le cycle métier : ouverture et clôture des mois,
  alertes de retard, rappels de rapport, report des tâches

### Supprimé
- `Category`, `Performance`, `Metric`, `Alert`, `Dashboard` et leurs endpoints
- Le moteur de seuils par unité de mesure, remplacé par la comparaison
  objectif/réalisé

### Migration
Trois migrations enchaînées :
`0002` retire les modèles d'infrastructure, `0003` crée les modèles métier,
`0004` rattache un profil aux comptes existants. **Les comptes utilisateurs et
leurs jetons ne sont pas touchés** ; seules les données métier sont remplacées.

## [1.1.0] - 2026-08-31

Version qui a rendu le projet exécutable de bout en bout.

### Ajouté
- Authentification complète : inscription, connexion, profil, déconnexion,
  changement de mot de passe
- Page de connexion (le client y redirigeait déjà, mais elle n'existait pas)
- Génération de rapports réelle, export CSV, calcul effectif des métriques
- Commande `seed_demo`, managers métier, filtres en query string

### Corrigé
- `daphne` dans `INSTALLED_APPS` sans être une dépendance : le serveur refusait
  de démarrer
- `filters.py`, `managers.py`, `signals.py` et `tasks.py` référençaient des
  champs inexistants
- Les signaux n'étaient jamais connectés
- Le frontend traitait les réponses paginées comme des tableaux

### Modifié
- Django 5.0 → 5.2, DRF 3.14 → 3.18
- Filtrage déplacé côté serveur, recherche différée

## [1.0.0] - 2024-08-31

### Ajouté
- Backend Django avec API REST, frontend SPA en JavaScript natif
- Modèles de supervision d'infrastructure
- Support Docker, configuration Nginx et Gunicorn

## Feuille de route

### Prochaine étape
- [ ] Modification du rôle d'un membre depuis l'interface (aujourd'hui via
      l'administration Django)
- [ ] Pagination visible dans l'interface (le client agrège les pages)
- [ ] Commentaires d'un fondateur sur un rapport soumis
- [ ] Export PDF des rapports

### Plus tard
- [ ] Objectifs d'équipe, en complément des objectifs individuels
- [ ] Historique des révisions d'un objectif
- [ ] Notifications temps réel
- [ ] Journal d'audit
- [ ] Multi-tenant

## Problèmes connus

- L'interface charge jusqu'à 20 pages d'une collection (200 éléments) avant de
  s'arrêter : au-delà, utilisez les filtres
- Les dates ISO passées en query string doivent avoir leur `+` encodé en `%2B`
- Un fondateur consulte les données de l'équipe mais ne peut pas les modifier
  depuis l'API : cela passe par l'administration Django

## Sécurité

- Ne versionnez jamais le fichier `.env` réel
- Changez `SECRET_KEY` avant toute mise en production
- Le cloisonnement entre membres est appliqué côté serveur : ne le contournez
  pas en ajoutant des endpoints non filtrés par `visible_to()`
