# Migrations
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import django.core.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('color', models.CharField(default='#3498db', max_length=7)),
                ('icon', models.CharField(blank=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'Categories',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Performance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, null=True)),
                ('value', models.FloatField(validators=[django.core.validators.MinValueValidator(0)])),
                ('unit', models.CharField(choices=[('ms', 'Millisecondes'), ('s', 'Secondes'), ('%', 'Pourcentage'), ('mb', 'Mégabytes'), ('kb', 'Kilobytes'), ('req/s', 'Requêtes par seconde'), ('ops/s', 'Opérations par seconde'), ('custom', 'Unité personnalisée')], default='ms', max_length=20)),
                ('target_value', models.FloatField(blank=True, null=True)),
                ('status', models.CharField(choices=[('excellent', 'Excellent'), ('good', 'Bon'), ('average', 'Moyen'), ('poor', 'Faible'), ('critical', 'Critique')], default='average', max_length=20)),
                ('tags', models.CharField(blank=True, max_length=500)),
                ('notes', models.TextField(blank=True, null=True)),
                ('source', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('recorded_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='performances', to='api.category')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='performances_created', to='auth.user')),
            ],
            options={
                'ordering': ['-recorded_at'],
            },
        ),
        migrations.CreateModel(
            name='Metric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('average_value', models.FloatField(default=0)),
                ('min_value', models.FloatField(default=0)),
                ('max_value', models.FloatField(default=0)),
                ('std_deviation', models.FloatField(default=0)),
                ('trend', models.CharField(default='stable', max_length=20)),
                ('trend_percentage', models.FloatField(default=0)),
                ('total_measurements', models.IntegerField(default=0)),
                ('success_count', models.IntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('performance', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='metric', to='api.performance')),
            ],
        ),
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('start_date', models.DateTimeField()),
                ('end_date', models.DateTimeField()),
                ('include_metrics', models.BooleanField(default=True)),
                ('include_alerts', models.BooleanField(default=True)),
                ('include_charts', models.BooleanField(default=True)),
                ('format', models.CharField(choices=[('pdf', 'PDF'), ('excel', 'Excel'), ('json', 'JSON'), ('csv', 'CSV')], default='pdf', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('file_url', models.URLField(blank=True)),
                ('categories', models.ManyToManyField(to='api.category')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Dashboard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('layout', models.CharField(default='grid', max_length=20)),
                ('items_per_row', models.IntegerField(default=3)),
                ('is_public', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('categories', models.ManyToManyField(to='api.category')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dashboards', to='auth.user')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='Alert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('severity', models.CharField(choices=[('low', 'Faible'), ('medium', 'Moyen'), ('high', 'Élevé'), ('critical', 'Critique')], default='medium', max_length=20)),
                ('status', models.CharField(choices=[('active', 'Active'), ('resolved', 'Résolue'), ('acknowledged', 'Reconnue')], default='active', max_length=20)),
                ('threshold_value', models.FloatField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
                ('performance', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alerts', to='api.performance')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='performance',
            index=models.Index(fields=['category', '-recorded_at'], name='api_perform_categor_idx'),
        ),
        migrations.AddIndex(
            model_name='performance',
            index=models.Index(fields=['status'], name='api_perform_status_idx'),
        ),
        migrations.AddIndex(
            model_name='performance',
            index=models.Index(fields=['recorded_at'], name='api_perform_record_idx'),
        ),
    ]
