"""
Crée un compte de gérant, ou promeut un compte existant.

Le rôle de gérant ouvre la paie et le suivi du personnel, en plus de tout ce
que voit un fondateur. Il ne s'attribue pas depuis l'API : cette commande et
l'administration Django sont les deux seules portes d'entrée.

    python manage.py create_manager nadia
    python manage.py create_manager nadia --password 'MotDePasseSolide!42'
    python manage.py create_manager karim --promote
"""

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.credentials import generate_password
from api.models import Member


class Command(BaseCommand):
    help = "Crée un compte de gérant, ou promeut un compte existant."

    def add_arguments(self, parser):
        parser.add_argument('username', help="Identifiant de connexion")
        parser.add_argument(
            '--password',
            help="Mot de passe ; engendré et affiché une fois s'il est omis",
        )
        parser.add_argument('--email', default='', help="Adresse électronique")
        parser.add_argument('--first-name', default='', help="Prénom")
        parser.add_argument('--last-name', default='', help="Nom")
        # Sans valeur par défaut : une promotion ne doit pas déplacer
        # quelqu'un de son pôle ni effacer son poste au passage.
        parser.add_argument(
            '--job-title', help="Poste affiché dans l'équipe (défaut : Gérant)",
        )
        parser.add_argument(
            '--department',
            choices=[code for code, _ in Member.DEPARTMENT_CHOICES],
            help="Pôle de rattachement (défaut : direction)",
        )
        parser.add_argument(
            '--promote', action='store_true',
            help="Autorise la promotion d'un compte qui existe déjà",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options['username'].strip()
        if not username:
            raise CommandError("L'identifiant ne peut pas être vide.")

        user = User.objects.filter(username=username).first()
        if user and not options['promote'] and not options['password']:
            raise CommandError(
                f"Le compte « {username} » existe déjà. Relancez avec --promote "
                f"pour le passer gérant sans toucher à son mot de passe."
            )

        password = options['password'] or (None if user else generate_password())
        if password:
            self._check_password(password, username)

        created = user is None
        if created:
            user = User.objects.create_user(
                username=username,
                email=options['email'],
                password=password,
                first_name=options['first_name'],
                last_name=options['last_name'],
            )
        else:
            # Les champs vides ne remplacent pas une identité déjà renseignée.
            for champ, valeur in (('email', options['email']),
                                  ('first_name', options['first_name']),
                                  ('last_name', options['last_name'])):
                if valeur:
                    setattr(user, champ, valeur)
            if password:
                user.set_password(password)
            user.save()

        # Le signal a posé un profil à la création du compte : on l'ajuste.
        member = Member.objects.for_user(user)
        member.role = 'manager'
        member.job_title = options['job_title'] or (
            member.job_title if not created else 'Gérant'
        )
        member.department = options['department'] or (
            member.department if not created else 'direction'
        )
        member.save(update_fields=['role', 'job_title', 'department', 'updated_at'])

        verbe = 'créé' if created else 'promu'
        self.stdout.write(self.style.SUCCESS(
            f"Gérant {verbe} : {member.display_name} ({username})"
        ))
        self.stdout.write(
            f"  Pôle    : {member.get_department_display()}\n"
            f"  Poste   : {member.job_title}\n"
            f"  Accès   : équipe complète, bulletins de paie, suivi du personnel"
        )

        if options['password']:
            self.stdout.write("  Mot de passe : celui que vous avez fourni")
        elif created:
            self.stdout.write(self.style.WARNING(
                f"  Mot de passe : {password}"
            ))
            self.stdout.write(
                "  Notez-le : il ne sera plus affiché. Changez-le à la première "
                "connexion."
            )
        else:
            self.stdout.write("  Mot de passe : inchangé")

    def _check_password(self, password, username):
        """Applique les règles de robustesse du projet."""
        try:
            validate_password(password, User(username=username))
        except ValidationError as erreur:
            raise CommandError(
                "Mot de passe refusé : " + ' '.join(erreur.messages)
            ) from erreur
