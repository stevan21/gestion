"""Projet Flux Gestion.

L'import de l'application Celery ici garantit que le décorateur @shared_task
la trouve au démarrage de Django.
"""

from .celery import app as celery_app

__all__ = ('celery_app',)
