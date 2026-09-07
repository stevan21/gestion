"""
Configuration Celery de Flux Gestion.

Le planificateur ne connaît que des tâches qui existent : chaque entrée du
calendrier ci-dessous pointe vers une fonction de `api.tasks`, et toutes les
tâches périodiques du projet y figurent.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fluxgestion.settings')

app = Celery('fluxgestion')

# La configuration vient des settings Django, préfixe CELERY_.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Découverte automatique des tâches des applications installées.
app.autodiscover_tasks()

# Calendrier des tâches périodiques. Les heures sont locales : `CELERY_TIMEZONE`
# suit `TIME_ZONE`. Des horaires fixes valent mieux qu'un intervalle en
# secondes — un rappel de rapport doit tomber le lundi matin, pas « toutes les
# 604 800 secondes » à partir du démarrage du worker.
app.conf.beat_schedule = {
    # Le mois écoulé se clôt avant que le suivant s'ouvre : l'ordre compte,
    # les objectifs reconduits partent du mois précédent.
    'close-previous-month': {
        'task': 'api.tasks.close_previous_month',
        'schedule': crontab(day_of_month='1', hour=0, minute=5),
    },
    'open-monthly-objectives': {
        'task': 'api.tasks.open_monthly_objectives',
        'schedule': crontab(day_of_month='1', hour=0, minute=10),
    },
    # Les tâches en retard sont reportées avant l'arrivée de l'équipe.
    'carry-over-late-tasks': {
        'task': 'api.tasks.carry_over_late_tasks',
        'schedule': crontab(hour=6, minute=0),
    },
    # Un départ oublié la veille est refermé sur l'heure de fin prévue.
    'close-stale-attendance': {
        'task': 'api.tasks.close_stale_attendance',
        'schedule': crontab(hour=3, minute=0),
    },
    # L'alerte de retard part en semaine, en début de matinée.
    'notify-objectives-at-risk': {
        'task': 'api.tasks.notify_objectives_at_risk',
        'schedule': crontab(day_of_week='mon-fri', hour=8, minute=30),
    },
    'remind-weekly-reports': {
        'task': 'api.tasks.remind_missing_reports',
        'schedule': crontab(day_of_week='mon', hour=9, minute=0),
        'kwargs': {'period_type': 'weekly'},
    },
    'remind-monthly-reports': {
        'task': 'api.tasks.remind_missing_reports',
        'schedule': crontab(day_of_month='3', hour=9, minute=0),
        'kwargs': {'period_type': 'monthly'},
    },
    'cleanup-old-data': {
        'task': 'api.tasks.cleanup_old_data',
        'schedule': crontab(day_of_week='sun', hour=4, minute=0),
    },
}


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
