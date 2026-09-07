// ===========================
// UTILITAIRES
// ===========================

/**
 * Échappe une chaîne destinée à être insérée dans du HTML.
 *
 * Tout le contenu de l'application est saisi par les utilisateurs (tâches,
 * bilans, jalons) : l'injecter tel quel dans innerHTML permettrait à un membre
 * de faire exécuter du script chez ses collègues.
 *
 * @param {*} value - La valeur à échapper
 * @returns {string} La chaîne sûre
 */
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Affiche une notification temporaire.
 * @param {string} message - Le texte à afficher
 * @param {string} type - success | error | warning | info
 * @param {number} duration - Durée d'affichage en millisecondes
 */
function showToast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = {
        success: 'fa-circle-check',
        error: 'fa-circle-exclamation',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class="fas ${icons[type] || icons.info} toast-icon"></i>
        <span>${escapeHtml(message)}</span>
    `;
    container.appendChild(toast);

    setTimeout(() => toast.remove(), duration);
}

/**
 * Devise de l'application.
 *
 * `XAF` s'écrit « FCFA » (zone BEAC : Cameroun, Gabon, Tchad…), `XOF` s'écrit
 * « F CFA » (zone BCEAO : Sénégal, Côte d'Ivoire, Mali…). Les deux monnaies
 * ont la même parité avec l'euro : seul le libellé affiché change.
 */
const CURRENCY = 'XAF';

/**
 * Formate un montant en francs CFA.
 *
 * Le franc CFA n'a pas de subdivision : aucune décimale par défaut.
 *
 * @param {number|string} amount - Le montant
 * @param {number} decimals - Nombre de décimales
 * @returns {string} Le montant formaté
 */
function formatMoney(amount, decimals = 0) {
    const value = Number(amount) || 0;
    return value.toLocaleString('fr-FR', {
        style: 'currency',
        currency: CURRENCY,
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/**
 * Montant abrégé : « 12,5 M FCFA » au lieu de « 12 500 000 FCFA ».
 *
 * Réservé aux endroits étroits — tuiles de statistiques, axes de graphique,
 * barre latérale — où le montant complet déborderait. Partout où le chiffre
 * exact compte (bulletins, documents imprimés), `formatMoney` reste de mise.
 */
function formatMoneyCompact(amount) {
    const value = Number(amount) || 0;
    return value.toLocaleString('fr-FR', {
        style: 'currency',
        currency: CURRENCY,
        notation: 'compact',
        maximumFractionDigits: 1
    });
}

/**
 * Formate un nombre avec séparateur de milliers.
 */
function formatNumber(value, decimals = 0) {
    return (Number(value) || 0).toLocaleString('fr-FR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/** Formate un pourcentage, ou un tiret si la valeur est absente. */
function formatPercent(value) {
    if (value === null || value === undefined) return '—';
    return `${formatNumber(value, 0)} %`;
}

/** Formate une date en JJ/MM/AAAA. */
function formatDate(date) {
    if (!date) return '—';
    return new Date(date).toLocaleDateString('fr-FR', {
        day: '2-digit', month: '2-digit', year: 'numeric'
    });
}

/** Formate une date en JJ/MM. */
function formatDateShort(date) {
    if (!date) return '—';
    return new Date(date).toLocaleDateString('fr-FR', {
        day: '2-digit', month: '2-digit'
    });
}

/** Formate une heure en HH:MM. */
function formatTime(value) {
    if (!value) return '—';
    return new Date(value).toLocaleTimeString('fr-FR', {
        hour: '2-digit', minute: '2-digit'
    });
}

/** Formate une durée en minutes : « 45 min », « 2 h 05 ». */
function formatDuration(minutes) {
    const total = Number(minutes) || 0;
    if (total < 60) return `${total} min`;
    return `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, '0')}`;
}

/** Formate un mois AAAA-MM ou une date en « septembre 2026 ». */
function formatMonth(value) {
    if (!value) return '—';
    const date = value.length === 7 ? new Date(`${value}-01`) : new Date(value);
    return date.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
}

/** Exprime une date en durée relative (« il y a 3 jours »). */
function timeAgo(date) {
    if (!date) return '—';

    const seconds = Math.floor((new Date() - new Date(date)) / 1000);
    const units = [
        { limit: 60, label: "à l'instant", divisor: 1 },
        { limit: 3600, label: 'minute', divisor: 60 },
        { limit: 86400, label: 'heure', divisor: 3600 },
        { limit: 2592000, label: 'jour', divisor: 86400 },
        { limit: 31536000, label: 'mois', divisor: 2592000 }
    ];

    if (seconds < 60) return "à l'instant";

    for (const unit of units) {
        if (seconds < unit.limit) {
            const count = Math.floor(seconds / unit.divisor);
            const plural = count > 1 && unit.label !== 'mois' ? 's' : '';
            return `il y a ${count} ${unit.label}${plural}`;
        }
    }
    return formatDate(date);
}

/**
 * Formate une date pour un <input type="date"> (AAAA-MM-JJ).
 *
 * On lit les composantes locales : `toISOString()` convertit d'abord en UTC et
 * renverrait la veille pour tout fuseau à l'est de Greenwich — dont
 * Europe/Paris, le fuseau par défaut du projet.
 */
function toDateInputValue(date) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Formate une date pour un <input type="month"> (AAAA-MM). */
function toMonthInputValue(date) {
    return toDateInputValue(date).slice(0, 7);
}

/** Met une chaîne en majuscule initiale. */
function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/** Valide une adresse email. */
function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Retarde l'exécution d'une fonction tant qu'elle est rappelée.
 * Évite une requête à chaque frappe clavier.
 */
function debounce(fn, delay = 300) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

// ===========================
// INTERFACE
// ===========================

let loadingDepth = 0;

/**
 * Affiche ou masque l'indicateur de chargement.
 *
 * Les appels s'imbriquent : on compte les demandes plutôt que de masquer
 * l'indicateur dès la première requête terminée.
 */
function setLoading(show = true) {
    const spinner = document.getElementById('loadingSpinner');
    if (!spinner) return;

    loadingDepth = Math.max(0, loadingDepth + (show ? 1 : -1));
    spinner.classList.toggle('active', loadingDepth > 0);
}

/**
 * Garnit un conteneur de blocs d'attente.
 *
 * Le conteneur déjà rempli est laissé tel quel : au retour sur une page, les
 * données précédentes restent lisibles pendant que la requête se rejoue,
 * plutôt que de faire clignoter la vue.
 *
 * @param {string} containerId - L'identifiant du conteneur
 * @param {number} count - Nombre de blocs
 * @param {string} variant - `card` pour une liste, `row` pour un tableau
 */
function showSkeleton(containerId, count = 3, variant = 'card') {
    const container = document.getElementById(containerId);
    if (!container || container.children.length) return;

    const block = variant === 'row'
        ? `<tr class="skeleton-row"><td colspan="7">
               <span class="skeleton skeleton-line"></span>
           </td></tr>`
        : `<div class="skeleton-card">
               <span class="skeleton skeleton-title"></span>
               <span class="skeleton skeleton-line"></span>
               <span class="skeleton skeleton-line court"></span>
           </div>`;

    container.innerHTML = block.repeat(count);
}

/** Initialise le thème et son bouton de bascule. */
function initTheme() {
    if (localStorage.getItem('darkMode') === 'true') {
        document.body.classList.add('dark-mode');
    }
    // La page de connexion n'a pas de bouton de thème.
    document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
}

/** Bascule entre thème clair et sombre. */
function toggleTheme() {
    document.body.classList.toggle('dark-mode');
    localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));

    // Les couleurs d'axes des graphiques sont figées à la construction.
    if (typeof refreshCharts === 'function') refreshCharts();
}

/** Écrit un texte dans un élément, s'il est présent dans la page. */
function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

/** Active une page, son entrée de menu et le fil d'Ariane. */
function setActivePage(page) {
    document.querySelectorAll('.page').forEach(section => {
        section.classList.toggle('active', section.id === page);
    });

    let current = null;
    document.querySelectorAll('.nav-link').forEach(link => {
        const isActive = link.dataset.page === page;
        link.classList.toggle('active', isActive);
        if (isActive) current = link;
    });

    // Le fil d'Ariane recopie l'entrée de menu : un seul libellé à maintenir.
    if (current) {
        setText('topbarSection', current.dataset.section || '');
        setText('topbarTitle', current.querySelector('.nav-label').textContent.trim());
    }

    // Sur mobile, le rail recouvre le contenu : il se referme après le choix.
    setSidebarOpen(false);
}

/** Ouvre ou ferme le rail de navigation (tiroir sous 1024 px). */
function setSidebarOpen(open) {
    const sidebar = document.getElementById('appSidebar');
    if (!sidebar) return;

    sidebar.classList.toggle('open', open);
    document.getElementById('sidebarScrim')?.classList.toggle('active', open);
}

/** Branche le tiroir de navigation et affiche la date du jour. */
function initShell() {
    document.getElementById('sidebarToggle')?.addEventListener('click', () => {
        const sidebar = document.getElementById('appSidebar');
        setSidebarOpen(!sidebar.classList.contains('open'));
    });
    document.getElementById('sidebarScrim')
        ?.addEventListener('click', () => setSidebarOpen(false));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') setSidebarOpen(false);
    });

    setText('topbarDate', new Date().toLocaleDateString('fr-FR', {
        weekday: 'long', day: 'numeric', month: 'long'
    }));
}

/** Ouvre une modale. */
function openModal(modalId) {
    document.getElementById(modalId)?.classList.add('active');
}

/** Ferme une modale. */
function closeModal(modalId) {
    document.getElementById(modalId)?.classList.remove('active');
}

/** Branche la fermeture des modales : croix, bouton Annuler, fond, Échap. */
function initModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.querySelectorAll('.modal-close').forEach(button => {
            button.addEventListener('click', () => modal.classList.remove('active'));
        });
        modal.addEventListener('click', (event) => {
            if (event.target === modal) modal.classList.remove('active');
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            document.querySelectorAll('.modal.active')
                .forEach(modal => modal.classList.remove('active'));
        }
    });
}
