"""Exécuteur de tests : un hachage rapide, pour la seule durée de la suite."""

from django.conf import settings
from django.test.runner import DiscoverRunner


class FastPasswordRunner(DiscoverRunner):
    """Remplace le hachage des mots de passe pendant les tests.

    La suite crée plusieurs centaines de comptes, et PBKDF2 — un million
    d'itérations, comme Django le règle par défaut — coûte quelques secondes
    par mot de passe sur une machine ordinaire. Le hachage occupait ainsi la
    quasi-totalité du temps d'exécution, au point qu'on hésitait à lancer la
    suite ; une suite qu'on ne lance plus ne protège plus de rien.

    Rien de ce qui est vérifié ne dépend de l'algorithme : les tests demandent
    qu'un mot de passe juste ouvre la session et qu'un mot de passe faux la
    refuse. Le réglage de production n'est pas touché — la substitution ne
    vaut que le temps des tests.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        settings.PASSWORD_HASHERS = [
            'django.contrib.auth.hashers.MD5PasswordHasher',
        ]
