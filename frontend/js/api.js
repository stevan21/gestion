// ===========================
// CLIENT API
// ===========================

const API_URL = window.FLUXGESTION_API_URL || 'http://localhost:8000/api';

const TOKEN_KEY = 'authToken';
const USER_KEY = 'authUser';

// ===========================
// SESSION
// ===========================

const session = {
    getToken: () => localStorage.getItem(TOKEN_KEY) || '',

    getUser: () => {
        try {
            return JSON.parse(localStorage.getItem(USER_KEY)) || null;
        } catch {
            return null;
        }
    },

    isAuthenticated: () => Boolean(localStorage.getItem(TOKEN_KEY)),

    isFounder: () => Boolean(session.getUser()?.is_founder),

    save: (token, user) => {
        localStorage.setItem(TOKEN_KEY, token);
        if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    },

    clear: () => {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    },

    /** Redirige vers la page de connexion en mémorisant la destination. */
    redirectToLogin: () => {
        const current = window.location.pathname.split('/').pop() || 'index.html';
        if (current === 'login.html') return;
        session.clear();
        const next = encodeURIComponent(current + window.location.search);
        window.location.href = `login.html?next=${next}`;
    }
};

// ===========================
// REQUÊTES
// ===========================

/**
 * Extrait un message lisible d'une réponse d'erreur DRF.
 * DRF renvoie soit {detail}, soit {champ: [messages]}, soit une liste.
 */
function extractError(payload, fallback) {
    if (!payload) return fallback;
    if (typeof payload === 'string') return payload;
    if (payload.detail) return payload.detail;
    if (payload.error) return payload.error;

    const messages = [];
    for (const [field, value] of Object.entries(payload)) {
        const text = Array.isArray(value) ? value.join(' ') : String(value);
        messages.push(field === 'non_field_errors' ? text : `${field} : ${text}`);
    }
    return messages.length ? messages.join('\n') : fallback;
}

/**
 * Effectue une requête API.
 * @param {string} endpoint - L'endpoint (commençant par /)
 * @param {object} options - method, body, headers, silent, skipAuthRedirect
 * @returns {Promise<any>} Le corps de la réponse désérialisé
 */
async function apiRequest(endpoint, options = {}) {
    const {
        silent = false, quiet = false, skipAuthRedirect = false, ...fetchOptions
    } = options;

    const headers = { 'Content-Type': 'application/json', ...(fetchOptions.headers || {}) };
    const token = session.getToken();
    if (token) headers.Authorization = `Token ${token}`;

    const config = {
        ...fetchOptions,
        headers,
        method: fetchOptions.method || 'GET'
    };

    if (config.body && typeof config.body === 'object') {
        config.body = JSON.stringify(config.body);
    }

    try {
        // `quiet` : relecture de fond, l'indicateur de chargement reste au repos.
        if (!quiet) setLoading(true);
        const response = await fetch(`${API_URL}${endpoint}`, config);

        if (response.status === 401 && !skipAuthRedirect) {
            session.redirectToLogin();
            throw new Error('Session expirée. Veuillez vous reconnecter.');
        }

        if (response.status === 204) return null;

        const contentType = response.headers.get('Content-Type') || '';
        const payload = contentType.includes('application/json')
            ? await response.json()
            : await response.text();

        if (!response.ok) {
            const error = new Error(
                extractError(payload, `Erreur API : ${response.statusText}`)
            );
            error.status = response.status;
            error.payload = payload;
            throw error;
        }

        return payload;
    } catch (error) {
        console.error('Erreur API:', error);
        if (!silent) showToast(error.message, 'error');
        throw error;
    } finally {
        if (!quiet) setLoading(false);
    }
}

/** Télécharge un fichier généré par l'API. */
async function apiDownload(endpoint, options = {}) {
    const headers = {};
    const token = session.getToken();
    if (token) headers.Authorization = `Token ${token}`;

    try {
        setLoading(true);
        const response = await fetch(`${API_URL}${endpoint}`, {
            method: options.method || 'GET',
            headers
        });

        if (response.status === 401) {
            session.redirectToLogin();
            throw new Error('Session expirée. Veuillez vous reconnecter.');
        }
        if (!response.ok) {
            throw new Error(`Le téléchargement a échoué (${response.status})`);
        }

        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/);
        const filename = options.filename || (match ? match[1] : 'export.csv');

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);

        return filename;
    } catch (error) {
        console.error('Erreur de téléchargement:', error);
        showToast(error.message, 'error');
        throw error;
    } finally {
        setLoading(false);
    }
}

/** Normalise une réponse paginée DRF en tableau. */
function unwrap(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.results)) return payload.results;
    return [];
}

/** Construit une query string en ignorant les valeurs vides. */
function buildQuery(params = {}) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value === undefined || value === null || value === '') continue;
        if (Array.isArray(value)) {
            value.forEach(item => search.append(key, item));
        } else {
            search.append(key, value);
        }
    }
    const query = search.toString();
    return query ? `?${query}` : '';
}

