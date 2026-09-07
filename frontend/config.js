// ===========================
// CONFIGURATION DU CLIENT
// ===========================
//
// Adresse de l'API consommée par la SPA. Le nom d'hôte est déduit de la page
// courante : `localhost` et `127.0.0.1` sont deux origines distinctes pour le
// navigateur, et les figer provoquerait un refus CORS selon l'URL d'entrée.
//
// Ajustez API_PORT si le backend n'écoute pas sur le port 8000 de la même
// machine — ou, sans toucher à ce fichier, ouvrez la page une fois avec
// `?api=http://127.0.0.1:8765/api` : l'adresse est retenue pour les visites
// suivantes. Utile quand le port 8000 est déjà pris par un autre projet, cas
// où l'application semble muette alors qu'elle interroge simplement le voisin.
// `?api=` seul efface le détour et rend la main au port configuré ci-dessous.

const API_PORT = 8000;

const MEMOIRE_API = 'fluxgestionApiUrl';

const adresseForcee = new URLSearchParams(window.location.search).get('api');
if (adresseForcee !== null) {
    try {
        if (adresseForcee) localStorage.setItem(MEMOIRE_API, adresseForcee);
        else localStorage.removeItem(MEMOIRE_API);
    } catch (erreur) {
        // Navigation privée ou stockage refusé : l'adresse vaut alors pour
        // cette page seulement, ce qui dépanne quand même.
        console.warn("Adresse d'API non mémorisée:", erreur);
    }
}

let adresseRetenue = adresseForcee;
if (!adresseRetenue) {
    try {
        adresseRetenue = localStorage.getItem(MEMOIRE_API);
    } catch (erreur) {
        adresseRetenue = null;
    }
}

window.FLUXGESTION_API_URL = adresseRetenue
    || `${window.location.protocol}//${window.location.hostname}:${API_PORT}/api`;
