"""Le bulletin de paie perd son brouillon et gagne les heures travaillées.

Un bulletin enregistré est désormais établi : il n'y a plus d'état à faire
passer de « brouillon » à « émis ». Les brouillons existants deviennent donc
des bulletins établis, horodatés à leur création faute de mieux.
"""

from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def horodate_les_brouillons(apps, schema_editor):
    """Un bulletin sans date d'établissement prend celle de sa création."""
    Payslip = apps.get_model('api', 'Payslip')
    for bulletin in Payslip.objects.filter(issued_at__isnull=True).iterator():
        bulletin.issued_at = bulletin.created_at
        bulletin.save(update_fields=['issued_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_salaire_de_base_et_reactions'),
    ]

    operations = [
        migrations.AddField(
            model_name='payslip',
            name='worked_hours',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'),
                help_text='Heures effectuées dans le mois, hors heures supplémentaires',
                max_digits=7,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                verbose_name='Heures travaillées',
            ),
        ),
        migrations.RunPython(horodate_les_brouillons, migrations.RunPython.noop),
        migrations.RemoveField(model_name='payslip', name='status'),
        migrations.AlterField(
            model_name='payslip',
            name='issued_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Établi le'),
        ),
    ]