/**
 * Récupère toutes les pages d'une collection paginée.
 * Le plafond évite de boucler indéfiniment sur un jeu très large.
 */
async function fetchAllPages(endpoint, params = {}, maxPages = 20) {
    const items = [];
    let page = 1;

    while (page <= maxPages) {
        const payload = await apiRequest(`${endpoint}${buildQuery({ ...params, page })}`);
        items.push(...unwrap(payload));
        if (!payload || !payload.next) break;
        page += 1;
    }

    return items;
}

// ===========================
// AUTHENTIFICATION
// ===========================

const authAPI = {
    register: async (data) => {
        const result = await apiRequest('/auth/register/', {
            method: 'POST', body: data, skipAuthRedirect: true
        });
        session.save(result.token, result.user);
        return result;
    },

    login: async (username, password) => {
        const result = await apiRequest('/auth/login/', {
            method: 'POST', body: { username, password }, skipAuthRedirect: true
        });
        session.save(result.token, result.user);
        return result;
    },

    logout: async () => {
        try {
            await apiRequest('/auth/logout/', { method: 'POST', silent: true });
        } catch {
            // Le token est peut-être déjà invalide : la session locale part quand même.
        }
        session.clear();
    },

    me: async () => {
        const user = await apiRequest('/auth/me/');
        session.save(session.getToken(), user);
        return user;
    },

    changePassword: async (oldPassword, newPassword) => {
        const result = await apiRequest('/auth/change-password/', {
            method: 'POST',
            body: { old_password: oldPassword, new_password: newPassword }
        });
        session.save(result.token, result.user);
        return result;
    }
};

// ===========================
// MEMBRES
// ===========================

