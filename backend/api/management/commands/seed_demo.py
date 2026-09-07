"""
Jeu de données de démonstration : une équipe de startup sur plusieurs mois.

Usage :
    python manage.py seed_demo
    python manage.py seed_demo --months 6 --reset
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.managers import month_range, month_start
from api.models import (
    Attendance, DailyTask, LeaveRequest, Member, MonthlyObjective, Payslip,
    Report, RoadmapItem, StaffEvent,
)

MOT_DE_PASSE = 'demo1234'

EQUIPE = [
    {
        'username': 'awa', 'first_name': 'Awa', 'last_name': 'Diallo',
        'role': 'founder', 'department': 'direction', 'job_title': 'CEO',
        'revenue': (18000000, 28000000), 'clients': (8, 14),
    },
    {
        'username': 'karim', 'first_name': 'Karim', 'last_name': 'Benali',
        'role': 'member', 'department': 'commercial',
        'job_title': 'Responsable commercial',
        'revenue': (12000000, 20000000), 'clients': (6, 12),
    },
    {
        'username': 'lea', 'first_name': 'Léa', 'last_name': 'Moreau',
        'role': 'member', 'department': 'marketing',
        'job_title': "Chargée d'acquisition",
        'revenue': (4000000, 8000000), 'clients': (10, 20),
    },
    {
        'username': 'thomas', 'first_name': 'Thomas', 'last_name': 'Nguyen',
        'role': 'member', 'department': 'produit', 'job_title': 'Product Manager',
        'revenue': (0, 0), 'clients': (2, 5),
    },
    {
        'username': 'sofia', 'first_name': 'Sofia', 'last_name': 'Rossi',
        'role': 'member', 'department': 'commercial', 'job_title': 'Business Developer',
        'revenue': (8000000, 15000000), 'clients': (5, 10),
    },
    {
        'username': 'nadia', 'first_name': 'Nadia', 'last_name': 'Belkacem',
        'role': 'manager', 'department': 'direction', 'job_title': 'Gérante',
        'revenue': (0, 0), 'clients': (0, 0),
    },
]

#: Salaire de base mensuel par pôle, en francs CFA.
SALAIRES = {
    'direction': 800000,
    'commercial': 450000,
    'marketing': 400000,
    'produit': 550000,
    'technique': 600000,
    'finance': 500000,
    'operations': 420000,
}

FOCUS = {
    'direction': [
        "Boucler la levée d'amorçage",
        "Structurer le comité de direction",
        "Signer deux partenariats grands comptes",
    ],
    'commercial': [
        "Ouvrir le segment PME industrielles",
        "Réactiver le portefeuille dormant",
        "Passer le panier moyen au-dessus de 1 300 000 FCFA",
    ],
    'marketing': [
        "Diviser par deux le coût par lead",
        "Lancer la campagne LinkedIn Q4",
        "Publier trois études de cas clients",
    ],
    'produit': [
        "Livrer le module de facturation",
        "Réduire le délai d'onboarding à 3 jours",
        "Cadrer la V2 de l'application mobile",
    ],
}

JALONS = {
    'direction': [
        "Préparer le deck investisseurs", "Rencontrer 5 fonds",
        "Finaliser le prévisionnel 3 ans", "Recruter un profil senior",
    ],
    'commercial': [
        "Constituer une liste de 100 prospects", "Lancer la séquence de prospection",
        "Tenir 20 rendez-vous de découverte", "Relancer les devis en attente",
        "Négocier les renouvellements",
    ],
    'marketing': [
        "Refondre la page d'accueil", "Produire 4 articles de blog",
        "Mettre en place le suivi des conversions", "Lancer le test A/B des annonces",
    ],
    'produit': [
        "Rédiger les spécifications", "Livrer la maquette validée",
        "Recette avec 3 clients pilotes", "Documenter le module",
    ],
}

TACHES = {
    'direction': [
        "Point hebdo avec l'équipe", "Relire le pacte d'associés",
        "Appel investisseur", "Valider le budget du mois",
        "Entretien de recrutement",
    ],
    'commercial': [
        "Relancer 10 prospects par email", "Rendez-vous client à 14 h",
        "Préparer la proposition commerciale", "Mettre à jour le pipeline",
        "Appel de qualification", "Envoyer les devis en attente",
    ],
    'marketing': [
        "Rédiger la newsletter", "Analyser les performances des annonces",
        "Programmer les publications de la semaine",
        "Interviewer un client pour une étude de cas",
        "Ajuster le ciblage des campagnes",
    ],
    'produit': [
        "Affiner les tickets du sprint", "Point avec les développeurs",
        "Tester le parcours d'inscription", "Recueillir les retours utilisateurs",
        "Mettre à jour la roadmap produit",
    ],
}


class Command(BaseCommand):
    help = "Crée une équipe de démonstration avec objectifs, feuille de route, tâches et rapports."

    def add_arguments(self, parser):
        parser.add_argument('--months', type=int, default=6,
                            help="Nombre de mois d'historique (défaut : 6)")
        parser.add_argument('--task-days', type=int, default=21,
                            help='Profondeur des tâches quotidiennes (défaut : 21)')
        parser.add_argument('--reset', action='store_true',
                            help='Supprime les données de démonstration existantes')

    @transaction.atomic
    def handle(self, *args, **options):
        months = max(1, options['months'])
        task_days = max(1, options['task_days'])
        random.seed(7)  # Jeu reproductible d'une exécution à l'autre.

        if options['reset']:
            # Les comptes ne sont pas touchés : seules leurs données métier partent.
            Attendance.objects.all().delete()
            LeaveRequest.objects.all().delete()
            DailyTask.objects.all().delete()
            Report.objects.all().delete()
            RoadmapItem.objects.all().delete()
            MonthlyObjective.objects.all().delete()
            self.stdout.write(self.style.WARNING('Données métier existantes supprimées'))

        members = [self._ensure_member(spec) for spec in EQUIPE]

        objectives = 0
        milestones = 0
        for member, spec in zip(members, EQUIPE):
            for offset in range(months - 1, -1, -1):
                objective = self._create_objective(member, spec, offset)
                if objective is None:
                    continue
                objectives += 1
                # La feuille de route n'est détaillée que sur les mois récents.
                if offset <= 1:
                    milestones += self._create_roadmap(objective, spec, offset)

        tasks = sum(self._create_tasks(member, spec, task_days)
                    for member, spec in zip(members, EQUIPE))
        reports = sum(self._create_reports(member) for member in members)
        payslips = self._create_payroll(members)
        events = self._create_staff_events(members)
        # Les congés d'abord : le pointage saute les journées qu'ils couvrent.
        leaves = self._create_leaves(members)
        attendance = self._create_attendance(members, task_days)

        self.stdout.write(self.style.SUCCESS(
            f"{len(members)} membres, {objectives} objectifs mensuels, "
            f"{milestones} jalons, {tasks} tâches, {reports} rapports, "
            f"{payslips} bulletins de paie, {events} évènements de personnel, "
            f"{leaves} demandes de congé et {attendance} pointages générés."
        ))
        self.stdout.write(
            f"Connexion : awa / {MOT_DE_PASSE} (fondatrice, voit toute l'équipe)\n"
            f"            nadia / {MOT_DE_PASSE} (gérante, + paie et personnel)\n"
            f"            karim / {MOT_DE_PASSE} (membre, ne voit que ses données)"
        )

    def _create_payroll(self, members):
        """Un bulletin par membre pour le mois courant et le précédent."""
        created = 0
        for offset in (1, 0):
            month, _ = month_range(months_back=offset)
            for member in members:
                if Payslip.objects.filter(member=member, month=month).exists():
                    continue

                base = Decimal(SALAIRES.get(member.department, 420000))
                # 173,33 heures mensuelles pour un mois plein ; quelques
                # absences font varier le décompte d'un salarié à l'autre.
                travaillees = Decimal(random.choice([173, 168, 160, 173]))
                heures = Decimal(random.choice([0, 0, 2, 4, 6]))
                # Une heure supplémentaire est majorée de 25 %, sur une base de
                # 173,33 heures mensuelles (semaine légale de 40 heures).
                taux = (base / Decimal('173.33') * Decimal('1.25'))

                Payslip.objects.create(
                    member=member,
                    month=month,
                    base_salary=base,
                    worked_hours=travaillees,
                    overtime_hours=heures,
                    # Le franc CFA n'a pas de subdivision : tout est arrondi
                    # au franc entier.
                    overtime_amount=(heures * taux).quantize(Decimal('1')),
                    bonuses=Decimal(random.choice([0, 0, 25000, 50000])),
                    deductions=Decimal(random.choice([0, 0, 0, 15000])),
                    contributions=(base * Decimal('0.22')).quantize(Decimal('1')),
                )
                created += 1
        return created

    def _create_staff_events(self, members):
        """Quelques évènements de personnel sur le mois écoulé."""
        today = timezone.localdate()
        salaries = [m for m in members if m.role == 'member']
        gerante = next((m for m in members if m.role == 'manager'), None)
        if not salaries:
            return 0

        # Les évènements restent dans le mois courant : la page du gérant
        # l'affiche mois par mois, un jeu daté du mois précédent paraîtrait vide.
        debut = month_start(today)

        def jour(recul):
            return max(today - timedelta(days=recul), debut)

        modeles = [
            {
                'kind': 'lateness', 'date': jour(9), 'minutes': 35,
                'reason': "Arrivée à 9 h 35 sans avoir prévenu l'équipe.",
                'decision': 'Rappel oral des horaires.',
            },
            {
                'kind': 'observation', 'date': jour(6),
                'reason': "Comptes rendus de visite non transmis deux semaines "
                          "de suite, malgré une relance.",
                'decision': 'Rappel des règles, point de contrôle sous quinze jours.',
            },
            {
                'kind': 'overtime', 'date': jour(3),
                'hours': Decimal('4.50'), 'is_paid': True,
                'reason': 'Préparation du salon professionnel, samedi compris.',
                'decision': 'Heures payées sur le bulletin du mois.',
            },
            {
                'kind': 'suspension', 'date': jour(20),
                'end_date': min(jour(20) + timedelta(days=2), today),
                'reason': 'Absence injustifiée de trois jours consécutifs.',
                'decision': 'Mise à pied disciplinaire sans solde, notifiée par courrier.',
            },
        ]

        created = 0
        for index, modele in enumerate(modeles):
            member = salaries[index % len(salaries)]
            if StaffEvent.objects.filter(
                member=member, kind=modele['kind'], date=modele['date']
            ).exists():
                continue
            StaffEvent.objects.create(member=member, recorded_by=gerante, **modele)
            created += 1
        return created

    def _create_leaves(self, members):
        """Quelques demandes de congé : accordées, en attente, refusée."""
        today = timezone.localdate()
        salaries = [m for m in members if m.role == 'member']
        direction = next((m for m in members if m.role == 'founder'), None)
        if not salaries:
            return 0

        def lundi(recul_semaines):
            """Lundi d'une semaine passée ou à venir, selon le signe."""
            lundi_courant = today - timedelta(days=today.weekday())
            return lundi_courant - timedelta(weeks=recul_semaines)

        modeles = [
            # Un congé en cours : le panel montre le membre absent, et la
            # synthèse de présence ne le compte pas comme absent sans motif.
            {
                'kind': 'paid', 'status': 'approved',
                'start_date': lundi(0), 'end_date': lundi(0) + timedelta(days=4),
                'reason': 'Congé annuel, une semaine en famille.',
                'decision': 'Accordé, relais assuré par le pôle.',
            },
            {
                'kind': 'paid', 'status': 'approved',
                'start_date': lundi(5), 'end_date': lundi(5) + timedelta(days=2),
                'reason': 'Congé annuel, trois jours.',
                'decision': 'Accordé.',
            },
            {
                'kind': 'sick', 'status': 'approved',
                'start_date': lundi(3) + timedelta(days=1),
                'end_date': lundi(3) + timedelta(days=2),
                'reason': 'Arrêt maladie, certificat transmis.',
                'decision': 'Reçu, bon rétablissement.',
            },
            {
                'kind': 'paid', 'status': 'pending',
                'start_date': lundi(-3), 'end_date': lundi(-3) + timedelta(days=4),
                'reason': 'Congé annuel, déplacement prévu de longue date.',
            },
            {
                'kind': 'special', 'status': 'pending',
                'start_date': lundi(-1) + timedelta(days=2),
                'end_date': lundi(-1) + timedelta(days=2),
                'half_day': True,
                'reason': 'Rendez-vous administratif, une demi-journée.',
            },
            {
                'kind': 'unpaid', 'status': 'refused',
                'start_date': lundi(2), 'end_date': lundi(2) + timedelta(days=9),
                'reason': 'Congé sans solde de deux semaines.',
                'decision': 'Refusé : période de clôture commerciale.',
            },
        ]

        created = 0
        for index, modele in enumerate(modeles):
            member = salaries[index % len(salaries)]
            if LeaveRequest.objects.filter(
                member=member, start_date=modele['start_date']
            ).exists():
                continue

            decide = modele['status'] != 'pending'
            LeaveRequest.objects.create(
                member=member,
                decided_by=direction if decide else None,
                decided_at=timezone.now() if decide else None,
                **modele,
            )
            created += 1
        return created

    def _create_attendance(self, members, days):
        """Pointages des dernières semaines, jours ouvrés seulement.

        Les congés accordés sont sautés : une journée couverte par un congé
        n'a pas à être pointée, et la compter en absence serait faux.
        """
        today = timezone.localdate()
        created = 0

        conges = {}
        for demande in LeaveRequest.objects.approved().select_related('member'):
            conges.setdefault(demande.member_id, []).append(demande)

        for member in members:
            for recul in range(days):
                jour = today - timedelta(days=recul)
                if jour.weekday() >= 5:
                    continue
                if any(demande.covers(jour) for demande in conges.get(member.pk, [])):
                    continue
                # Une journée manquée de temps en temps : le suivi de présence
                # n'aurait rien à montrer si tout le monde pointait toujours.
                if random.random() < 0.06:
                    continue
                if Attendance.objects.filter(member=member, date=jour).exists():
                    continue

                depart_prevu = member.work_starts_at
                minutes = random.choices(
                    [-10, -5, 0, 5, 12, 25, 45],
                    weights=[15, 20, 25, 15, 10, 10, 5],
                )[0]
                arrivee = timezone.make_aware(datetime.combine(
                    jour, depart_prevu
                )) + timedelta(minutes=minutes)

                pointage = Attendance.objects.create(member=member, date=jour,
                                                     check_in=arrivee)
                # La journée du jour reste ouverte pour une partie de l'équipe :
                # c'est ce que le panel de la direction montre en direct.
                if recul == 0 and random.random() < 0.5:
                    created += 1
                    continue

                pointage.close(arrivee + timedelta(
                    minutes=random.choice([450, 480, 500, 510, 540])
                ))
                created += 1
        return created

    def _ensure_member(self, spec):
        """Crée le compte et aligne son profil métier sur la fiche d'équipe."""
        user, created = User.objects.get_or_create(
            username=spec['username'],
            defaults={
                'first_name': spec['first_name'],
                'last_name': spec['last_name'],
                'email': f"{spec['username']}@fluxgestion.local",
            },
        )
        if created:
            user.set_password(MOT_DE_PASSE)
            user.save()

        # Le signal a déjà posé un profil : on le complète.
        member = Member.objects.for_user(user)
        member.role = spec['role']
        member.department = spec['department']
        member.job_title = spec['job_title']
        member.joined_on = timezone.localdate() - timedelta(days=random.randint(120, 900))
        member.save()
        return member

    def _create_objective(self, member, spec, months_back):
        """Objectifs d'un mois, avec un réalisé plausible."""
        month, _ = month_range(months_back=months_back)
        if MonthlyObjective.objects.filter(member=member, month=month).exists():
            return None

        low, high = spec['revenue']
        revenue_target = Decimal(random.randrange(low, high + 1, 500)) if high else Decimal('0')
        clients_target = random.randint(*spec['clients'])

        if months_back == 0:
            # Mois en cours : le réalisé suit la portion de mois écoulée,
            # avec un écart aléatoire qui rend certains membres en retard.
            today = timezone.localdate()
            elapsed = today.day / 30
            ratio = elapsed * random.uniform(0.55, 1.25)
            status = 'active'
        else:
            ratio = random.uniform(0.72, 1.22)
            status = 'closed'

        return MonthlyObjective.objects.create(
            member=member,
            month=month,
            revenue_target=revenue_target,
            revenue_achieved=(revenue_target * Decimal(str(round(ratio, 3)))).quantize(Decimal('0.01')),
            clients_target=clients_target,
            clients_achieved=max(0, round(clients_target * ratio)),
            focus=random.choice(FOCUS[spec['department']]),
            status=status,
            notes='' if months_back else "Mise à jour hebdomadaire des chiffres.",
        )

    def _create_roadmap(self, objective, spec, months_back):
        """Jalons du mois, avec un avancement cohérent avec leur statut."""
        titles = random.sample(JALONS[spec['department']],
                               k=min(4, len(JALONS[spec['department']])))
        created = 0
        for position, title in enumerate(titles):
            if months_back > 0:
                status = 'done' if random.random() < 0.8 else 'blocked'
            else:
                status = random.choices(
                    ['done', 'in_progress', 'todo', 'blocked'],
                    weights=[3, 3, 3, 1],
                )[0]

            progress = {'done': 100, 'in_progress': random.randint(30, 80),
                        'todo': 0, 'blocked': random.randint(10, 50)}[status]

            RoadmapItem.objects.create(
                objective=objective,
                title=title,
                description='',
                due_date=objective.month + timedelta(days=7 * (position + 1)),
                status=status,
                progress=progress,
                position=position,
            )
            created += 1
        return created

    def _create_tasks(self, member, spec, days):
        """Tâches quotidiennes des derniers jours ouvrés."""
        catalogue = TACHES[spec['department']]
        milestones = list(RoadmapItem.objects.filter(
            objective__member=member, objective__month=month_start()
        ))
        today = timezone.localdate()
        created = 0

        for offset in range(days):
            day = today - timedelta(days=offset)
            if day.weekday() >= 5:  # Ni samedi ni dimanche.
                continue

            for title in random.sample(catalogue, k=random.randint(2, 4)):
                if offset == 0:
                    status = random.choices(['todo', 'in_progress', 'done'],
                                            weights=[4, 2, 3])[0]
                else:
                    status = random.choices(['done', 'blocked'], weights=[9, 1])[0]

                DailyTask.objects.create(
                    member=member,
                    date=day,
                    title=title,
                    status=status,
                    priority=random.choices([1, 2, 3, 4], weights=[2, 5, 3, 1])[0],
                    roadmap_item=(random.choice(milestones)
                                  if milestones and random.random() < 0.4 else None),
                    estimated_minutes=random.choice([15, 30, 45, 60, 90, 120]),
                )
                created += 1
        return created

    def _create_reports(self, member):
        """Rapport de la semaine en cours, puis les trois semaines précédentes."""
        today = timezone.localdate()
        monday = today - timedelta(days=today.weekday())
        created = 0

        # La semaine en cours reste un brouillon : c'est l'état normal en
        # milieu de semaine, et elle chevauche le mois affiché.
        periods = [(monday, today, False)]
        for week in range(1, 4):
            end = monday - timedelta(days=7 * (week - 1) + 1)
            periods.append((end - timedelta(days=6), end, True))

        for start, end, always_submitted in periods:
            if Report.objects.filter(member=member, period_start=start).exists():
                continue

            submitted = always_submitted or random.random() < 0.5
            Report.objects.create(
                member=member,
                period_type='weekly',
                period_start=start,
                period_end=end,
                summary=(
                    f"Semaine du {start:%d/%m} au {end:%d/%m} : avancement conforme "
                    f"sur les priorités du mois, deux sujets restent à débloquer."
                ),
                achievements="Rendez-vous tenus, jalons de la semaine livrés.",
                blockers="Attente de retours clients sur deux propositions.",
                next_steps="Relancer les dossiers en attente et préparer la revue mensuelle.",
                status='submitted' if submitted else 'draft',
                submitted_at=timezone.now() if submitted else None,
            )
            created += 1

        created += self._seed_event_reports(member, today)
        return created

    def _seed_event_reports(self, member, today):
        """Un rapport de mission et un rapport de réunion, pour l'exemple."""
        created = 0
        modeles = [
            {
                'period_type': 'mission',
                'title': 'Mission de cadrage chez Aurore Industries',
                'location': 'Lyon, siège du client',
                'participants': (
                    f"{member.display_name}, Sophie Aubert (direction achats), "
                    "Marc Lenoir (production)"
                ),
                'summary': (
                    "Deux jours sur site pour cadrer le déploiement : besoins "
                    "recueillis auprès des trois services concernés, contraintes "
                    "de calendrier validées avec la production."
                ),
                'achievements': (
                    "Périmètre arrêté, interlocuteurs identifiés, accès aux "
                    "données de production obtenus."
                ),
                'blockers': "Le budget définitif dépend d'un arbitrage prévu fin de mois.",
                'next_steps': "Envoyer la proposition chiffrée sous huit jours.",
                'start': today - timedelta(days=9),
                'end': today - timedelta(days=8),
            },
            {
                'period_type': 'meeting',
                'title': 'Comité commercial hebdomadaire',
                'location': 'Salle Horizon',
                'participants': f"{member.display_name}, la direction, le pôle marketing",
                'summary': (
                    "Revue du portefeuille en cours et arbitrage des priorités "
                    "pour la fin du mois."
                ),
                'decisions': (
                    "Priorité donnée au compte Aurore ; relance des devis de plus "
                    "de trois semaines confiée au pôle commercial."
                ),
                'next_steps': "Point de contrôle lundi prochain.",
                'start': today - timedelta(days=3),
                'end': today - timedelta(days=3),
            },
        ]

        for modele in modeles:
            start = modele.pop('start')
            end = modele.pop('end')
            if Report.objects.filter(member=member, title=modele['title']).exists():
                continue
            Report.objects.create(
                member=member, period_start=start, period_end=end,
                status='submitted', submitted_at=timezone.now(), **modele,
            )
            created += 1
        return created
