"""
Fabrique de mots de passe pour les comptes créés par l'administration.

Un mot de passe engendré ici n'est affiché qu'une fois, à la personne qui crée
le compte : il est fait pour être transmis puis changé, pas pour être retenu.
"""

from django.utils.crypto import get_random_string

#: Sans les caractères qui se confondent à la lecture ou à la dictée :
#: I, l et 1, O et 0. Un mot de passe se recopie souvent à la main.
ALPHABET = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789@#%+='

#: Assez long pour rester solide malgré un alphabet réduit.
LONGUEUR = 14


def generate_password(length=LONGUEUR):
    """Engendre un mot de passe aléatoire, lisible et transmissible."""
    return get_random_string(length, ALPHABET)
