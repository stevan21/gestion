"""
Rattache un profil métier aux comptes créés avant le pivot.

Le signal `create_member_profile` ne se déclenche qu'à la création d'un compte :
sans cette reprise, les utilisateurs existants n'auraient aucun profil et se
verraient refuser l'accès à l'API.
"""

from django.db import migrations


def create_missing_profiles(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Member = apps.get_model('api', 'Member')

    existing = set(Member.objects.values_list('user_id', flat=True))
    orphans = User.objects.exclude(id__in=existing).order_by('date_joined', 'id')

    for index, user in enumerate(orphans):
        # Le compte le plus ancien devient fondateur, faute de quoi personne
        # ne pourrait consulter l'équipe après la migration.
        is_founder = user.is_superuser or (index == 0 and not existing)
        Member.objects.create(
            user=user,
            role='founder' if is_founder else 'member',
            department='direction' if is_founder else 'commercial',
            job_title='Fondateur' if is_founder else '',
            joined_on=user.date_joined.date(),
        )


def remove_profiles(apps, schema_editor):
    # Retour arrière : les profils sont recréés au besoin par le signal.
    apps.get_model('api', 'Member').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_modele_suivi_equipe'),
    ]

    operations = [
        migrations.RunPython(create_missing_profiles, remove_profiles),
    ]
