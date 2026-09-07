"""
Amorçage Django pour pytest.

Les tests officiels du projet passent par `python manage.py test api`.
Ce fichier permet en plus de les lancer avec pytest si l'outil est installé.
"""

import os

import django


def pytest_configure():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fluxgestion.settings')
    django.setup()