const memberAPI = {
    getAll: async (params = {}) => fetchAllPages('/members/', params),

    me: async () => apiRequest('/members/me/'),

    updateMe: async (data) =>
        apiRequest('/members/me/', { method: 'PATCH', body: data }),

    // --- Administration des comptes (fondateurs) ---

    create: async (data) => apiRequest('/members/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/members/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/members/${id}/`, { method: 'DELETE' }),

    /** Active ou désactive un compte sans toucher à son historique. */
    setActive: async (id, active) =>
        apiRequest(`/members/${id}/set_active/`, {
            method: 'PATCH', body: { active }
        }),

    /** Engendre un mot de passe ; il n'est lisible que dans cette réponse. */
    resetPassword: async (id) =>
        apiRequest(`/members/${id}/reset_password/`, { method: 'PATCH' })
};

// ===========================
// OBJECTIFS MENSUELS
// ===========================

const objectiveAPI = {
    getAll: async (params = {}) => fetchAllPages('/objectives/', params),

    getById: async (id) => apiRequest(`/objectives/${id}/`),

    /** Objectifs du mois en cours ; null si le mois n'est pas encore défini. */
    current: async () => {
        try {
            return await apiRequest('/objectives/current/', { silent: true });
        } catch (error) {
            if (error.status === 404) return null;
            throw error;
        }
    },

    create: async (data) => apiRequest('/objectives/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/objectives/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/objectives/${id}/`, { method: 'DELETE' }),

    close: async (id) => apiRequest(`/objectives/${id}/close/`, { method: 'PATCH' }),

    history: async (months = 6) =>
        apiRequest(`/objectives/history/${buildQuery({ months })}`),

    exportCSV: async (params = {}) =>
        apiDownload(`/objectives/export/${buildQuery(params)}`)
};

// ===========================
// FEUILLE DE ROUTE
// ===========================

const roadmapAPI = {
    getAll: async (params = {}) => fetchAllPages('/roadmap/', params),

    getById: async (id) => apiRequest(`/roadmap/${id}/`),

    create: async (data) => apiRequest('/roadmap/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/roadmap/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/roadmap/${id}/`, { method: 'DELETE' }),

    complete: async (id) => apiRequest(`/roadmap/${id}/complete/`, { method: 'PATCH' }),

    overdue: async () => apiRequest('/roadmap/overdue/')
};

// ===========================
// TÂCHES DU JOUR
// ===========================

const taskAPI = {
    getAll: async (params = {}) => fetchAllPages('/tasks/', params),

    /** Tâches du jour et retards, en un appel. */
    today: async () => apiRequest('/tasks/today/'),

    create: async (data) => apiRequest('/tasks/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/tasks/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/tasks/${id}/`, { method: 'DELETE' }),

    /** Lance le chronomètre : la tâche passe en cours. */
    start: async (id) => apiRequest(`/tasks/${id}/start/`, { method: 'PATCH' }),

    complete: async (id) => apiRequest(`/tasks/${id}/complete/`, { method: 'PATCH' }),

    carryOver: async () => apiRequest('/tasks/carry_over/', { method: 'POST' })
};

// ===========================
// RAPPORTS
// ===========================

const reportAPI = {
    getAll: async (params = {}) => fetchAllPages('/reports/', params),

    getById: async (id) => apiRequest(`/reports/${id}/`),

    create: async (data) => apiRequest('/reports/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/reports/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/reports/${id}/`, { method: 'DELETE' }),

    submit: async (id) => apiRequest(`/reports/${id}/submit/`, { method: 'PATCH' })
};

// ===========================
// BULLETINS DE PAIE (gérant)
// ===========================

const payslipAPI = {
    getAll: async (params = {}) => fetchAllPages('/payslips/', params),

    getById: async (id) => apiRequest(`/payslips/${id}/`),

    create: async (data) => apiRequest('/payslips/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/payslips/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/payslips/${id}/`, { method: 'DELETE' }),

    summary: async (month) => apiRequest(`/payslips/summary/${buildQuery({ month })}`)
};

// ===========================
// SUIVI DU PERSONNEL (gérant)
// ===========================

const staffEventAPI = {
    getAll: async (params = {}) => fetchAllPages('/staff-events/', params),

    create: async (data) => apiRequest('/staff-events/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/staff-events/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/staff-events/${id}/`, { method: 'DELETE' }),

    summary: async (month) =>
        apiRequest(`/staff-events/summary/${buildQuery({ month })}`)
};

// ===========================
// CONGÉS ET ABSENCES
// ===========================

const leaveAPI = {
    getAll: async (params = {}) => fetchAllPages('/leaves/', params),

    getById: async (id) => apiRequest(`/leaves/${id}/`),

    create: async (data) => apiRequest('/leaves/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/leaves/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/leaves/${id}/`, { method: 'DELETE' }),

    /** Accorde ou refuse une demande (direction). */
    decide: async (id, status, decision = '') =>
        apiRequest(`/leaves/${id}/decide/`, {
            method: 'PATCH', body: { status, decision }
        }),

    /** Retire une demande : son auteur y renonce. */
    cancel: async (id) => apiRequest(`/leaves/${id}/cancel/`, { method: 'PATCH' }),

    /** Solde de l'année : le sien, ou celui de l'équipe pour la direction. */
    balance: async (year) => apiRequest(`/leaves/balance/${buildQuery({ year })}`)
};

// ===========================
// POINTAGE
// ===========================

const attendanceAPI = {
    getAll: async (params = {}) => fetchAllPages('/attendance/', params),

    /** Sa journée en cours et ce que le mois compte déjà. */
    today: async (silent = false) => apiRequest('/attendance/today/', { silent }),

    checkIn: async () => apiRequest('/attendance/check_in/', { method: 'POST' }),

    checkOut: async () => apiRequest('/attendance/check_out/', { method: 'POST' }),

    /** Présence du mois, membre par membre. */
    summary: async (month) =>
        apiRequest(`/attendance/summary/${buildQuery({ month })}`),

    // --- Correction d'un pointage (direction) ---

    update: async (id, data) =>
        apiRequest(`/attendance/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/attendance/${id}/`, { method: 'DELETE' })
};

// ===========================
// RÉACTIONS ET POINTS
// ===========================

const reactionAPI = {
    getAll: async (params = {}) => fetchAllPages('/reactions/', params),

    create: async (data) => apiRequest('/reactions/', { method: 'POST', body: data }),

    delete: async (id) => apiRequest(`/reactions/${id}/`, { method: 'DELETE' }),

    /** Barème : natures, points par défaut et valeur du point. */
    scale: async () => apiRequest('/reactions/scale/', { silent: true })
};

// ===========================
// BOÎTE À SUGGESTIONS
// ===========================

const suggestionAPI = {
    getAll: async (params = {}) => fetchAllPages('/suggestions/', params),

    create: async (data) => apiRequest('/suggestions/', { method: 'POST', body: data }),

    update: async (id, data) =>
        apiRequest(`/suggestions/${id}/`, { method: 'PATCH', body: data }),

    delete: async (id) => apiRequest(`/suggestions/${id}/`, { method: 'DELETE' }),

    /** Marque une suggestion comme lue ou traitée (direction). */
    handle: async (id, status, reply = '') =>
        apiRequest(`/suggestions/${id}/handle/`, {
            method: 'PATCH', body: { status, reply }
        })
};

// ===========================
// TABLEAUX DE BORD
// ===========================

const dashboardAPI = {
    overview: async () => apiRequest('/dashboard/overview/'),

    /** Synthèse d'équipe : réservée aux fondateurs. */
    team: async (month) => apiRequest(`/dashboard/team/${buildQuery({ month })}`),

    activity: async (days = 14) =>
        apiRequest(`/dashboard/activity/${buildQuery({ days })}`),

    /** Alertes du moment, sans stockage : la cloche les relit à l'ouverture. */
    notifications: async () => apiRequest('/dashboard/notifications/', { silent: true }),

    /** Activité de l'équipe à l'instant (fondateurs). */
    panel: async (quiet = false) =>
        apiRequest('/dashboard/panel/', { quiet, silent: quiet })
};
