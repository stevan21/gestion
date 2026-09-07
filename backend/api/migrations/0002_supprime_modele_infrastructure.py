"""
Retrait du modèle de supervision d'infrastructure.

Le produit suit la performance d'une équipe de startup, pas des serveurs :
Category, Performance, Metric, Alert, Report et Dashboard décrivaient un tout
autre domaine et sont supprimés au profit des modèles métier créés dans la
migration suivante.

Les comptes utilisateurs et leurs jetons ne sont pas touchés.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
    ]

    operations = [
        # L'ordre suit les dépendances : les modèles qui pointent vers un autre
        # partent en premier, sinon la contrainte de clé étrangère bloque.
        migrations.DeleteModel(name='Metric'),
        migrations.DeleteModel(name='Alert'),
        migrations.DeleteModel(name='Report'),
        migrations.DeleteModel(name='Dashboard'),
        migrations.DeleteModel(name='Performance'),
        migrations.DeleteModel(name='Category'),
    ]
