"""
Mise en forme des montants côté serveur.

L'interface formate ses montants elle-même ; ce module sert aux sorties qui ne
passent pas par elle : l'administration Django et les courriels d'alerte.
"""


def format_fcfa(amount):
    """Formate un montant en francs CFA : « 1 435 983 FCFA ».

    Le franc CFA n'a pas de subdivision : le montant est arrondi au franc et
    les milliers sont séparés par une espace, comme le veut l'usage français.
    """
    if amount is None:
        return '—'
    return f"{amount:,.0f}".replace(',', ' ') + ' FCFA'
