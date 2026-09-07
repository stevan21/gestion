// ===========================
// APPLICATION
// ===========================

/** État partagé entre les pages, alimenté au chargement. */
const state = {
    profile: null,
    objectives: [],
    currentObjective: null,
    // Personnel de l'équipe, chargé une fois pour les sélecteurs du gérant.
    staff: [],
    // Minuteur de relecture du panel, actif seulement sur cette page.
    panelTimer: null,
    // Barème des réactions, lu une fois par session.
    reactionScale: null,
    // Congés de l'année et solde : les filtres trient ce jeu, sans requête.
    leaves: [],
    leaveBalance: null,
    // Journée pointée du membre connecté, portée par le bouton du haut.
    punch: null
};

const STATUS_CLASS = {
    todo: 'status-todo',
    in_progress: 'status-progress',
    done: 'status-done',
    blocked: 'status-blocked',
    draft: 'status-draft',
    active: 'status-progress',
    closed: 'status-done',
    submitted: 'status-done'
};

const PRIORITY_LABEL = { 1: 'Basse', 2: 'Normale', 3: 'Haute', 4: 'Urgente' };

// ===========================
// DÉMARRAGE
// ===========================

async function initApp() {
    // Sans session, inutile de monter l'interface : l'API refuserait tout appel.
    if (!session.isAuthenticated()) {
        session.redirectToLogin();
        return;
    }

    initTheme();
    initShell();
    initModals();
    initEventListeners();

    // Le profil et le tableau de bord n'ont pas besoin l'un de l'autre :
    // les enchaîner doublait le temps d'attente au démarrage.
    showPageSkeleton('dashboard');
    await Promise.all([loadProfile(), loadDashboard(), loadNotifications(), loadPunch()]);
}

/** Charge le profil, affiche l'identité et révèle les vues de fondateur. */
async function loadProfile() {
    try {
        const profile = await authAPI.me();
        state.profile = profile;

        const displayName = profile.display_name || profile.username;
        setText('sidebarName', displayName);
        setText('sidebarRole',
            [profile.job_title, profile.department].filter(Boolean).join(' · ') ||
            profile.role_label || '');

        // Les vues d'équipe n'apparaissent que pour un fondateur, la paie et le
        // suivi du personnel pour le seul gérant ; le serveur les refuse de
        // toute façon, l'affichage suit simplement la règle.
        document.querySelectorAll('.founder-only').forEach(element => {
            element.hidden = !profile.is_founder;
        });
        document.querySelectorAll('.manager-only').forEach(element => {
            element.hidden = !profile.is_manager;
        });
    } catch (error) {
        console.error('Chargement du profil:', error);
    }
}

// ===========================
// TABLEAU DE BORD
// ===========================

async function loadDashboard() {
    // Les graphiques tirent leurs propres séries : ils partent tout de suite,
    // sans attendre la synthèse.
    const charts = initCharts();

    try {
        const overview = await dashboardAPI.overview();
        state.currentObjective = overview.objective;

        renderObjectiveBanner(overview);
        renderDashboardStats(overview);
        renderSidebar(overview);
        renderTaskList('dashboardTasks', overview.tasks.items, {
            emptyMessage: "Aucune tâche prévue aujourd'hui."
        });
        updateTaskBadge(overview.tasks);
    } catch (error) {
        console.error('Chargement du tableau de bord:', error);
        showLoadError('dashboardTasks');
    }

    await charts;
}

/** Bandeau d'alerte quand le mois n'est pas défini ou accuse du retard. */
function renderObjectiveBanner(overview) {
    const container = document.getElementById('objectiveBanner');
    const objective = overview.objective;

    if (!objective) {
        container.innerHTML = `
            <div class="banner banner-info">
                <i class="fas fa-circle-info"></i>
                <div>
                    <strong>Vos objectifs du mois ne sont pas encore définis.</strong>
                    <p>Indiquez le chiffre d'affaires et le nombre de clients visés
                       pour suivre votre avancement.</p>
                </div>
                <button class="btn btn-primary btn-small" id="bannerDefineBtn">
                    Définir maintenant
                </button>
            </div>`;
        document.getElementById('bannerDefineBtn')
            .addEventListener('click', () => openObjectiveModal());
        return;
    }

    if (objective.is_at_risk) {
        container.innerHTML = `
            <div class="banner banner-warning">
                <i class="fas fa-triangle-exclamation"></i>
                <div>
                    <strong>Vous êtes en retard sur vos objectifs.</strong>
                    <p>${formatPercent(objective.completion)} atteint alors que
                       ${formatPercent(objective.elapsed_ratio)} du mois est écoulé.
                       Il reste ${escapeHtml(formatMoney(objective.revenue_gap))}
                       à réaliser.</p>
                </div>
            </div>`;
        return;
    }

    container.innerHTML = '';
}

function renderDashboardStats(overview) {
    const objective = overview.objective;

    document.getElementById('dashboardSubtitle').textContent =
        capitalize(formatMonth(overview.month));

    document.getElementById('statRevenue').textContent = objective
        ? `${formatMoneyCompact(objective.revenue_achieved)} / `
          + `${formatMoneyCompact(objective.revenue_target)}`
        : '—';
    document.getElementById('statClients').textContent = objective
        ? `${objective.clients_achieved} / ${objective.clients_target}`
        : '—';
    document.getElementById('statTasks').textContent =
        `${overview.tasks.done} / ${overview.tasks.total}`;
    document.getElementById('statRoadmap').textContent =
        `${overview.roadmap.done} / ${overview.roadmap.total}`;
}

/** Résumé permanent dans la barre latérale. */
function renderSidebar(overview) {
    const objective = overview.objective;
    const objectiveBox = document.getElementById('sidebarObjective');

    objectiveBox.innerHTML = objective
        ? `
            ${progressBar(objective.completion, objective.elapsed_ratio)}
            <div class="sidebar-metric">
                <span>CA</span>
                <strong>${formatMoneyCompact(objective.revenue_achieved)}</strong>
            </div>
            <div class="sidebar-metric">
                <span>Clients</span>
                <strong>${objective.clients_achieved} / ${objective.clients_target}</strong>
            </div>
            ${objective.focus
                ? `<p class="sidebar-focus">« ${escapeHtml(objective.focus)} »</p>` : ''}
        `
        : '<p class="text-muted">Mois non défini</p>';

    document.getElementById('sidebarToday').innerHTML = `
        <div class="sidebar-metric">
            <span>Tâches faites</span>
            <strong>${overview.tasks.done} / ${overview.tasks.total}</strong>
        </div>
        ${overview.tasks.late
            ? `<div class="sidebar-metric warning">
                   <span>En retard</span><strong>${overview.tasks.late}</strong>
               </div>` : ''}
        ${overview.roadmap.overdue
            ? `<div class="sidebar-metric warning">
                   <span>Jalons dépassés</span><strong>${overview.roadmap.overdue}</strong>
               </div>` : ''}
    `;
}

/**
 * Barre d'avancement, avec un repère sur le temps écoulé.
 * Le repère rend le retard lisible d'un coup d'œil.
 */
function progressBar(completion, elapsed) {
    const value = Math.min(completion || 0, 100);
    const marker = Math.min(elapsed || 0, 100);
    const behind = completion !== null && completion < (elapsed || 0) - 15;

    return `
        <div class="progress" title="${formatPercent(completion)} atteint">
            <div class="progress-fill ${behind ? 'behind' : ''}" style="width:${value}%"></div>
            <div class="progress-marker" style="left:${marker}%"
                 title="${formatPercent(elapsed)} du mois écoulé"></div>
        </div>
        <div class="progress-legend">
            <span>${formatPercent(completion)} atteint</span>
            <span class="text-muted">${formatPercent(elapsed)} du mois</span>
        </div>`;
}

function updateTaskBadge(tasks) {
    const badge = document.getElementById('taskBadge');
    const remaining = (tasks.total - tasks.done) + (tasks.late || 0);
    badge.textContent = remaining;
    badge.hidden = remaining === 0;
}

// ===========================
// OBJECTIFS
// ===========================

async function loadObjectives() {
    try {
        const objectives = await objectiveAPI.getAll({
            status: document.getElementById('objectiveStatusFilter').value,
            department: document.getElementById('objectiveDepartmentFilter').value
        });
        state.objectives = objectives;
        renderObjectives(objectives);
    } catch (error) {
        console.error('Chargement des objectifs:', error);
        showLoadError('objectivesList');
    }
}

function renderObjectives(objectives) {
    const container = document.getElementById('objectivesList');

    if (!objectives.length) {
        container.innerHTML = emptyState(
            'fa-bullseye',
            'Aucun objectif',
            "Définissez le chiffre d'affaires et les clients visés pour un mois."
        );
        return;
    }

    const isFounder = Boolean(state.profile?.is_founder);

    container.innerHTML = objectives.map(objective => `
        <div class="objective-card ${objective.is_at_risk ? 'at-risk' : ''}"
             data-id="${objective.id}">
            <div class="objective-head">
                <div>
                    <h3>${escapeHtml(capitalize(formatMonth(objective.month)))}</h3>
                    ${isFounder
                        ? `<p class="text-muted">${escapeHtml(objective.member_name)}</p>` : ''}
                    ${objective.focus
                        ? `<p class="objective-focus">« ${escapeHtml(objective.focus)} »</p>` : ''}
                </div>
                <div class="objective-badges">
                    <span class="status-badge ${STATUS_CLASS[objective.status] || ''}">
                        ${escapeHtml(objective.status_label)}
                    </span>
                    ${objective.is_at_risk
                        ? '<span class="status-badge status-blocked">En retard</span>' : ''}
                </div>
            </div>

            ${progressBar(objective.completion, objective.elapsed_ratio)}

            <div class="objective-metrics">
                <div class="metric">
                    <span class="metric-label">Chiffre d'affaires</span>
                    <span class="metric-value">
                        ${formatMoney(objective.revenue_achieved)}
                        <small>/ ${formatMoney(objective.revenue_target)}</small>
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Clients</span>
                    <span class="metric-value">
                        ${objective.clients_achieved}
                        <small>/ ${objective.clients_target}</small>
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Feuille de route</span>
                    <span class="metric-value">
                        ${objective.roadmap_done}
                        <small>/ ${objective.roadmap_count} jalons</small>
                    </span>
                </div>
            </div>

            <div class="card-actions">
                <button class="btn btn-small btn-secondary edit-objective">
                    <i class="fas fa-pen"></i> Modifier
                </button>
                ${objective.status !== 'closed'
                    ? `<button class="btn btn-small btn-success close-objective">
                           <i class="fas fa-lock"></i> Clôturer
                       </button>` : ''}
            </div>
        </div>
    `).join('');

    container.querySelectorAll('.edit-objective').forEach(button => {
        button.addEventListener('click', () => {
            const id = Number(button.closest('.objective-card').dataset.id);
            openObjectiveModal(objectives.find(o => o.id === id));
        });
    });

    container.querySelectorAll('.close-objective').forEach(button => {
        button.addEventListener('click', async () => {
            const id = Number(button.closest('.objective-card').dataset.id);
            try {
                await objectiveAPI.close(id);
                showToast('Mois clôturé', 'success');
                await loadObjectives();
            } catch (error) {
                console.error('Clôture:', error);
            }
        });
    });
}

function openObjectiveModal(objective = null) {
    const form = document.getElementById('objectiveForm');
    form.reset();

    document.getElementById('objectiveId').value = objective?.id || '';
    document.getElementById('objectiveMonth').value = objective
        ? String(objective.month).slice(0, 7)
        : toMonthInputValue(new Date());
    document.getElementById('objectiveRevenueTarget').value =
        Number(objective?.revenue_target ?? 0);
    document.getElementById('objectiveRevenueAchieved').value =
        Number(objective?.revenue_achieved ?? 0);
    document.getElementById('objectiveClientsTarget').value = objective?.clients_target ?? 0;
    document.getElementById('objectiveClientsAchieved').value = objective?.clients_achieved ?? 0;
    document.getElementById('objectiveFocus').value = objective?.focus || '';
    document.getElementById('objectiveNotes').value = objective?.notes || '';

    document.querySelector('#objectiveModal .modal-header h2').textContent =
        objective ? 'Modifier les objectifs' : 'Définir les objectifs du mois';

    // Le mois identifie l'objectif : le changer reviendrait à en créer un autre.
    document.getElementById('objectiveMonth').disabled = Boolean(objective);

    openModal('objectiveModal');
}

async function submitObjective(event) {
    event.preventDefault();

    const id = document.getElementById('objectiveId').value;
    const payload = {
        revenue_target: document.getElementById('objectiveRevenueTarget').value || 0,
        revenue_achieved: document.getElementById('objectiveRevenueAchieved').value || 0,
        clients_target: Number(document.getElementById('objectiveClientsTarget').value) || 0,
        clients_achieved: Number(document.getElementById('objectiveClientsAchieved').value) || 0,
        focus: document.getElementById('objectiveFocus').value.trim(),
        notes: document.getElementById('objectiveNotes').value.trim()
    };

    if (!id) {
        // L'API attend un jour : le premier du mois saisi.
        payload.month = `${document.getElementById('objectiveMonth').value}-01`;
    }

    try {
        if (id) {
            await objectiveAPI.update(id, payload);
            showToast('Objectifs mis à jour', 'success');
        } else {
            await objectiveAPI.create(payload);
            showToast('Objectifs enregistrés', 'success');
        }
        closeModal('objectiveModal');
        await loadObjectives();
        await loadDashboard();
    } catch (error) {
        console.error('Enregistrement des objectifs:', error);
    }
}

// ===========================
// FEUILLE DE ROUTE
// ===========================

async function loadRoadmap() {
    try {
        const items = await roadmapAPI.getAll({
            status: document.getElementById('roadmapStatusFilter').value,
            search: document.getElementById('roadmapSearch').value.trim()
        });
        renderRoadmap(items);
    } catch (error) {
        console.error('Chargement de la feuille de route:', error);
        showLoadError('roadmapList');
    }
}

function renderRoadmap(items) {
    const container = document.getElementById('roadmapList');

    if (!items.length) {
        container.innerHTML = emptyState(
            'fa-route',
            'Aucun jalon',
            'Découpez votre objectif du mois en étapes concrètes.'
        );
        return;
    }

    const isFounder = Boolean(state.profile?.is_founder);

    container.innerHTML = items.map(item => `
        <div class="roadmap-card ${item.is_overdue ? 'overdue' : ''}" data-id="${item.id}">
            <div class="roadmap-head">
                <div>
                    <h3>${escapeHtml(item.title)}</h3>
                    <p class="text-muted">
                        ${escapeHtml(capitalize(formatMonth(item.month)))}
                        ${isFounder ? ` · ${escapeHtml(item.member_name)}` : ''}
                        ${item.due_date ? ` · échéance ${formatDate(item.due_date)}` : ''}
                    </p>
                </div>
                <span class="status-badge ${STATUS_CLASS[item.status] || ''}">
                    ${escapeHtml(item.status_label)}
                </span>
            </div>

            ${item.description
                ? `<p class="roadmap-description">${escapeHtml(item.description)}</p>` : ''}

            <div class="progress progress-slim">
                <div class="progress-fill" style="width:${item.progress}%"></div>
            </div>
            <div class="progress-legend">
                <span>${item.progress} %</span>
                ${item.open_tasks
                    ? `<span class="text-muted">${item.open_tasks} tâche(s) ouverte(s)</span>` : ''}
                ${item.is_overdue ? '<span class="text-warning">Échéance dépassée</span>' : ''}
            </div>

            <div class="card-actions">
                <button class="btn btn-small btn-secondary edit-roadmap">
                    <i class="fas fa-pen"></i> Modifier
                </button>
                ${item.status !== 'done'
                    ? `<button class="btn btn-small btn-success complete-roadmap">
                           <i class="fas fa-check"></i> Terminer
                       </button>` : ''}
                <button class="btn btn-small btn-danger delete-roadmap">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');

    container.querySelectorAll('.edit-roadmap').forEach(button => {
        button.addEventListener('click', () => {
            const id = Number(button.closest('.roadmap-card').dataset.id);
            openRoadmapModal(items.find(i => i.id === id));
        });
    });

    container.querySelectorAll('.complete-roadmap').forEach(button => {
        button.addEventListener('click', async () => {
            const id = Number(button.closest('.roadmap-card').dataset.id);
            try {
                await roadmapAPI.complete(id);
                showToast('Jalon terminé', 'success');
                await loadRoadmap();
            } catch (error) {
                console.error('Achèvement du jalon:', error);
            }
        });
    });

    container.querySelectorAll('.delete-roadmap').forEach(button => {
        button.addEventListener('click', async () => {
            const card = button.closest('.roadmap-card');
            const item = items.find(i => i.id === Number(card.dataset.id));
            if (!confirm(`Supprimer le jalon « ${item.title} » ?`)) return;
            try {
                await roadmapAPI.delete(item.id);
                showToast('Jalon supprimé', 'success');
                await loadRoadmap();
            } catch (error) {
                console.error('Suppression du jalon:', error);
            }
        });
    });
}

async function openRoadmapModal(item = null) {
    const form = document.getElementById('roadmapForm');
    form.reset();

    // La liste des mois disponibles vient des objectifs du membre.
    const select = document.getElementById('roadmapObjective');
    if (!state.objectives.length) {
        state.objectives = await objectiveAPI.getAll();
    }
    const own = state.objectives.filter(
        o => !state.profile?.is_founder || o.member === state.profile.member_id
    );

    if (!own.length) {
        showToast("Définissez d'abord vos objectifs du mois.", 'warning');
        return;
    }

    select.innerHTML = own.map(objective => `
        <option value="${objective.id}">
            ${escapeHtml(capitalize(formatMonth(objective.month)))}
        </option>
    `).join('');

    document.getElementById('roadmapId').value = item?.id || '';
    if (item) select.value = item.objective;
    select.disabled = Boolean(item);

    document.getElementById('roadmapTitle').value = item?.title || '';
    document.getElementById('roadmapDescription').value = item?.description || '';
    document.getElementById('roadmapDueDate').value = item?.due_date || '';
    document.getElementById('roadmapStatus').value = item?.status || 'todo';
    document.getElementById('roadmapProgress').value = item?.progress ?? 0;
    document.getElementById('roadmapProgressValue').textContent = item?.progress ?? 0;

    document.querySelector('#roadmapModal .modal-header h2').textContent =
        item ? 'Modifier le jalon' : 'Nouveau jalon';

    openModal('roadmapModal');
}

async function submitRoadmap(event) {
    event.preventDefault();

    const id = document.getElementById('roadmapId').value;
    const payload = {
        title: document.getElementById('roadmapTitle').value.trim(),
        description: document.getElementById('roadmapDescription').value.trim(),
        due_date: document.getElementById('roadmapDueDate').value || null,
        status: document.getElementById('roadmapStatus').value,
        progress: Number(document.getElementById('roadmapProgress').value)
    };
    if (!id) {
        payload.objective = Number(document.getElementById('roadmapObjective').value);
    }

    try {
        if (id) {
            await roadmapAPI.update(id, payload);
            showToast('Jalon mis à jour', 'success');
        } else {
            await roadmapAPI.create(payload);
            showToast('Jalon ajouté', 'success');
        }
        closeModal('roadmapModal');
        await loadRoadmap();
    } catch (error) {
        console.error('Enregistrement du jalon:', error);
    }
}

// ===========================
// TÂCHES DU JOUR
// ===========================

async function loadTasks() {
    // Le sélecteur de jalons ne dépend pas des tâches : les deux partent
    // ensemble plutôt que l'un après l'autre.
    const options = loadRoadmapOptions();

    try {
        const payload = await taskAPI.today();

        document.getElementById('tasksSubtitle').textContent =
            `${capitalize(formatMonth(payload.date))} — ${formatDate(payload.date)}`;

        renderTaskList('todayTasksList', payload.today, {
            emptyMessage: "Rien de prévu aujourd'hui. Ajoutez votre première tâche."
        });

        const lateSection = document.getElementById('lateTasksSection');
        lateSection.hidden = payload.late.length === 0;
        renderTaskList('lateTasksList', payload.late, { showDate: true });

        updateTaskBadge({
            total: payload.total_count,
            done: payload.done_count,
            late: payload.late.length
        });
    } catch (error) {
        console.error('Chargement des tâches:', error);
        showLoadError('todayTasksList');
    }

    await options;
}

/** Alimente le sélecteur de jalon du formulaire d'ajout rapide. */
async function loadRoadmapOptions() {
    const select = document.getElementById('quickTaskRoadmap');
    try {
        const [items, todo] = await Promise.all([
            roadmapAPI.getAll({ status: 'in_progress' }),
            roadmapAPI.getAll({ status: 'todo' })
        ]);
        const options = [...items, ...todo];

        select.innerHTML = '<option value="">Sans jalon</option>' + options.map(item =>
            `<option value="${item.id}">${escapeHtml(item.title)}</option>`
        ).join('');
    } catch (error) {
        console.error('Chargement des jalons:', error);
    }
}

function renderTaskList(containerId, tasks, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!tasks.length) {
        container.innerHTML = options.emptyMessage
            ? `<p class="text-muted text-center">${escapeHtml(options.emptyMessage)}</p>`
            : '';
        return;
    }

    container.innerHTML = tasks.map(task => `
        <div class="task-item priority-${task.priority} ${task.status === 'done' ? 'done' : ''}"
             data-id="${task.id}">
            <button class="task-check ${task.status === 'done' ? 'checked' : ''}"
                    title="${task.status === 'done' ? 'Terminée' : 'Marquer comme terminée'}"
                    ${task.status === 'done' ? 'disabled' : ''}>
                <i class="fas ${task.status === 'done' ? 'fa-circle-check' : 'fa-circle'}"></i>
            </button>
            <div class="task-body">
                <div class="task-title">${escapeHtml(task.title)}</div>
                <div class="task-meta text-muted">
                    ${options.showDate ? `${formatDate(task.date)} · ` : ''}
                    ${escapeHtml(PRIORITY_LABEL[task.priority] || '')}
                    ${task.roadmap_title ? ` · ${escapeHtml(task.roadmap_title)}` : ''}
                    ${task.estimated_minutes
                        ? ` · ${task.estimated_minutes} min prévues` : ''}
                    ${taskDuration(task)}
                </div>
            </div>
            ${task.status === 'todo' || task.status === 'blocked' ? `
                <button class="btn btn-small btn-secondary start-task">
                    <i class="fas fa-play"></i> Démarrer
                </button>` : ''}
            ${task.status === 'in_progress' ? `
                <button class="btn btn-small btn-success finish-task">
                    <i class="fas fa-flag-checkered"></i> Terminer
                </button>` : ''}
            <span class="status-badge ${STATUS_CLASS[task.status] || ''}">
                ${escapeHtml(task.status_label)}
            </span>
            <button class="btn-icon delete-task" title="Supprimer">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    `).join('');

    container.querySelectorAll('.task-check:not([disabled])').forEach(button => {
        button.addEventListener('click', async () => {
            const id = Number(button.closest('.task-item').dataset.id);
            try {
                await taskAPI.complete(id);
                showToast('Tâche terminée', 'success');
                await refreshCurrentPage();
            } catch (error) {
                console.error('Achèvement de la tâche:', error);
            }
        });
    });

    container.querySelectorAll('.start-task').forEach(button => {
        button.addEventListener('click', async () => {
            const id = Number(button.closest('.task-item').dataset.id);
            try {
                await taskAPI.start(id);
                showToast('Tâche démarrée', 'success');
                await refreshCurrentPage();
            } catch (error) {
                console.error('Démarrage de la tâche:', error);
            }
        });
    });

    container.querySelectorAll('.finish-task').forEach(button => {
        button.addEventListener('click', async () => {
            const id = Number(button.closest('.task-item').dataset.id);
            try {
                const tache = await taskAPI.complete(id);
                showToast(`Tâche terminée en ${tache.duration_label}`, 'success');
                await refreshCurrentPage();
            } catch (error) {
                console.error('Achèvement de la tâche:', error);
            }
        });
    });

    container.querySelectorAll('.delete-task').forEach(button => {
        button.addEventListener('click', async () => {
            const id = Number(button.closest('.task-item').dataset.id);
            try {
                await taskAPI.delete(id);
                showToast('Tâche supprimée', 'success');
                await refreshCurrentPage();
            } catch (error) {
                console.error('Suppression de la tâche:', error);
            }
        });
    });
}

async function submitQuickTask(event) {
    event.preventDefault();

    const title = document.getElementById('quickTaskTitle').value.trim();
    if (!title) return;

    try {
        await taskAPI.create({
            title,
            priority: Number(document.getElementById('quickTaskPriority').value),
            roadmap_item: Number(document.getElementById('quickTaskRoadmap').value) || null
        });
        document.getElementById('quickTaskTitle').value = '';
        showToast('Tâche ajoutée', 'success');
        await loadTasks();
    } catch (error) {
        console.error('Ajout de la tâche:', error);
    }
}

// ===========================
// RAPPORTS
// ===========================

async function loadReports() {
    try {
        const reports = await reportAPI.getAll({
            period_type: document.getElementById('reportPeriodFilter').value,
            status: document.getElementById('reportStatusFilter').value
        });
        renderReports(reports);
    } catch (error) {
        console.error('Chargement des rapports:', error);
        showLoadError('reportsList');
    }
}

/**
 * Libellés et champs propres à chaque type de rapport.
 *
 * Un bilan de période, une mission et une réunion ne rendent pas compte de la
 * même chose : « Bilan » convient à une semaine de travail, pas au compte
 * rendu d'un déplacement chez un client.
 */
const REPORT_FORMS = {
    daily: {
        start: 'Début', end: 'Fin', summary: 'Bilan',
        achievements: 'Réalisations', blockers: 'Difficultés',
        next_steps: 'Prochaines étapes'
    },
    weekly: {
        start: 'Début', end: 'Fin', summary: 'Bilan',
        achievements: 'Réalisations', blockers: 'Difficultés',
        next_steps: 'Prochaines étapes'
    },
    monthly: {
        start: 'Début', end: 'Fin', summary: 'Bilan',
        achievements: 'Réalisations', blockers: 'Difficultés',
        next_steps: 'Prochaines étapes'
    },
    mission: {
        start: 'Du', end: 'Au', summary: 'Déroulé de la mission',
        achievements: 'Résultats obtenus', blockers: 'Difficultés rencontrées',
        next_steps: 'Suites à donner'
    },
    meeting: {
        // Une réunion se tient un jour donné : la date de fin n'a pas de sens.
        start: 'Date de la réunion', end: null, summary: 'Compte rendu',
        achievements: 'Points abordés', blockers: 'Points de blocage',
        next_steps: 'Actions à suivre'
    }
};

/** Vrai pour un rapport de mission ou de réunion. */
function isEventReport(periodType) {
    return periodType === 'mission' || periodType === 'meeting';
}

function reportForm(periodType) {
    return REPORT_FORMS[periodType] || REPORT_FORMS.weekly;
}

/** Intitulé d'un rapport : son objet s'il en a un, son type sinon. */
function reportHeading(report) {
    if (report.title) return report.title;
    if (report.period_type === 'meeting') return `Réunion du ${formatDate(report.period_start)}`;
    return `${report.period_label} — ${formatDate(report.period_start)} `
        + `au ${formatDate(report.period_end)}`;
}

/** Dates d'un rapport, sous la forme qui convient à son type. */
function reportDates(report) {
    if (report.period_type === 'meeting' || report.period_start === report.period_end) {
        return formatDate(report.period_start);
    }
    return `du ${formatDate(report.period_start)} au ${formatDate(report.period_end)}`;
}

function renderReports(reports) {
    const container = document.getElementById('reportsList');

    if (!reports.length) {
        container.innerHTML = emptyState(
            'fa-file-lines',
            'Aucun rapport',
            'Rédigez un bilan de période, un rapport de mission ou de réunion.'
        );
        return;
    }

    const isFounder = Boolean(state.profile?.is_founder);

    container.innerHTML = reports.map(report => {
        const labels = reportForm(report.period_type);
        return `
        <div class="report-card" data-id="${report.id}">
            <div class="report-head">
                <div>
                    <span class="report-kind">${escapeHtml(report.period_label)}</span>
                    <h3>${escapeHtml(reportHeading(report))}</h3>
                    <p class="text-muted">
                        ${isFounder ? `${escapeHtml(report.member_name)} · ` : ''}
                        ${escapeHtml(reportDates(report))} ·
                        ${report.submitted_at
                            ? `soumis ${timeAgo(report.submitted_at)}`
                            : `modifié ${timeAgo(report.updated_at)}`}
                    </p>
                </div>
                <span class="status-badge ${STATUS_CLASS[report.status] || ''}">
                    ${escapeHtml(report.status_label)}
                </span>
            </div>

            ${report.location || report.participants ? `
                <dl class="report-meta">
                    ${report.location
                        ? `<div><dt>Lieu</dt><dd>${escapeHtml(report.location)}</dd></div>` : ''}
                    ${report.participants
                        ? `<div><dt>Participants</dt>
                               <dd>${escapeHtml(report.participants)}</dd></div>` : ''}
                </dl>` : ''}

            <p class="report-summary">${escapeHtml(report.summary)}</p>

            ${reportSection(labels.achievements, report.achievements)}
            ${reportSection(labels.blockers, report.blockers)}
            ${reportSection('Décisions', report.decisions)}
            ${reportSection(labels.next_steps, report.next_steps)}

            <div class="card-actions">
                ${report.status === 'draft' ? `
                    <button class="btn btn-small btn-secondary edit-report">
                        <i class="fas fa-pen"></i> Modifier
                    </button>
                    <button class="btn btn-small btn-success submit-report">
                        <i class="fas fa-paper-plane"></i> Soumettre
                    </button>` : ''}
                <button class="btn btn-small btn-secondary export-report"
                        title="Ouvre l'aperçu d'impression : choisissez « Enregistrer au format PDF »">
                    <i class="fas fa-file-pdf"></i> Exporter en PDF
                </button>
            </div>
        </div>
    `;
    }).join('');

    container.querySelectorAll('.edit-report').forEach(button => {
        button.addEventListener('click', () => {
            const id = Number(button.closest('.report-card').dataset.id);
            openReportModal(reports.find(r => r.id === id));
        });
    });

    container.querySelectorAll('.export-report').forEach(button => {
        button.addEventListener('click', () => {
            const id = Number(button.closest('.report-card').dataset.id);
            exportReportToPdf(reports.find(r => r.id === id));
        });
    });

    container.querySelectorAll('.submit-report').forEach(button => {
        button.addEventListener('click', async () => {
            const id = Number(button.closest('.report-card').dataset.id);
            try {
                await reportAPI.submit(id);
                showToast('Rapport soumis', 'success');
                await loadReports();
            } catch (error) {
                console.error('Soumission du rapport:', error);
            }
        });
    });
}

/**
 * Met le rapport en page et ouvre l'aperçu d'impression.
 *
 * Le navigateur sait enregistrer une impression au format PDF : c'est la voie
 * la plus sûre, sans bibliothèque tierce, et le document reste du texte
 * sélectionnable. Le titre du document devient le nom de fichier proposé.
 */
function exportReportToPdf(report) {
    if (!report) return;
    printDocument(buildPrintableReport(report), printableFileName(report));
}

/**
 * Affiche un document mis en page et lance l'impression.
 *
 * Le titre de la page devient le nom de fichier proposé par le navigateur ;
 * la classe bascule la feuille d'impression sur le document, sans quoi un
 * Ctrl+P de l'utilisateur imprimerait une page blanche.
 *
 * @param {string} html - Le document à imprimer
 * @param {string} filename - Le nom de fichier proposé
 */
function printDocument(html, filename) {
    document.getElementById('reportPrint').innerHTML = html;

    const previousTitle = document.title;
    document.title = filename.replace(/[\\/:*?"<>|]/g, '').slice(0, 120);
    document.body.classList.add('exporting');

    // `afterprint` se déclenche aussi bien après l'impression qu'après une
    // annulation : l'état revient dans tous les cas.
    const restore = () => {
        document.title = previousTitle;
        document.body.classList.remove('exporting');
        window.removeEventListener('afterprint', restore);
    };
    window.addEventListener('afterprint', restore);

    window.print();
}

/** Met le bulletin en page et ouvre l'aperçu d'impression. */
function exportPayslipToPdf(payslip) {
    if (!payslip) return;
    printDocument(
        buildPrintablePayslip(payslip),
        `Bulletin de paie - ${payslip.member_name} - ${payslip.month_label}`
    );
}

/** Bulletin imprimable : identité, décompte, net à payer. */
function buildPrintablePayslip(payslip) {
    const identity = [
        ['Salarié', payslip.member_name],
        ['Poste', payslip.job_title],
        ['Pôle', capitalize(payslip.department || '')],
        ['Période', capitalize(formatMonth(payslip.month))],
        ['Heures travaillées', Number(payslip.worked_hours)
            ? `${formatNumber(payslip.worked_hours, 2)} h` : ''],
        ['Établi le', payslip.issued_at ? formatDate(payslip.issued_at) : '']
    ].filter(([, value]) => value);

    const lines = [
        ['Salaire de base', payslip.base_salary, false],
        [`Heures supplémentaires (${formatNumber(payslip.overtime_hours, 2)} h)`,
         payslip.overtime_amount, false],
        ['Primes', payslip.bonuses, false],
        ['Retenues', payslip.deductions, true],
        ['Cotisations', payslip.contributions, true]
    ].filter(([, amount]) => Number(amount));

    return `
        <article class="print-sheet">
            <header class="print-head">
                <div class="print-brand">
                    <strong>Flux Gestion</strong>
                    <span>Suivi de performance d'équipe</span>
                </div>
                <div class="print-kind">Bulletin de paie</div>
            </header>

            <h1>${escapeHtml(capitalize(formatMonth(payslip.month)))}</h1>

            <table class="print-meta">
                ${identity.map(([label, value]) => `
                    <tr>
                        <th>${escapeHtml(label)}</th>
                        <td>${escapeHtml(value)}</td>
                    </tr>`).join('')}
            </table>

            <table class="print-lines">
                <thead>
                    <tr><th>Élément</th><th>Gain</th><th>Retenue</th></tr>
                </thead>
                <tbody>
                    ${lines.map(([label, amount, negative]) => `
                        <tr>
                            <td>${escapeHtml(label)}</td>
                            <td>${negative ? '' : formatMoney(amount)}</td>
                            <td>${negative ? formatMoney(amount) : ''}</td>
                        </tr>`).join('')}
                    <tr class="print-total">
                        <td>Salaire brut</td>
                        <td>${formatMoney(payslip.gross)}</td>
                        <td></td>
                    </tr>
                    <tr class="print-total">
                        <td>Net à payer</td>
                        <td>${formatMoney(payslip.net)}</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>

            ${printablePayslipEvents(payslip.staff_events)}

            ${payslip.notes ? `
                <section class="print-section">
                    <h2>Observations</h2>
                    <p>${escapeHtml(payslip.notes)}</p>
                </section>` : ''}

            <div class="print-signatures">
                <div>Signature de l'employeur</div>
                <div>Signature du salarié</div>
            </div>

            <footer class="print-foot">
                <span>${escapeHtml(payslip.member_name || '')}</span>
                <span>Édité le ${formatDate(new Date())}</span>
            </footer>
        </article>`;
}

/**
 * Retards, observations et mises à pied du mois, repris sur le bulletin.
 *
 * Une retenue s'explique par une absence, une prime par des heures faites :
 * le décompte seul ne se relit pas. Les évènements viennent du suivi du
 * personnel, le bulletin ne fait que les rappeler.
 */
function printablePayslipEvents(events) {
    if (!events?.length) return '';

    return `
        <section class="print-section">
            <h2>Retards, observations et mises à pied du mois</h2>
            <table class="print-lines print-events">
                <thead>
                    <tr><th>Nature</th><th>Date</th><th>Mesure</th><th>Motif</th></tr>
                </thead>
                <tbody>
                    ${events.map(event => `
                        <tr>
                            <td>${escapeHtml(event.kind_label)}</td>
                            <td>${escapeHtml(staffEventDates(event))}</td>
                            <td>${escapeHtml(event.summary || '—')}</td>
                            <td>${escapeHtml(event.reason || '')}</td>
                        </tr>`).join('')}
                </tbody>
            </table>
        </section>`;
}

/** Nom de fichier proposé par le navigateur, sans caractère interdit. */
function printableFileName(report) {
    const parts = [report.period_label, report.title || report.period_end];
    return parts.join(' - ').replace(/[\\/:*?"<>|]/g, '').slice(0, 120);
}

/** Document imprimable : en-tête, cartouche, puis les sections remplies. */
function buildPrintableReport(report) {
    const labels = reportForm(report.period_type);
    const meta = [
        ['Auteur', report.member_name],
        ['Pôle', capitalize(report.department || '')],
        [report.period_type === 'meeting' ? 'Date' : 'Période', reportDates(report)],
        ['Lieu', report.location],
        ['Participants', report.participants],
        ['État', report.status_label + (report.submitted_at
            ? ` le ${formatDate(report.submitted_at)}` : '')]
    ].filter(([, value]) => value);

    const sections = [
        [labels.summary, report.summary],
        [labels.achievements, report.achievements],
        [labels.blockers, report.blockers],
        ['Décisions', report.decisions],
        [labels.next_steps, report.next_steps]
    ].filter(([, value]) => value);

    return `
        <article class="print-sheet">
            <header class="print-head">
                <div class="print-brand">
                    <strong>Flux Gestion</strong>
                    <span>Suivi de performance d'équipe</span>
                </div>
                <div class="print-kind">${escapeHtml(report.period_label)}</div>
            </header>

            <h1>${escapeHtml(reportHeading(report))}</h1>

            <table class="print-meta">
                ${meta.map(([label, value]) => `
                    <tr>
                        <th>${escapeHtml(label)}</th>
                        <td>${escapeHtml(value)}</td>
                    </tr>`).join('')}
            </table>

            ${sections.map(([label, value]) => `
                <section class="print-section">
                    <h2>${escapeHtml(label)}</h2>
                    <p>${escapeHtml(value)}</p>
                </section>`).join('')}

            <footer class="print-foot">
                <span>${escapeHtml(report.member_name || '')}</span>
                <span>Édité le ${formatDate(new Date())}</span>
            </footer>
        </article>`;
}

/**
 * Temps passé sur une tâche, tel qu'il s'affiche dans sa ligne.
 *
 * Une tâche en cours compte jusqu'à maintenant, une tâche terminée s'arrête à
 * son achèvement. Le dépassement de l'estimation est signalé : c'est ce qui
 * rend la comparaison utile.
 */
function taskDuration(task) {
    if (!task.started_at || !task.duration_label) return '';

    // Les heures sont écrites en clair, pas seulement au survol : savoir
    // « de 9 h 15 à 10 h 50 » vaut autant que la durée elle-même.
    const bornes = task.status === 'done'
        ? `${formatTime(task.started_at)} → ${formatTime(task.completed_at)}`
        : `depuis ${formatTime(task.started_at)}`;
    const duree = task.duration_label + (task.status === 'done' ? '' : '…');

    return `
        · <span class="task-timer${task.over_estimate ? ' over' : ''}"
                title="Temps passé sur la tâche">
            <i class="fas fa-stopwatch"></i>
            ${escapeHtml(bornes)} · <strong>${escapeHtml(duree)}</strong>
        </span>`;
}

function reportSection(label, content) {
    if (!content) return '';
    return `
        <div class="report-section">
            <h4>${escapeHtml(label)}</h4>
            <p>${escapeHtml(content)}</p>
        </div>`;
}

function openReportModal(report = null) {
    const form = document.getElementById('reportForm');
    form.reset();

    // Par défaut, la semaine qui vient de s'écouler.
    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - 6);

    document.getElementById('reportId').value = report?.id || '';
    document.getElementById('reportPeriodType').value = report?.period_type || 'weekly';
    document.getElementById('reportStart').value =
        report?.period_start || toDateInputValue(start);
    document.getElementById('reportEnd').value =
        report?.period_end || toDateInputValue(today);
    document.getElementById('reportTitle').value = report?.title || '';
    document.getElementById('reportLocation').value = report?.location || '';
    document.getElementById('reportParticipants').value = report?.participants || '';
    document.getElementById('reportSummary').value = report?.summary || '';
    document.getElementById('reportAchievements').value = report?.achievements || '';
    document.getElementById('reportBlockers').value = report?.blockers || '';
    document.getElementById('reportDecisions').value = report?.decisions || '';
    document.getElementById('reportNextSteps').value = report?.next_steps || '';

    document.querySelector('#reportModal .modal-header h2').textContent =
        report ? 'Modifier le rapport' : 'Nouveau rapport';

    applyReportType();
    openModal('reportModal');
}

/**
 * Ajuste le formulaire au type choisi.
 *
 * Les champs d'une mission n'ont pas de sens pour un bilan hebdomadaire, et
 * une réunion se tient un jour donné : la date de fin disparaît alors.
 */
function applyReportType() {
    const periodType = document.getElementById('reportPeriodType').value;
    const labels = reportForm(periodType);
    const isEvent = isEventReport(periodType);

    document.querySelectorAll('#reportForm .event-field').forEach(group => {
        group.hidden = !isEvent;
    });

    document.getElementById('reportStartLabel').textContent = labels.start;
    document.getElementById('reportSummaryLabel').textContent = labels.summary;
    document.getElementById('reportAchievementsLabel').textContent = labels.achievements;
    document.getElementById('reportBlockersLabel').textContent = labels.blockers;
    document.getElementById('reportNextStepsLabel').textContent = labels.next_steps;

    const endGroup = document.getElementById('reportEndGroup');
    const endInput = document.getElementById('reportEnd');
    endGroup.hidden = !labels.end;
    // Un champ requis mais masqué bloquerait l'envoi sans rien signaler.
    endInput.required = Boolean(labels.end);
    if (labels.end) {
        document.getElementById('reportEndLabel').textContent = labels.end;
    }

    const titleInput = document.getElementById('reportTitle');
    titleInput.required = isEvent;
    titleInput.placeholder = periodType === 'meeting'
        ? 'Comité commercial hebdomadaire'
        : 'Mission de cadrage chez Aurore Industries';

    document.getElementById('reportSummary').placeholder = isEvent
        ? 'Ce qui a été fait, vu et dit'
        : 'Où en êtes-vous sur la période ?';
}

async function submitReport(event) {
    event.preventDefault();

    const periodType = document.getElementById('reportPeriodType').value;
    const start = document.getElementById('reportStart').value;
    const end = document.getElementById('reportEnd').value;

    const id = document.getElementById('reportId').value;
    const payload = {
        period_type: periodType,
        period_start: start,
        // Une réunion tient sur une journée : le serveur attend malgré tout
        // les deux bornes de la période.
        period_end: reportForm(periodType).end ? end : start,
        title: document.getElementById('reportTitle').value.trim(),
        location: document.getElementById('reportLocation').value.trim(),
        participants: document.getElementById('reportParticipants').value.trim(),
        summary: document.getElementById('reportSummary').value.trim(),
        achievements: document.getElementById('reportAchievements').value.trim(),
        blockers: document.getElementById('reportBlockers').value.trim(),
        decisions: document.getElementById('reportDecisions').value.trim(),
        next_steps: document.getElementById('reportNextSteps').value.trim()
    };

    try {
        if (id) {
            await reportAPI.update(id, payload);
            showToast('Rapport mis à jour', 'success');
        } else {
            await reportAPI.create(payload);
            showToast('Rapport enregistré en brouillon', 'success');
        }
        closeModal('reportModal');
        await loadReports();
    } catch (error) {
        console.error('Enregistrement du rapport:', error);
    }
}

// ===========================
// ÉQUIPE
// ===========================

async function loadTeam() {
    // Le profil n'est pas encore arrivé, ou le membre n'est pas fondateur :
    // sans ce nettoyage, les blocs d'attente scintilleraient indéfiniment.
    if (!state.profile?.is_founder) {
        document.getElementById('teamTableBody').innerHTML = '';
        return;
    }

    try {
        const month = document.getElementById('teamMonth').value;
        const data = await dashboardAPI.team(month);

        document.getElementById('teamSubtitle').textContent =
            capitalize(formatMonth(data.month));
        document.getElementById('teamRevenue').textContent =
            `${formatMoneyCompact(data.revenue_achieved)} / `
            + `${formatMoneyCompact(data.revenue_target)}`;
        document.getElementById('teamClients').textContent =
            `${data.clients_achieved} / ${data.clients_target}`;
        document.getElementById('teamCoverage').textContent =
            `${data.members_with_objective} / ${data.team_size}`;
        document.getElementById('teamAtRisk').textContent = data.members_at_risk;

        renderTeamTable(data.members);
    } catch (error) {
        console.error("Chargement de l'équipe:", error);
        showLoadError('teamTableBody', 'row');
    }
}

function renderTeamTable(members) {
    const body = document.getElementById('teamTableBody');

    if (!members.length) {
        body.innerHTML = '<tr><td colspan="7" class="text-center text-muted">Aucun membre</td></tr>';
        return;
    }

    body.innerHTML = members.map(member => `
        <tr class="${member.is_at_risk ? 'row-at-risk' : ''}">
            <td>
                <strong>${escapeHtml(member.member_name)}</strong>
                ${member.job_title
                    ? `<div class="text-muted">${escapeHtml(member.job_title)}</div>` : ''}
            </td>
            <td>${escapeHtml(member.department)}</td>
            <td>
                ${member.has_objective
                    ? `${formatMoneyCompact(member.revenue_achieved)}
                       <small class="text-muted">
                           / ${formatMoneyCompact(member.revenue_target)}</small>`
                    : '<span class="text-muted">non défini</span>'}
            </td>
            <td>${member.has_objective
                    ? `${member.clients_achieved} / ${member.clients_target}` : '—'}</td>
            <td>
                ${member.completion !== null ? `
                    <div class="progress progress-slim">
                        <div class="progress-fill ${member.is_at_risk ? 'behind' : ''}"
                             style="width:${Math.min(member.completion, 100)}%"></div>
                    </div>
                    <small>${formatPercent(member.completion)}</small>` : '—'}
            </td>
            <td>${member.open_tasks}</td>
            <td>${member.reports_submitted}</td>
        </tr>
    `).join('');
}

// ===========================
// NAVIGATION ET ÉVÉNEMENTS
// ===========================

function emptyState(icon, title, message) {
    return `
        <div class="empty-state">
            <i class="fas ${icon}"></i>
            <h3>${escapeHtml(title)}</h3>
            <p class="text-muted">${escapeHtml(message)}</p>
        </div>`;
}

/**
 * Remplace les squelettes par un message d'échec.
 *
 * Sans cela, une API injoignable laissait les blocs d'attente scintiller
 * indéfiniment : rien ne distinguait un chargement lent d'un serveur éteint.
 *
 * @param {string} containerId - Le conteneur à remplir
 * @param {string} variant - `card` pour une liste, `row` pour un tableau
 */
function showLoadError(containerId, variant = 'card') {
    const container = document.getElementById(containerId);
    if (!container) return;

    const content = `
        <div class="empty-state">
            <i class="fas fa-plug-circle-xmark"></i>
            <h3>Chargement impossible</h3>
            <p class="text-muted">Le serveur n'a pas répondu.</p>
            <button class="btn btn-small btn-secondary retry-load">
                <i class="fas fa-rotate-right"></i> Réessayer
            </button>
        </div>`;

    container.innerHTML = variant === 'row'
        ? `<tr><td colspan="7">${content}</td></tr>`
        : content;

    container.querySelector('.retry-load')
        ?.addEventListener('click', refreshCurrentPage);
}

// ===========================
// RÉACTIONS ET POINTS
// ===========================

/** Habillage des natures de réaction ; le barème vient du serveur. */
const REACTION_ICONS = {
    objectif: 'fa-bullseye', bravo: 'fa-star', entraide: 'fa-hands-helping',
    initiative: 'fa-lightbulb', rappel: 'fa-hand', manquement: 'fa-triangle-exclamation'
};

/**
 * Charge le barème une fois par session.
 *
 * Les natures et leurs points vivent côté serveur : les recopier ici ferait
 * diverger l'interface du jour où le barème changerait.
 */
async function loadReactionScale() {
    if (state.reactionScale) return state.reactionScale;
    try {
        state.reactionScale = await reactionAPI.scale();
    } catch (error) {
        console.error('Chargement du barème:', error);
        state.reactionScale = { point_value: 0, kinds: [] };
    }
    return state.reactionScale;
}

async function openReactionModal(membre) {
    const bareme = await loadReactionScale();

    document.getElementById('reactionForm').reset();
    document.getElementById('reactionMember').value = membre.member_id || membre.id;
    setText('reactionMemberName', membre.member_name || membre.display_name);
    document.getElementById('reactionDate').value = toDateInputValue(new Date());

    document.getElementById('reactionPicker').innerHTML = bareme.kinds.map(nature => `
        <button type="button" class="reaction-choice${nature.points < 0 ? ' negative' : ''}"
                data-kind="${escapeHtml(nature.kind)}" data-points="${nature.points}">
            <i class="fas ${REACTION_ICONS[nature.kind] || 'fa-star'}"></i>
            <span>${escapeHtml(nature.label)}</span>
            <strong>${nature.points > 0 ? '+' : ''}${nature.points}</strong>
        </button>`).join('');

    document.querySelectorAll('#reactionPicker .reaction-choice').forEach(bouton => {
        bouton.addEventListener('click', () => selectReactionKind(bouton));
    });

    const premier = document.querySelector('#reactionPicker .reaction-choice');
    if (premier) selectReactionKind(premier);

    openModal('reactionModal');
}

/** Retient la nature choisie et propose ses points, encore ajustables. */
function selectReactionKind(bouton) {
    document.querySelectorAll('#reactionPicker .reaction-choice')
        .forEach(autre => autre.classList.toggle('active', autre === bouton));
    document.getElementById('reactionPoints').value = bouton.dataset.points;
    updateReactionValue();
}

/** Traduit les points en francs, pour que le geste ait un montant. */
function updateReactionValue() {
    const points = Number(document.getElementById('reactionPoints').value) || 0;
    const valeur = points * (state.reactionScale?.point_value || 0);
    setText('reactionValueHint', points
        ? `${points > 0 ? '+' : ''}${points} point(s) — ${formatMoney(valeur)} de prime`
        : 'Une réaction accorde ou retire des points, jamais zéro.');
}

async function submitReaction(event) {
    event.preventDefault();

    const choix = document.querySelector('#reactionPicker .reaction-choice.active');
    if (!choix) return;

    const payload = {
        member: Number(document.getElementById('reactionMember').value),
        kind: choix.dataset.kind,
        points: Number(document.getElementById('reactionPoints').value),
        date: document.getElementById('reactionDate').value,
        reason: document.getElementById('reactionReason').value.trim()
    };

    try {
        await reactionAPI.create(payload);
        showToast(payload.points > 0
            ? `${payload.points} points accordés` : `${-payload.points} points retirés`,
            'success');
        closeModal('reactionModal');
        await refreshCurrentPage();
    } catch (error) {
        console.error("Enregistrement de la réaction:", error);
    }
}

/** Liste des réactions reçues, telle qu'elle apparaît dans le profil. */
function renderReactions(reactions) {
    const container = document.getElementById('profileReactions');

    if (!reactions.length) {
        container.innerHTML =
            '<p class="text-muted">Aucune réaction reçue pour le moment.</p>';
        return;
    }

    container.innerHTML = reactions.slice(0, 8).map(reaction => `
        <div class="reaction-item ${reaction.is_positive ? '' : 'negative'}">
            <i class="fas ${REACTION_ICONS[reaction.kind] || 'fa-star'}"></i>
            <div>
                <strong>${escapeHtml(reaction.kind_label)}</strong>
                ${reaction.reason
                    ? `<span class="text-muted"> — ${escapeHtml(reaction.reason)}</span>`
                    : ''}
                <small class="text-muted">
                    ${escapeHtml(formatDate(reaction.date))}
                    ${reaction.author_name
                        ? ` · par ${escapeHtml(reaction.author_name)}` : ''}
                </small>
            </div>
            <span class="reaction-points">
                ${reaction.points > 0 ? '+' : ''}${reaction.points}
            </span>
        </div>`).join('');
}

// ===========================
// MON PROFIL
// ===========================

/**
 * Ouvre la fiche personnelle.
 *
 * Le profil vient de l'état chargé au démarrage ; seuls les bulletins sont
 * relus, parce qu'un bulletin peut être remis entre deux ouvertures.
 */
async function openProfileModal() {
    const profil = state.profile;
    if (!profil) return;

    setText('profileName', profil.display_name || profil.username);
    setText('profileTitle', profil.job_title || profil.role_label || '');
    setText('profileUsername', profil.username);
    setText('profileEmail', profil.email || '—');
    setText('profileDepartment', profil.department || '—');
    setText('profileJob', profil.job_title || '—');

    const badge = document.getElementById('profileRole');
    const rang = roleProfile(profil.role);
    badge.textContent = rang.label;
    badge.className = `status-badge ${rang.tone}`;

    document.getElementById('passwordForm').reset();
    openModal('profileModal');

    await Promise.all([loadProfileDetails(), loadOwnPayslips(), loadOwnReactions()]);
}

/** Complète la fiche avec ce que le profil de session ne porte pas. */
async function loadProfileDetails() {
    try {
        const membre = await memberAPI.me();
        setText('profilePhone', membre.phone || '—');
        setText('profileJoined', formatDate(membre.joined_on));
        setText('profileDepartment', membre.department_label || '—');

        setText('profileSalary', formatMoney(membre.base_salary));
        setText('profilePoints', `${membre.points_month > 0 ? '+' : ''}`
            + `${membre.points_month} pt`);
        setText('profileBonus', formatMoney(membre.bonus_earned));

        setText('profileLeaveBalance', `${formatNumber(membre.leave_balance, 1)} j`);
        setText('profileLeaveTaken',
            `${formatNumber(membre.leave_days_taken, 1)} / ${membre.leave_entitlement} j`);

        // La présence du mois vient du pointage déjà relu pour la barre du
        // haut : la fiche n'a pas à redemander la même chose.
        const mois = state.punch?.month;
        setText('profileAttendance', mois
            ? `${formatNumber(mois.hours, 1)} h · ${mois.days} jour(s)` : '—');
        setText('profileLate', mois ? formatDuration(mois.late_minutes) : '—');
    } catch (error) {
        console.error('Chargement du profil:', error);
    }
}

async function loadOwnReactions() {
    try {
        renderReactions(await reactionAPI.getAll());
    } catch (error) {
        console.error('Chargement des réactions:', error);
    }
}

/**
 * Charge les bulletins de paie du membre connecté.
 *
 * L'API ne renvoie que les siens, et seulement ceux qui lui ont été remis :
 * le filtrage est côté serveur, pas ici.
 */
async function loadOwnPayslips() {
    const container = document.getElementById('profilePayslips');
    showSkeleton('profilePayslips', 2, 'card');

    try {
        renderOwnPayslips(await payslipAPI.getAll());
    } catch (error) {
        console.error('Chargement de la rémunération:', error);
        showLoadError('profilePayslips');
    }
}

function renderOwnPayslips(bulletins) {
    const container = document.getElementById('profilePayslips');

    if (!bulletins.length) {
        container.innerHTML = `
            <p class="text-muted">
                Aucun bulletin de paie ne vous a encore été remis.
            </p>`;
        return;
    }

    const dernier = bulletins[0];

    container.innerHTML = `
        <div class="profile-pay-head">
            <div>
                <span class="report-kind">
                    ${escapeHtml(capitalize(formatMonth(dernier.month)))}
                </span>
                <strong>${escapeHtml(formatMoney(dernier.net))}</strong>
                <span class="text-muted">net à payer</span>
            </div>
            <button class="btn btn-small btn-secondary" id="profilePayPdf">
                <i class="fas fa-file-pdf"></i> Exporter en PDF
            </button>
        </div>

        <div class="payslip-lines">
            ${Number(dernier.worked_hours)
                ? payslipTextLine('Heures travaillées',
                                  `${formatNumber(dernier.worked_hours, 2)} h`)
                : ''}
            ${payslipLine('Salaire de base', dernier.base_salary)}
            ${Number(dernier.overtime_amount)
                ? payslipLine(
                    `Heures sup. (${formatNumber(dernier.overtime_hours, 2)} h)`,
                    dernier.overtime_amount)
                : ''}
            ${Number(dernier.bonuses) ? payslipLine('Primes', dernier.bonuses) : ''}
            ${Number(dernier.deductions)
                ? payslipLine('Retenues', dernier.deductions, true) : ''}
            ${Number(dernier.contributions)
                ? payslipLine('Cotisations', dernier.contributions, true) : ''}
            <div class="payslip-line total">
                <span>Net à payer</span>
                <strong>${formatMoney(dernier.net)}</strong>
            </div>
        </div>

        ${payslipEventsSection(dernier.staff_events)}

        ${bulletins.length > 1 ? `
            <h5 class="profile-pay-history">Bulletins précédents</h5>
            <ul class="profile-pay-list">
                ${bulletins.slice(1, 7).map(bulletin => `
                    <li data-id="${bulletin.id}">
                        <span>${escapeHtml(capitalize(formatMonth(bulletin.month)))}</span>
                        <strong>${escapeHtml(formatMoney(bulletin.net))}</strong>
                        <button class="btn-icon export-own-payslip"
                                title="Exporter en PDF">
                            <i class="fas fa-file-pdf"></i>
                        </button>
                    </li>`).join('')}
            </ul>` : ''}`;

    document.getElementById('profilePayPdf')
        .addEventListener('click', () => exportPayslipToPdf(dernier));

    container.querySelectorAll('.export-own-payslip').forEach(bouton => {
        bouton.addEventListener('click', () => {
            const id = Number(bouton.closest('li').dataset.id);
            exportPayslipToPdf(bulletins.find(b => b.id === id));
        });
    });
}

async function submitPassword(event) {
    event.preventDefault();

    const actuel = document.getElementById('passwordCurrent').value;
    const nouveau = document.getElementById('passwordNew').value;
    const confirmation = document.getElementById('passwordConfirm').value;

    // La confirmation se vérifie ici : inutile d'aller au serveur pour une
    // faute de frappe.
    if (nouveau !== confirmation) {
        showToast('Les deux nouveaux mots de passe diffèrent', 'error');
        return;
    }

    try {
        // Le serveur révoque l'ancien jeton : `authAPI` enregistre le nouveau,
        // sans quoi la session serait perdue dès la requête suivante.
        await authAPI.changePassword(actuel, nouveau);
        showToast('Mot de passe changé', 'success');
        document.getElementById('passwordForm').reset();
    } catch (error) {
        console.error('Changement de mot de passe:', error);
    }
}

// ===========================
// UTILISATEURS (fondateurs)
// ===========================

/** Ce que chaque profil ouvre réellement, dit au moment du choix. */
const ROLE_PROFILES = {
    member: {
        label: 'Employé', family: 'Profil employé', tone: 'status-todo',
        hint: "Ses objectifs, sa feuille de route, ses tâches et ses rapports. "
            + "Il ne voit rien des autres."
    },
    manager: {
        label: 'Gérant', family: 'Profil administratif', tone: 'status-progress',
        hint: "Tout ce que voit un fondateur, plus les bulletins de paie et le "
            + "suivi du personnel."
    },
    founder: {
        label: 'Fondateur', family: 'Profil administratif', tone: 'status-done',
        hint: "Toute l'équipe, le panel de suivi et l'administration des comptes."
    }
};

const DEPARTMENTS = [
    ['direction', 'Direction'], ['commercial', 'Commercial'],
    ['marketing', 'Marketing'], ['produit', 'Produit'],
    ['technique', 'Technique'], ['finance', 'Finance'],
    ['operations', 'Opérations']
];

function roleProfile(role) {
    return ROLE_PROFILES[role] || ROLE_PROFILES.member;
}

async function loadAccounts() {
    if (!state.profile?.is_founder) {
        document.getElementById('accountsTableBody').innerHTML = '';
        return;
    }

    try {
        const comptes = await memberAPI.getAll({
            search: document.getElementById('accountSearch').value.trim(),
            role: document.getElementById('accountRoleFilter').value,
            department: document.getElementById('accountDepartmentFilter').value
        });
        renderAccounts(comptes);
    } catch (error) {
        console.error('Chargement des utilisateurs:', error);
        showLoadError('accountsTableBody', 'row');
    }
}

function renderAccounts(comptes) {
    const container = document.getElementById('accountsTableBody');
    setText('accountsSubtitle',
        `${comptes.length} compte(s) · `
        + `${comptes.filter(c => c.role !== 'member').length} profil(s) administratif(s)`);

    if (!comptes.length) {
        container.innerHTML =
            '<tr><td colspan="6" class="text-center text-muted">Aucun compte</td></tr>';
        return;
    }

    const moi = state.profile?.member_id;

    container.innerHTML = comptes.map(compte => {
        const profil = roleProfile(compte.role);
        return `
        <tr data-id="${compte.id}" class="${compte.is_active ? '' : 'account-off'}">
            <td>
                <strong>${escapeHtml(compte.display_name)}</strong>
                <div class="text-muted">${escapeHtml(compte.username)}</div>
            </td>
            <td>
                <span class="status-badge ${profil.tone}">
                    ${escapeHtml(profil.label)}
                </span>
            </td>
            <td>${escapeHtml(compte.department_label || '')}</td>
            <td>${escapeHtml(compte.job_title || '—')}</td>
            <td>${compte.is_active
                    ? '<span class="text-muted">Actif</span>'
                    : '<strong class="text-danger">Désactivé</strong>'}</td>
            <td>
                <div class="row-actions">
                    <button class="btn-icon edit-account" title="Modifier">
                        <i class="fas fa-pen"></i>
                    </button>
                    <button class="btn-icon reset-account" title="Réinitialiser le mot de passe">
                        <i class="fas fa-key"></i>
                    </button>
                    ${compte.id === moi ? '' : `
                        <button class="btn-icon toggle-account"
                                title="${compte.is_active ? 'Désactiver' : 'Réactiver'}">
                            <i class="fas ${compte.is_active
                                ? 'fa-user-slash' : 'fa-user-check'}"></i>
                        </button>
                        <button class="btn-icon delete-account" title="Supprimer">
                            <i class="fas fa-trash"></i>
                        </button>`}
                </div>
            </td>
        </tr>`;
    }).join('');

    const compteDe = (bouton) =>
        comptes.find(c => c.id === Number(bouton.closest('tr').dataset.id));

    container.querySelectorAll('.edit-account').forEach(bouton => {
        bouton.addEventListener('click', () => openAccountModal(compteDe(bouton)));
    });

    container.querySelectorAll('.toggle-account').forEach(bouton => {
        bouton.addEventListener('click', async () => {
            const compte = compteDe(bouton);
            try {
                await memberAPI.setActive(compte.id, !compte.is_active);
                showToast(compte.is_active ? 'Compte désactivé' : 'Compte réactivé',
                          'success');
                forgetStaffMembers();
                await loadAccounts();
            } catch (error) {
                console.error('Changement d\'état du compte:', error);
            }
        });
    });

    container.querySelectorAll('.reset-account').forEach(bouton => {
        bouton.addEventListener('click', async () => {
            const compte = compteDe(bouton);
            if (!confirm(`Engendrer un nouveau mot de passe pour `
                + `${compte.display_name} ? L'ancien cessera de fonctionner.`)) return;
            try {
                const maj = await memberAPI.resetPassword(compte.id);
                showGeneratedPassword(maj);
            } catch (error) {
                console.error('Réinitialisation du mot de passe:', error);
            }
        });
    });

    container.querySelectorAll('.delete-account').forEach(bouton => {
        bouton.addEventListener('click', async () => {
            const compte = compteDe(bouton);
            // La suppression emporte l'historique : mieux vaut le dire avant.
            if (!confirm(`Supprimer définitivement ${compte.display_name} ?\n\n`
                + `Ses objectifs, tâches, rapports et bulletins partent avec le `
                + `compte. Pour lui retirer l'accès sans rien perdre, désactivez-le `
                + `plutôt.`)) return;
            try {
                await memberAPI.delete(compte.id);
                showToast('Compte supprimé', 'success');
                forgetStaffMembers();
                await loadAccounts();
            } catch (error) {
                console.error('Suppression du compte:', error);
            }
        });
    });
}

/**
 * Affiche un mot de passe engendré.
 *
 * C'est la seule fois où il est lisible : il n'est jamais stocké en clair, et
 * une notification passagère le ferait disparaître trop vite pour être noté.
 */
/**
 * Montre une seule fois le mot de passe engendré par le serveur.
 *
 * Une fenêtre de l'application plutôt qu'un dialogue natif : le texte d'un
 * `alert` ne se sélectionne pas dans les navigateurs récents, et un navigateur
 * réglé pour bloquer les dialogues le ferait disparaître sans recours — le
 * compte existerait alors avec un mot de passe que personne ne connaît.
 */
function showGeneratedPassword(compte) {
    if (!compte.generated_password) return;

    setText('credentialName', compte.display_name || compte.username);
    setText('credentialUsername', compte.username ? `· ${compte.username}` : '');
    document.getElementById('credentialValue').value = compte.generated_password;

    openModal('credentialModal');
}

/**
 * Copie le mot de passe, en retombant sur la sélection si le presse-papiers
 * est refusé — hors HTTPS, le navigateur le refuse souvent.
 */
async function copyGeneratedPassword() {
    const champ = document.getElementById('credentialValue');

    try {
        await navigator.clipboard.writeText(champ.value);
        showToast('Mot de passe copié', 'success');
    } catch (error) {
        champ.select();
        showToast('Sélectionné : copiez-le avec Ctrl+C', 'info');
    }
}

function openAccountModal(compte = null) {
    const form = document.getElementById('accountForm');
    form.reset();

    document.getElementById('accountId').value = compte?.id || '';
    document.getElementById('accountFirstName').value = compte?.first_name || '';
    document.getElementById('accountLastName').value = compte?.last_name || '';
    document.getElementById('accountUsername').value = compte?.username || '';
    document.getElementById('accountEmail').value = compte?.email || '';
    document.getElementById('accountRole').value = compte?.role || 'member';
    document.getElementById('accountDepartment').value =
        compte?.department || 'commercial';
    document.getElementById('accountJobTitle').value = compte?.job_title || '';
    document.getElementById('accountPhone').value = compte?.phone || '';
    document.getElementById('accountSalary').value = Number(compte?.base_salary || 0);
    document.getElementById('accountPassword').value = '';

    setText('accountPasswordLabel',
        compte ? 'Nouveau mot de passe' : 'Mot de passe');
    setText('accountPasswordHint', compte
        ? "Laissez vide pour ne pas y toucher."
        : "Laissez vide : un mot de passe est engendré et affiché une fois.");

    document.querySelector('#accountModal .modal-header h2').textContent =
        compte ? 'Modifier le compte' : 'Nouvel utilisateur';

    applyAccountRole();
    openModal('accountModal');
}

/** Rappelle ce que le profil choisi ouvre réellement. */
function applyAccountRole() {
    setText('accountRoleHint', roleProfile(document.getElementById('accountRole').value).hint);
}

async function submitAccount(event) {
    event.preventDefault();

    const id = document.getElementById('accountId').value;
    const motdepasse = document.getElementById('accountPassword').value.trim();

    const payload = {
        username: document.getElementById('accountUsername').value.trim(),
        email: document.getElementById('accountEmail').value.trim(),
        first_name: document.getElementById('accountFirstName').value.trim(),
        last_name: document.getElementById('accountLastName').value.trim(),
        role: document.getElementById('accountRole').value,
        department: document.getElementById('accountDepartment').value,
        job_title: document.getElementById('accountJobTitle').value.trim(),
        phone: document.getElementById('accountPhone').value.trim(),
        base_salary: document.getElementById('accountSalary').value || 0
    };
    if (motdepasse) payload.password = motdepasse;

    try {
        if (id) {
            await memberAPI.update(id, payload);
            showToast('Compte mis à jour', 'success');
        } else {
            const cree = await memberAPI.create(payload);
            showToast('Compte créé', 'success');
            showGeneratedPassword(cree);
        }
        forgetStaffMembers();
        closeModal('accountModal');
        await loadAccounts();
    } catch (error) {
        console.error('Enregistrement du compte:', error);
    }
}

// ===========================
// PANEL DU FONDATEUR
// ===========================

/** Intervalle de relecture du panel, en millisecondes. */
const PANEL_REFRESH_MS = 30000;

/** Habillage de chaque état de membre. */
const PANEL_STATES = {
    working: { label: 'Au travail', tone: 'status-progress', icon: 'fa-person-running' },
    idle: { label: 'Rien d\'entamé', tone: 'status-blocked', icon: 'fa-pause' },
    no_tasks: { label: 'Aucune tâche', tone: 'status-draft', icon: 'fa-circle-minus' },
    done: { label: 'Journée faite', tone: 'status-done', icon: 'fa-circle-check' },
    on_leave: { label: 'En congé', tone: 'status-draft', icon: 'fa-umbrella-beach' }
};

async function loadPanel() {
    if (!state.profile?.is_founder) {
        document.getElementById('panelTableBody').innerHTML = '';
        return;
    }

    await refreshPanel();
    schedulePanelRefresh();
}

/**
 * Relance la relecture périodique, ou l'arrête si le suivi est décoché.
 *
 * Le panel est le seul écran qui se relit tout seul : ailleurs, une requête
 * de fond toutes les trente secondes ne servirait à rien.
 */
function schedulePanelRefresh() {
    stopPanelRefresh();
    if (!document.getElementById('panelAuto').checked) return;

    state.panelTimer = setInterval(() => refreshPanel(true), PANEL_REFRESH_MS);
    document.getElementById('panelDot').hidden = false;
}

function stopPanelRefresh() {
    if (state.panelTimer) {
        clearInterval(state.panelTimer);
        state.panelTimer = null;
    }
    document.getElementById('panelDot').hidden = true;
}

async function refreshPanel(quiet = false) {
    try {
        renderPanel(await dashboardAPI.panel(quiet));
    } catch (error) {
        console.error('Chargement du panel:', error);
        if (!quiet) showLoadError('panelTableBody', 'row');
    }
}

function renderPanel(panel) {
    const totaux = panel.totals;

    setText('panelSubtitle',
        `${capitalize(formatDate(panel.date))} — ${totaux.team_size} membre(s) suivis, `
        + `${totaux.checked_in} pointage(s)`
        + (totaux.on_leave ? `, ${totaux.on_leave} en congé` : ''));
    setText('panelWorking', `${totaux.working} / ${totaux.team_size}`);
    setText('panelLogged', formatDuration(totaux.minutes_logged));
    setText('panelTasks', `${totaux.tasks_done} / ${totaux.tasks_total}`);
    setText('panelIdle', totaux.idle);
    setText('panelStamp', `Relevé à ${formatTime(panel.generated_at)}`);

    renderPanelTable(panel.members);
    renderPanelReports(panel.recent_reports);
}

function renderPanelTable(membres) {
    const container = document.getElementById('panelTableBody');

    if (!membres.length) {
        container.innerHTML =
            '<tr><td colspan="6" class="text-center text-muted">Aucun membre actif</td></tr>';
        return;
    }

    container.innerHTML = membres.map(ligne => {
        const etat = PANEL_STATES[ligne.status] || PANEL_STATES.no_tasks;
        const tache = ligne.current_task;

        return `
        <tr class="panel-row ${escapeHtml(ligne.status)}" data-id="${ligne.member_id}">
            <td>
                <strong>${escapeHtml(ligne.member_name)}</strong>
                ${ligne.job_title
                    ? `<div class="text-muted">${escapeHtml(ligne.job_title)}</div>` : ''}
            </td>
            <td>
                <span class="status-badge ${etat.tone}">
                    <i class="fas ${etat.icon}"></i> ${escapeHtml(etat.label)}
                </span>
                ${ligne.on_leave
                    ? `<div class="text-muted">${escapeHtml(ligne.on_leave)}</div>` : ''}
            </td>
            <td>
                ${tache ? `
                    <div>${escapeHtml(tache.title)}</div>
                    <small class="task-timer${tache.over_estimate ? ' over' : ''}">
                        <i class="fas fa-stopwatch"></i>
                        depuis ${escapeHtml(formatTime(tache.started_at))} ·
                        <strong>${escapeHtml(tache.duration_label)}…</strong>
                    </small>`
                    : '<span class="text-muted">—</span>'}
            </td>
            <td>
                ${ligne.minutes_logged
                    ? escapeHtml(formatDuration(ligne.minutes_logged))
                    : '<span class="text-muted">—</span>'}
                ${ligne.attendance ? `
                    <div class="text-muted">
                        <i class="fas fa-fingerprint"></i>
                        ${escapeHtml(formatTime(ligne.attendance.check_in))}
                        ${ligne.attendance.is_open
                            ? '' : ` → ${escapeHtml(formatTime(ligne.attendance.check_out))}`}
                        ${ligne.attendance.late_minutes
                            ? ` · <span class="text-danger">+${ligne.attendance.late_minutes} min</span>`
                            : ''}
                    </div>` : ''}
            </td>
            <td>${ligne.tasks_done} / ${ligne.tasks_total}</td>
            <td>${ligne.tasks_late
                    ? `<strong class="text-danger">${ligne.tasks_late}</strong>`
                    : '<span class="text-muted">0</span>'}</td>
            <td>
                <strong class="${ligne.points_month < 0 ? 'text-danger' : ''}">
                    ${ligne.points_month > 0 ? '+' : ''}${ligne.points_month}
                </strong>
                <div class="text-muted">${escapeHtml(formatMoney(ligne.bonus_earned))}</div>
            </td>
            <td>
                <button class="btn btn-small btn-secondary react-member"
                        title="Accorder ou retirer des points">
                    <i class="fas fa-star"></i> Réagir
                </button>
            </td>
        </tr>`;
    }).join('');

    container.querySelectorAll('.react-member').forEach(bouton => {
        bouton.addEventListener('click', () => {
            const id = Number(bouton.closest('tr').dataset.id);
            openReactionModal(membres.find(m => m.member_id === id));
        });
    });
}

function renderPanelReports(rapports) {
    const container = document.getElementById('panelReports');

    if (!rapports.length) {
        container.innerHTML = emptyState(
            'fa-file-lines', 'Aucun rapport reçu',
            "Les bilans, missions et comptes rendus de l'équipe arrivent ici."
        );
        return;
    }

    container.innerHTML = rapports.map(rapport => `
        <button type="button" class="panel-report" data-id="${rapport.id}">
            <span class="report-kind">${escapeHtml(rapport.period_label)}</span>
            <strong>${escapeHtml(rapport.title || reportDates(rapport))}</strong>
            <span class="text-muted">
                ${escapeHtml(rapport.member_name)} ·
                ${rapport.submitted_at
                    ? `soumis ${escapeHtml(timeAgo(rapport.submitted_at))}`
                    : 'brouillon'}
            </span>
            <p>${escapeHtml(rapport.summary)}</p>
        </button>`).join('');

    // Un rapport ouvre son document imprimable : c'est ce qu'un fondateur en
    // fait le plus souvent, le lire en entier ou l'archiver.
    container.querySelectorAll('.panel-report').forEach(bouton => {
        bouton.addEventListener('click', () => {
            const id = Number(bouton.dataset.id);
            exportReportToPdf(rapports.find(r => r.id === id));
        });
    });
}

// ===========================
// NOTIFICATIONS ET SUGGESTIONS
// ===========================

/** Habillage de chaque nature d'alerte. */
const NOTIF_STYLES = {
    objective_missing: { icon: 'fa-bullseye' },
    objective_at_risk: { icon: 'fa-triangle-exclamation' },
    tasks_late: { icon: 'fa-clock' },
    roadmap_overdue: { icon: 'fa-route' },
    suggestions_new: { icon: 'fa-lightbulb' },
    attendance_missing: { icon: 'fa-fingerprint' },
    attendance_open: { icon: 'fa-hourglass-half' },
    leaves_pending: { icon: 'fa-umbrella-beach' }
};

/**
 * Relit les alertes et met à jour la cloche.
 *
 * Rien n'est stocké côté serveur : chaque ligne décrit une situation vérifiée
 * à l'instant. Une tâche rattrapée fait disparaître son alerte d'elle-même,
 * ce qui évite un « marquer comme lu » qui ne voudrait rien dire.
 */
async function loadNotifications() {
    try {
        const flux = await dashboardAPI.notifications();
        renderNotifications(flux);
    } catch (error) {
        console.error('Chargement des notifications:', error);
    }
}

function renderNotifications(flux) {
    const badge = document.getElementById('notifBadge');
    badge.textContent = flux.count > 99 ? '99+' : flux.count;
    badge.hidden = flux.count === 0;

    // La cloche connaît les congés en attente de l'équipe : le rail les montre
    // sans qu'il faille ouvrir la page pour le découvrir.
    if (state.profile?.is_founder) {
        updateLeaveBadge(flux.items.find(a => a.kind === 'leaves_pending')?.count || 0);
    }

    const container = document.getElementById('notifList');
    if (!flux.items.length) {
        container.innerHTML = `
            <p class="notif-empty">
                <i class="fas fa-circle-check"></i> Rien à signaler.
            </p>`;
        return;
    }

    container.innerHTML = flux.items.map(alerte => `
        <button type="button" class="notif-item ${escapeHtml(alerte.level)}"
                data-page="${escapeHtml(alerte.page || '')}"
                data-kind="${escapeHtml(alerte.kind)}">
            <i class="fas ${NOTIF_STYLES[alerte.kind]?.icon || 'fa-circle-info'}"></i>
            <span>
                <strong>${escapeHtml(alerte.title)}</strong>
                <small>${escapeHtml(alerte.detail)}</small>
            </span>
        </button>`).join('');

    container.querySelectorAll('.notif-item').forEach(bouton => {
        bouton.addEventListener('click', async () => {
            toggleNotifications(false);
            // Les suggestions n'ont pas de page : elles s'ouvrent dans leur boîte.
            if (bouton.dataset.kind === 'suggestions_new') {
                await openSuggestionModal();
            } else if (bouton.dataset.page) {
                await openPage(bouton.dataset.page);
            }
        });
    });
}

/** Ouvre ou ferme le panneau de la cloche. */
function toggleNotifications(open) {
    const panneau = document.getElementById('notifPanel');
    const ouvert = open === undefined ? panneau.hidden : open;
    panneau.hidden = !ouvert;
    if (ouvert) loadNotifications();
}

/** Ouvre la boîte à suggestions ; la direction y voit aussi les messages reçus. */
async function openSuggestionModal() {
    const form = document.getElementById('suggestionForm');
    form.reset();
    openModal('suggestionModal');

    if (state.profile?.is_founder) await loadSuggestions();
}

async function loadSuggestions() {
    const container = document.getElementById('suggestionList');
    showSkeleton('suggestionList', 2, 'card');

    try {
        renderSuggestions(await suggestionAPI.getAll());
    } catch (error) {
        console.error('Chargement des suggestions:', error);
        showLoadError('suggestionList');
    }
}

function renderSuggestions(suggestions) {
    const container = document.getElementById('suggestionList');

    if (!suggestions.length) {
        container.innerHTML =
            '<p class="text-muted">Aucune suggestion pour le moment.</p>';
        return;
    }

    container.innerHTML = suggestions.map(suggestion => `
        <div class="suggestion-card ${suggestion.status === 'new' ? 'unread' : ''}"
             data-id="${suggestion.id}">
            <div class="suggestion-head">
                <div>
                    <span class="report-kind">${escapeHtml(suggestion.category_label)}</span>
                    <strong>${escapeHtml(suggestion.author_name)}</strong>
                    <span class="text-muted"> · ${escapeHtml(timeAgo(suggestion.created_at))}</span>
                </div>
                <span class="status-badge ${suggestion.status === 'new'
                    ? 'status-todo' : 'status-done'}">
                    ${escapeHtml(suggestion.status_label)}
                </span>
            </div>
            <p class="suggestion-message">${escapeHtml(suggestion.message)}</p>
            ${suggestion.reply ? `
                <p class="suggestion-reply">
                    <strong>Réponse</strong>${escapeHtml(suggestion.handled_by_name
                        ? ` de ${suggestion.handled_by_name}` : '')} :
                    ${escapeHtml(suggestion.reply)}
                </p>` : ''}
            ${suggestion.status !== 'done' ? `
                <div class="suggestion-actions">
                    <input type="text" class="input-field suggestion-reply-input"
                           placeholder="Répondre (facultatif)">
                    <button class="btn btn-small btn-success handle-suggestion">
                        <i class="fas fa-check"></i> Traiter
                    </button>
                </div>` : ''}
        </div>`).join('');

    container.querySelectorAll('.handle-suggestion').forEach(bouton => {
        bouton.addEventListener('click', async () => {
            const carte = bouton.closest('.suggestion-card');
            const reponse = carte.querySelector('.suggestion-reply-input').value.trim();
            try {
                await suggestionAPI.handle(Number(carte.dataset.id), 'done', reponse);
                showToast('Suggestion traitée', 'success');
                await Promise.all([loadSuggestions(), loadNotifications()]);
            } catch (error) {
                console.error('Traitement de la suggestion:', error);
            }
        });
    });
}

async function submitSuggestion(event) {
    event.preventDefault();

    const payload = {
        category: document.getElementById('suggestionCategory').value,
        message: document.getElementById('suggestionMessage').value.trim()
    };

    try {
        await suggestionAPI.create(payload);
        showToast('Merci, votre suggestion est envoyée', 'success');
        document.getElementById('suggestionForm').reset();
        // La direction voit sa boîte se remplir sans rouvrir la fenêtre.
        if (state.profile?.is_founder) {
            await Promise.all([loadSuggestions(), loadNotifications()]);
        }
    } catch (error) {
        console.error("Envoi de la suggestion:", error);
    }
}

// ===========================
// CONGÉS
// ===========================

/** Habillage de chaque nature de congé. */
const LEAVE_KINDS = {
    paid: { icon: 'fa-umbrella-beach', tone: 'status-progress' },
    unpaid: { icon: 'fa-calendar-minus', tone: 'status-draft' },
    sick: { icon: 'fa-notes-medical', tone: 'status-todo' },
    special: { icon: 'fa-user-clock', tone: 'status-draft' }
};

/** Couleur de l'état d'une demande. */
const LEAVE_STATUS_CLASS = {
    pending: 'status-todo',
    approved: 'status-done',
    refused: 'status-blocked',
    cancelled: 'status-draft'
};

function leaveKind(kind) {
    return LEAVE_KINDS[kind] || LEAVE_KINDS.special;
}

/**
 * Jours ouvrables entre deux dates, bornes comprises.
 *
 * Le serveur fait foi ; ce calcul ne sert qu'à annoncer la durée pendant la
 * saisie, avant tout envoi.
 */
function workingDays(debut, fin) {
    const start = new Date(debut);
    const end = new Date(fin);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
        return 0;
    }

    let total = 0;
    for (let jour = new Date(start); jour <= end; jour.setDate(jour.getDate() + 1)) {
        const semaine = jour.getDay();
        if (semaine !== 0 && semaine !== 6) total += 1;
    }
    return total;
}

/**
 * Charge les congés de l'année et le solde.
 *
 * L'année entière tient en mémoire : les compteurs du haut de page ont besoin
 * de tout le jeu, les filtres se contentent donc de trier ce qui est déjà là.
 */
async function loadLeaves() {
    const annee = new Date().getFullYear();
    const membres = state.profile?.is_founder ? loadLeaveMembers() : null;

    try {
        const [demandes, solde] = await Promise.all([
            leaveAPI.getAll({ year: annee }),
            leaveAPI.balance(annee)
        ]);

        state.leaves = demandes;
        state.leaveBalance = solde;
        renderLeaveStats(demandes, solde, annee);
        renderLeaves(filterLeaves(demandes));
    } catch (error) {
        console.error('Chargement des congés:', error);
        showLoadError('leavesList');
    }

    await membres;
}

/** Garnit le filtre de personnel, réservé à la direction. */
async function loadLeaveMembers() {
    const select = document.getElementById('leaveMemberFilter');
    const membres = await loadTeamMembers();
    const courant = select.value;

    select.innerHTML = '<option value="">Toute l\'équipe</option>'
        + membres.map(membre =>
            `<option value="${membre.id}">${escapeHtml(membre.display_name)}</option>`
        ).join('');
    select.value = courant;
}

function filterLeaves(demandes) {
    const statut = document.getElementById('leaveStatusFilter').value;
    const nature = document.getElementById('leaveKindFilter').value;
    const membre = document.getElementById('leaveMemberFilter').value;

    return demandes.filter(demande =>
        (!statut || demande.status === statut)
        && (!nature || demande.kind === nature)
        && (!membre || String(demande.member) === membre));
}

function applyLeaveFilters() {
    renderLeaves(filterLeaves(state.leaves));
}

function renderLeaveStats(demandes, solde, annee) {
    const moi = (solde?.members || [])
        .find(ligne => ligne.member_id === state.profile?.member_id);

    setText('leaveBalance', moi ? `${formatNumber(moi.balance, 1)} j` : '—');
    setText('leaveTaken', moi
        ? `${formatNumber(moi.taken, 1)} / ${moi.entitlement} j` : '—');

    const attente = demandes.filter(demande => demande.status === 'pending').length;
    setText('leavePending', attente);
    updateLeaveBadge(attente);

    const aujourdhui = toDateInputValue(new Date());
    setText('leaveAway', demandes.filter(demande =>
        demande.status === 'approved'
        && demande.start_date <= aujourdhui && demande.end_date >= aujourdhui).length);

    setText('leavesSubtitle',
        `Année ${annee} — ${demandes.length} demande(s)`
        + (attente ? `, ${attente} en attente` : ''));
}

/** Compteur du rail : ce qui attend une réponse. */
function updateLeaveBadge(attente) {
    const badge = document.getElementById('leaveBadge');
    badge.textContent = attente > 99 ? '99+' : attente;
    badge.hidden = !attente;
}

function leaveDates(demande) {
    if (demande.start_date === demande.end_date) {
        return formatDate(demande.start_date);
    }
    return `du ${formatDate(demande.start_date)} au ${formatDate(demande.end_date)}`;
}

function renderLeaves(demandes) {
    const container = document.getElementById('leavesList');
    const direction = Boolean(state.profile?.is_founder);
    const aujourdhui = toDateInputValue(new Date());

    if (!demandes.length) {
        container.innerHTML = emptyState(
            'fa-umbrella-beach',
            'Aucune demande',
            'Posez vos dates, la direction répond depuis cette page.'
        );
        return;
    }

    container.innerHTML = demandes.map(demande => {
        const nature = leaveKind(demande.kind);
        const sien = demande.member === state.profile?.member_id;
        // Une demande passée ne s'annule plus : le serveur la refuse, le
        // bouton ne doit pas la proposer.
        const annulable = (sien || direction) && demande.end_date >= aujourdhui
            && ['pending', 'approved'].includes(demande.status);

        return `
        <div class="report-card leave-card ${escapeHtml(demande.status)}"
             data-id="${demande.id}">
            <div class="report-head">
                <div>
                    <span class="report-kind">
                        <i class="fas ${nature.icon}"></i> ${escapeHtml(demande.kind_label)}
                    </span>
                    <h3>${escapeHtml(direction ? demande.member_name : leaveDates(demande))}</h3>
                    <p class="text-muted">
                        ${direction ? `${escapeHtml(leaveDates(demande))} · ` : ''}
                        ${escapeHtml(demande.days_label)}
                        ${demande.is_counted ? ' · décompté du solde' : ''}
                    </p>
                </div>
                <span class="status-badge ${LEAVE_STATUS_CLASS[demande.status] || ''}">
                    ${escapeHtml(demande.status_label)}
                </span>
            </div>

            <p class="report-summary">${escapeHtml(demande.reason)}</p>
            ${demande.decision ? `
                <p class="suggestion-reply">
                    <strong>Réponse</strong>${escapeHtml(demande.decided_by_name
                        ? ` de ${demande.decided_by_name}` : '')} :
                    ${escapeHtml(demande.decision)}
                </p>` : ''}

            ${direction && demande.status === 'pending' ? `
                <div class="suggestion-actions">
                    <input type="text" class="input-field leave-reply-input"
                           placeholder="Réponse (facultative)">
                    <button class="btn btn-small btn-success approve-leave">
                        <i class="fas fa-check"></i> Accorder
                    </button>
                    <button class="btn btn-small btn-danger refuse-leave">
                        <i class="fas fa-xmark"></i> Refuser
                    </button>
                </div>` : ''}

            <div class="card-actions">
                ${sien && demande.status === 'pending' ? `
                    <button class="btn btn-small btn-secondary edit-leave">
                        <i class="fas fa-pen"></i> Modifier
                    </button>` : ''}
                ${annulable ? `
                    <button class="btn btn-small btn-secondary cancel-leave">
                        <i class="fas fa-ban"></i> Annuler
                    </button>` : ''}
                ${sien && demande.status === 'pending' ? `
                    <button class="btn btn-small btn-danger delete-leave">
                        <i class="fas fa-trash"></i> Retirer
                    </button>` : ''}
            </div>
        </div>`;
    }).join('');

    const idDe = (bouton) => Number(bouton.closest('.leave-card').dataset.id);

    container.querySelectorAll('.approve-leave, .refuse-leave').forEach(bouton => {
        bouton.addEventListener('click', async () => {
            const carte = bouton.closest('.leave-card');
            const reponse = carte.querySelector('.leave-reply-input').value.trim();
            const accorde = bouton.classList.contains('approve-leave');
            try {
                await leaveAPI.decide(Number(carte.dataset.id),
                                      accorde ? 'approved' : 'refused', reponse);
                showToast(accorde ? 'Congé accordé' : 'Demande refusée',
                          accorde ? 'success' : 'info');
                await Promise.all([loadLeaves(), loadNotifications()]);
            } catch (error) {
                console.error('Décision sur le congé:', error);
            }
        });
    });

    container.querySelectorAll('.edit-leave').forEach(bouton => {
        bouton.addEventListener('click', () =>
            openLeaveModal(demandes.find(demande => demande.id === idDe(bouton))));
    });

    container.querySelectorAll('.cancel-leave').forEach(bouton => {
        bouton.addEventListener('click', async () => {
            if (!confirm('Annuler cette demande de congé ?')) return;
            try {
                await leaveAPI.cancel(idDe(bouton));
                showToast('Demande annulée', 'info');
                await Promise.all([loadLeaves(), loadNotifications()]);
            } catch (error) {
                console.error('Annulation du congé:', error);
            }
        });
    });

    container.querySelectorAll('.delete-leave').forEach(bouton => {
        bouton.addEventListener('click', async () => {
            if (!confirm('Retirer définitivement cette demande ?')) return;
            try {
                await leaveAPI.delete(idDe(bouton));
                showToast('Demande retirée', 'success');
                await Promise.all([loadLeaves(), loadNotifications()]);
            } catch (error) {
                console.error('Suppression de la demande:', error);
            }
        });
    });
}

function openLeaveModal(demande = null) {
    const form = document.getElementById('leaveForm');
    form.reset();

    const debut = demande?.start_date || toDateInputValue(new Date());
    document.getElementById('leaveId').value = demande?.id || '';
    document.getElementById('leaveKind').value = demande?.kind || 'paid';
    document.getElementById('leaveStart').value = debut;
    document.getElementById('leaveEnd').value = demande?.end_date || debut;
    document.getElementById('leaveHalfDay').checked = Boolean(demande?.half_day);
    document.getElementById('leaveReason').value = demande?.reason || '';

    document.querySelector('#leaveModal .modal-header h2').textContent =
        demande ? 'Modifier la demande' : 'Demande de congé';

    updateLeaveDaysHint();
    openModal('leaveModal');
}

/** Annonce la durée demandée, et ce qu'il resterait au solde. */
function updateLeaveDaysHint() {
    const debut = document.getElementById('leaveStart').value;
    const fin = document.getElementById('leaveEnd').value;
    const demi = document.getElementById('leaveHalfDay').checked;
    const nature = document.getElementById('leaveKind').value;

    const jours = demi && debut === fin ? 0.5 : workingDays(debut, fin);
    setText('leaveDaysHint', jours
        ? `${formatNumber(jours, 1)} jour(s) ouvrable(s) — samedis et dimanches exclus.`
        : 'Cette période ne compte aucun jour ouvrable.');

    const moi = (state.leaveBalance?.members || [])
        .find(ligne => ligne.member_id === state.profile?.member_id);
    const rappel = document.getElementById('leaveBalanceHint');

    // Le solde ne concerne que le congé payé : l'afficher ailleurs induirait
    // en erreur, une maladie ne l'entame pas.
    rappel.hidden = !(moi && nature === 'paid');
    if (!rappel.hidden) {
        rappel.textContent = `Solde disponible : ${formatNumber(moi.balance, 1)} jour(s)`
            + (jours ? `, soit ${formatNumber(moi.balance - jours, 1)} après ce congé.` : '.');
    }
}

async function submitLeave(event) {
    event.preventDefault();

    const id = document.getElementById('leaveId').value;
    const payload = {
        kind: document.getElementById('leaveKind').value,
        start_date: document.getElementById('leaveStart').value,
        end_date: document.getElementById('leaveEnd').value,
        half_day: document.getElementById('leaveHalfDay').checked,
        reason: document.getElementById('leaveReason').value.trim()
    };

    try {
        if (id) {
            await leaveAPI.update(id, payload);
            showToast('Demande mise à jour', 'success');
        } else {
            await leaveAPI.create(payload);
            showToast('Demande envoyée à la direction', 'success');
        }
        closeModal('leaveModal');
        await Promise.all([loadLeaves(), loadNotifications()]);
    } catch (error) {
        console.error('Envoi de la demande de congé:', error);
    }
}

// ===========================
// POINTAGE
// ===========================

/**
 * Relit sa journée et met le bouton de la barre du haut à jour.
 *
 * Le bouton porte l'état à lui seul : arrivée à pointer, journée en cours, ou
 * journée close. Rien à ouvrir pour le savoir.
 */
async function loadPunch() {
    try {
        state.punch = await attendanceAPI.today(true);
        renderPunch(state.punch);
    } catch (error) {
        console.error('Chargement du pointage:', error);
    }
}

function renderPunch(journee) {
    const bouton = document.getElementById('punchBtn');
    const pointage = journee?.attendance;

    bouton.hidden = false;
    bouton.classList.remove('is-open', 'is-done', 'is-leave');
    bouton.disabled = false;

    if (journee?.on_leave) {
        bouton.classList.add('is-leave');
        bouton.disabled = true;
        bouton.dataset.action = '';
        setText('punchLabel', 'En congé');
        bouton.title = `${journee.on_leave.kind_label} — ${leaveDates(journee.on_leave)}`;
        return;
    }

    if (!pointage) {
        bouton.dataset.action = 'in';
        setText('punchLabel', "Pointer l'arrivée");
        bouton.title = "Votre journée n'est pas encore pointée.";
        return;
    }

    const arrivee = formatTime(pointage.check_in);
    if (pointage.is_open) {
        bouton.classList.add('is-open');
        bouton.dataset.action = 'out';
        setText('punchLabel', `Pointer le départ · ${pointage.duration_label}`);
        bouton.title = `Arrivée à ${arrivee}`
            + (pointage.late_minutes ? `, ${pointage.late_minutes} min de retard` : '');
        return;
    }

    bouton.classList.add('is-done');
    bouton.disabled = true;
    bouton.dataset.action = '';
    setText('punchLabel', `Journée pointée · ${pointage.duration_label}`);
    bouton.title = `Arrivée à ${arrivee}, départ à ${formatTime(pointage.check_out)}`;
}

async function togglePunch() {
    const action = document.getElementById('punchBtn').dataset.action;
    if (!action) return;

    try {
        if (action === 'in') {
            const pointage = await attendanceAPI.checkIn();
            showToast(pointage.late_minutes
                ? `Arrivée pointée — ${pointage.late_minutes} min de retard`
                : 'Arrivée pointée', pointage.late_minutes ? 'info' : 'success');
        } else {
            const pointage = await attendanceAPI.checkOut();
            showToast(`Départ pointé — ${pointage.duration_label} de présence`, 'success');
        }

        await Promise.all([loadPunch(), loadNotifications()]);
        // La page ouverte peut montrer la présence : elle se relit.
        const active = document.querySelector('.page.active');
        if (active && ['attendance', 'dashboard'].includes(active.id)) {
            await openPage(active.id);
        }
    } catch (error) {
        console.error('Pointage:', error);
    }
}

// ===========================
// PRÉSENCES (direction)
// ===========================

async function loadAttendance() {
    if (!state.profile?.is_founder) {
        document.getElementById('attendanceTableBody').innerHTML = '';
        return;
    }

    const month = document.getElementById('attendanceMonth').value;

    try {
        const [synthese, jour] = await Promise.all([
            attendanceAPI.summary(month),
            attendanceAPI.getAll({ date: toDateInputValue(new Date()) })
        ]);

        renderAttendanceSummary(synthese);
        renderAttendanceTable(synthese.members);
        renderAttendanceToday(jour);
    } catch (error) {
        console.error('Chargement des présences:', error);
        showLoadError('attendanceTableBody', 'row');
    }
}

function renderAttendanceSummary(synthese) {
    const totaux = synthese.totals;

    setText('attendanceSubtitle',
        `${capitalize(formatMonth(synthese.month))} — ${totaux.members} membre(s)`);
    setText('attendanceHours', `${formatNumber(totaux.hours, 1)} h`);
    setText('attendanceDays', totaux.days);
    setText('attendanceLate', formatDuration(totaux.late_minutes));
    setText('attendanceAbsences', totaux.absences);
    setText('attendanceWorkingDays',
        `${synthese.working_days} jour(s) ouvrable(s) écoulé(s)`);
}

function renderAttendanceTable(lignes) {
    const container = document.getElementById('attendanceTableBody');

    if (!lignes.length) {
        container.innerHTML =
            '<tr><td colspan="6" class="text-center text-muted">Aucun membre actif</td></tr>';
        return;
    }

    container.innerHTML = lignes.map(ligne => `
        <tr>
            <td>
                <strong>${escapeHtml(ligne.member_name)}</strong>
                ${ligne.job_title
                    ? `<div class="text-muted">${escapeHtml(ligne.job_title)}</div>` : ''}
            </td>
            <td>${ligne.days}</td>
            <td>${escapeHtml(formatNumber(ligne.hours, 1))} h</td>
            <td>${ligne.late_minutes
                    ? `<strong class="text-danger">${escapeHtml(formatDuration(ligne.late_minutes))}</strong>`
                    : '<span class="text-muted">—</span>'}</td>
            <td>${ligne.leave_days
                    ? `${escapeHtml(formatNumber(ligne.leave_days, 1))} j`
                    : '<span class="text-muted">—</span>'}</td>
            <td>${ligne.absences
                    ? `<strong class="text-danger">${ligne.absences}</strong>`
                    : '<span class="text-muted">0</span>'}</td>
        </tr>`).join('');
}

function renderAttendanceToday(pointages) {
    const container = document.getElementById('attendanceToday');
    setText('attendanceTodayCount', `${pointages.length} pointage(s) aujourd'hui`);

    if (!pointages.length) {
        container.innerHTML = emptyState(
            'fa-fingerprint',
            'Personne n\'a encore pointé',
            'Les arrivées du jour apparaîtront ici.'
        );
        return;
    }

    container.innerHTML = pointages.map(pointage => `
        <div class="attendance-row${pointage.is_open ? ' open' : ''}">
            <div>
                <strong>${escapeHtml(pointage.member_name)}</strong>
                <div class="text-muted">${escapeHtml(pointage.job_title || '')}</div>
            </div>
            <div class="attendance-times">
                <span><i class="fas fa-right-to-bracket"></i>
                    ${escapeHtml(formatTime(pointage.check_in))}</span>
                <span><i class="fas fa-right-from-bracket"></i>
                    ${pointage.check_out
                        ? escapeHtml(formatTime(pointage.check_out))
                        : '<em>en cours</em>'}</span>
            </div>
            <div>
                <span class="status-badge ${pointage.is_open ? 'status-progress' : 'status-done'}">
                    ${escapeHtml(pointage.duration_label)}
                </span>
                ${pointage.late_minutes
                    ? `<span class="status-badge status-blocked">
                           ${pointage.late_minutes} min de retard
                       </span>` : ''}
            </div>
        </div>`).join('');
}

// ===========================
// PAIE ET PERSONNEL (gérant)
// ===========================

/** Libellés et champs propres à chaque nature d'évènement. */
const STAFF_EVENT_FORMS = {
    suspension: {
        date: 'Premier jour', end: true, paid: 'Mise à pied avec solde',
        icon: 'fa-gavel', tone: 'status-blocked'
    },
    observation: {
        date: 'Date', icon: 'fa-triangle-exclamation', tone: 'status-draft'
    },
    lateness: {
        date: 'Date', minutes: true, icon: 'fa-clock', tone: 'status-todo'
    },
    overtime: {
        date: 'Date', hours: true, paid: 'Heures payées',
        icon: 'fa-business-time', tone: 'status-progress'
    }
};

function staffEventForm(kind) {
    return STAFF_EVENT_FORMS[kind] || STAFF_EVENT_FORMS.observation;
}

/**
 * Oublie le personnel mis en cache.
 *
 * À appeler après toute modification de compte : sans cela, un employé qui
 * vient d'être créé n'apparaîtrait pas dans les sélecteurs de la paie avant
 * un rechargement complet, et un salaire corrigé y resterait périmé.
 */
function forgetStaffMembers() {
    state.staff = [];
}

/**
 * Charge le personnel une seule fois et garnit les sélecteurs du gérant.
 *
 * La liste ne change pas d'une page à l'autre : la relire à chaque ouverture
 * de modale ajouterait un aller-retour sans rien apporter. Les modifications
 * de compte l'oublient explicitement, elles.
 */
async function loadTeamMembers() {
    if (state.staff.length) return state.staff;

    try {
        state.staff = await memberAPI.getAll();
    } catch (error) {
        console.error('Chargement du personnel:', error);
        return [];
    }
    return state.staff;
}

async function loadStaffMembers() {
    await loadTeamMembers();
    if (!state.staff.length) return [];

    const options = state.staff.map(member =>
        `<option value="${member.id}">${escapeHtml(member.display_name)}</option>`
    ).join('');

    ['payslipMember', 'staffEventMember'].forEach(id => {
        document.getElementById(id).innerHTML = options;
    });
    ['payslipMemberFilter', 'staffMemberFilter'].forEach(id => {
        document.getElementById(id).innerHTML =
            '<option value="">Tout le personnel</option>' + options;
    });

    return state.staff;
}

// --- Bulletins de paie ---

async function loadPayroll() {
    if (!state.profile?.is_manager) {
        document.getElementById('payslipsList').innerHTML = '';
        return;
    }

    const month = document.getElementById('payrollMonth').value;
    const members = loadStaffMembers();

    try {
        // La synthèse et la liste ne dépendent pas l'une de l'autre.
        const [summary, payslips] = await Promise.all([
            payslipAPI.summary(month),
            payslipAPI.getAll({
                month,
                member: document.getElementById('payslipMemberFilter').value
            })
        ]);

        renderPayrollSummary(summary);
        renderPayslips(payslips);
    } catch (error) {
        console.error('Chargement de la paie:', error);
        showLoadError('payslipsList');
    }

    await members;
}

function renderPayrollSummary(summary) {
    setText('payrollSubtitle',
        `${capitalize(formatMonth(summary.month))} — ${summary.count} bulletin(s) `
        + `sur ${summary.team_size} membre(s)`);
    setText('payrollGross', formatMoneyCompact(summary.gross));
    setText('payrollNet', formatMoneyCompact(summary.net));
    setText('payrollWorked', `${formatNumber(summary.worked_hours, 2)} h`);
    setText('payrollOvertime', `${formatNumber(summary.overtime_hours, 2)} h`);
}

function renderPayslips(payslips) {
    const container = document.getElementById('payslipsList');

    if (!payslips.length) {
        container.innerHTML = emptyState(
            'fa-money-check-dollar',
            'Aucun bulletin sur ce mois',
            'Établissez le premier bulletin de paie du mois.'
        );
        return;
    }

    container.innerHTML = payslips.map(payslip => `
        <div class="report-card" data-id="${payslip.id}">
            <div class="report-head">
                <div>
                    <span class="report-kind">${escapeHtml(capitalize(formatMonth(payslip.month)))}</span>
                    <h3>${escapeHtml(payslip.member_name)}</h3>
                    <p class="text-muted">
                        ${escapeHtml(payslip.job_title || capitalize(payslip.department || ''))}
                        ${payslip.issued_at ? ` · établi le ${formatDate(payslip.issued_at)}` : ''}
                    </p>
                </div>
            </div>

            <div class="payslip-lines">
                ${Number(payslip.worked_hours)
                    ? payslipTextLine('Heures travaillées',
                                      `${formatNumber(payslip.worked_hours, 2)} h`)
                    : ''}
                ${payslipLine('Salaire de base', payslip.base_salary)}
                ${Number(payslip.overtime_amount)
                    ? payslipLine(
                        `Heures sup. (${formatNumber(payslip.overtime_hours, 2)} h)`,
                        payslip.overtime_amount)
                    : ''}
                ${Number(payslip.bonuses) ? payslipLine('Primes', payslip.bonuses) : ''}
                ${Number(payslip.deductions)
                    ? payslipLine('Retenues', payslip.deductions, true) : ''}
                ${Number(payslip.contributions)
                    ? payslipLine('Cotisations', payslip.contributions, true) : ''}
                <div class="payslip-line total">
                    <span>Net à payer</span>
                    <strong>${formatMoney(payslip.net)}</strong>
                </div>
            </div>

            ${payslipEventsSection(payslip.staff_events)}
            ${payslip.notes ? reportSection('Observations', payslip.notes) : ''}

            <div class="card-actions">
                <button class="btn btn-small btn-secondary edit-payslip">
                    <i class="fas fa-pen"></i> Modifier
                </button>
                <button class="btn btn-small btn-secondary export-payslip"
                        title="Ouvre l'aperçu d'impression : choisissez « Enregistrer au format PDF »">
                    <i class="fas fa-file-pdf"></i> Exporter en PDF
                </button>
            </div>
        </div>
    `).join('');

    container.querySelectorAll('.edit-payslip').forEach(button => {
        button.addEventListener('click', () => {
            const id = Number(button.closest('.report-card').dataset.id);
            openPayslipModal(payslips.find(p => p.id === id));
        });
    });

    container.querySelectorAll('.export-payslip').forEach(button => {
        button.addEventListener('click', () => {
            const id = Number(button.closest('.report-card').dataset.id);
            exportPayslipToPdf(payslips.find(p => p.id === id));
        });
    });
}

/**
 * Retards, observations et mises à pied du mois, sous le décompte.
 *
 * Ils ne se saisissent pas depuis le bulletin : le suivi du personnel reste
 * leur seule source, le bulletin les reprend pour que le décompte se relise.
 */
function payslipEventsSection(events) {
    if (!events?.length) return '';
    return `
        <div class="report-section">
            <h4>Retards, observations et mises à pied du mois</h4>
            ${payslipEventsList(events)}
        </div>`;
}

/** Les évènements du mois, un par ligne. */
function payslipEventsList(events) {
    return `
        <ul class="payslip-events">
            ${events.map(event => `
                <li class="${event.is_disciplinary ? 'disciplinary' : ''}">
                    <i class="fas ${staffEventForm(event.kind).icon}"></i>
                    <span class="payslip-event-kind">
                        ${escapeHtml(event.kind_label)}
                    </span>
                    <span class="text-muted">
                        ${escapeHtml(staffEventDates(event))}
                        ${event.summary ? ` · ${escapeHtml(event.summary)}` : ''}
                    </span>
                    <span class="payslip-event-reason">
                        ${escapeHtml(event.reason || '')}
                    </span>
                </li>`).join('')}
        </ul>`;
}

/** Ligne de décompte d'un bulletin ; une retenue s'affiche en négatif. */
function payslipLine(label, amount, negative = false) {
    return payslipTextLine(
        label, `${negative ? '− ' : ''}${formatMoney(amount)}`, negative
    );
}

/** Ligne d'un bulletin dont la valeur n'est pas un montant : des heures. */
function payslipTextLine(label, value, negative = false) {
    return `
        <div class="payslip-line${negative ? ' negative' : ''}">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
        </div>`;
}

function openPayslipModal(payslip = null) {
    document.getElementById('payslipForm').reset();

    document.getElementById('payslipId').value = payslip?.id || '';
    document.getElementById('payslipMember').value = payslip?.member || '';
    document.getElementById('payslipMonth').value =
        payslip?.month_label || document.getElementById('payrollMonth').value;
    // L'API renvoie les montants en chaîne (« 450000.00 ») : sans conversion,
    // le champ afficherait des centimes que le franc CFA ne connaît pas.
    document.getElementById('payslipBase').value = Number(payslip?.base_salary || 0);
    document.getElementById('payslipWorkedHours').value =
        Number(payslip?.worked_hours || 0);
    document.getElementById('payslipOvertimeHours').value =
        Number(payslip?.overtime_hours || 0);
    document.getElementById('payslipOvertimeAmount').value =
        Number(payslip?.overtime_amount || 0);
    document.getElementById('payslipBonuses').value = Number(payslip?.bonuses || 0);
    document.getElementById('payslipDeductions').value = Number(payslip?.deductions || 0);
    document.getElementById('payslipContributions').value =
        Number(payslip?.contributions || 0);
    document.getElementById('payslipNotes').value = payslip?.notes || '';

    // Le salarié d'un bulletin ne change pas : ce serait établir le bulletin
    // de quelqu'un d'autre. Le mois, lui, se corrige — une période saisie de
    // travers doit pouvoir se rattraper sans tout ressaisir.
    document.getElementById('payslipMember').disabled = Boolean(payslip);
    document.getElementById('payslipMonth').disabled = false;

    document.querySelector('#payslipModal .modal-header h2').textContent =
        payslip ? 'Modifier le bulletin' : 'Nouveau bulletin';

    prefillPayslipBase();
    updatePayslipPreview();
    updateBonusHint();
    showPayslipEvents(payslip?.staff_events);
    openModal('payslipModal');
    refreshPayslipEvents();
    refreshPayslipHours();
}

/**
 * Rappelle les heures pointées du mois pour le salarié choisi.
 *
 * Le décompte du pointage ne s'inscrit pas tout seul : le gérant le reporte
 * d'un clic, comme la prime des points, et reste maître du chiffre porté au
 * bulletin — un mois se corrige parfois à la main.
 */
async function refreshPayslipHours() {
    const id = Number(document.getElementById('payslipMember').value);
    const month = document.getElementById('payslipMonth').value;
    const indice = document.getElementById('payslipHoursHint');

    indice.hidden = true;
    if (!id || !month) return;

    try {
        const synthese = await attendanceAPI.summary(month);
        const ligne = synthese.members.find(l => l.member_id === id);
        if (!ligne || !ligne.hours) return;

        indice.hidden = false;
        setText('payslipHoursText',
            `${formatNumber(ligne.hours, 2)} h pointées sur ${ligne.days} jour(s). `);
        document.getElementById('payslipHoursApply').dataset.hours = ligne.hours;
    } catch (error) {
        // Le bulletin se chiffre sans elles : le rappel est un confort.
        console.error('Chargement des heures pointées:', error);
    }
}

/**
 * Rappelle sous le formulaire les évènements du salarié pour le mois saisi.
 *
 * Le gérant retient une absence ou reporte des heures : il doit les avoir
 * sous les yeux au moment où il chiffre, pas seulement une fois le bulletin
 * établi. Les fiches restent en lecture seule ici.
 */
async function refreshPayslipEvents() {
    const member = document.getElementById('payslipMember').value;
    const month = document.getElementById('payslipMonth').value;
    if (!member || !month) return showPayslipEvents([]);

    const [from, to] = monthBounds(month);
    try {
        showPayslipEvents(await staffEventAPI.getAll({
            member, from_date: from, to_date: to
        }));
    } catch (error) {
        // Le bulletin se chiffre sans eux : un rappel manquant n'empêche pas
        // d'enregistrer.
        console.error('Chargement des évènements du bulletin:', error);
    }
}

function showPayslipEvents(events) {
    const bloc = document.getElementById('payslipEventsBlock');
    bloc.hidden = !events?.length;
    document.getElementById('payslipEvents').innerHTML =
        events?.length ? payslipEventsList(events) : '';
}

/**
 * Choisir un membre renseigne ce que l'on sait déjà de lui.
 *
 * Le salaire de base vit sur son profil : le retaper serait risquer que le
 * bulletin et la fiche disent deux choses différentes.
 */
function onPayslipMemberChange() {
    prefillPayslipBase();
    updateBonusHint();
    refreshPayslipEvents();
    refreshPayslipHours();
}

/**
 * Reporte le salaire de base du profil sur un bulletin en cours de création.
 *
 * Un bulletin déjà établi garde le sien : il porte la trace d'un mois payé,
 * que la fiche d'aujourd'hui n'a pas à réécrire. Le montant proposé reste
 * modifiable — un mois n'est pas toujours un mois ordinaire.
 */
function prefillPayslipBase() {
    if (document.getElementById('payslipId').value) return;

    const id = Number(document.getElementById('payslipMember').value);
    const membre = state.staff.find(m => m.id === id);
    if (!membre) return;

    document.getElementById('payslipBase').value = Number(membre.base_salary || 0);
    updatePayslipPreview();
}

/**
 * Rappelle la prime ouverte par les points du mois du membre choisi.
 *
 * Le report se fait d'un clic mais jamais tout seul : le gérant décide du
 * montant qu'il inscrit, les points ne sont qu'une proposition.
 */
function updateBonusHint() {
    const id = Number(document.getElementById('payslipMember').value);
    const membre = state.staff.find(m => m.id === id);
    const indice = document.getElementById('payslipBonusHint');

    if (!membre || !membre.bonus_earned) {
        indice.hidden = true;
        return;
    }

    indice.hidden = false;
    setText('payslipBonusText',
        `${membre.points_month} point(s) ce mois-ci, soit `
        + `${formatMoney(membre.bonus_earned)} de prime. `);
    document.getElementById('payslipBonusApply').dataset.amount = membre.bonus_earned;
}

/** Recalcule le brut et le net affichés sous le formulaire. */
function updatePayslipPreview() {
    const value = (id) => Number(document.getElementById(id).value) || 0;

    const gross = value('payslipBase') + value('payslipOvertimeAmount')
        + value('payslipBonuses');
    const net = gross - value('payslipDeductions') - value('payslipContributions');

    setText('payslipGrossPreview', formatMoney(gross));
    setText('payslipNetPreview', formatMoney(net));
    document.getElementById('payslipNetPreview')
        .classList.toggle('negative', net < 0);
}

async function submitPayslip(event) {
    event.preventDefault();

    const id = document.getElementById('payslipId').value;
    const payload = {
        base_salary: document.getElementById('payslipBase').value || 0,
        worked_hours: document.getElementById('payslipWorkedHours').value || 0,
        overtime_hours: document.getElementById('payslipOvertimeHours').value || 0,
        overtime_amount: document.getElementById('payslipOvertimeAmount').value || 0,
        bonuses: document.getElementById('payslipBonuses').value || 0,
        deductions: document.getElementById('payslipDeductions').value || 0,
        contributions: document.getElementById('payslipContributions').value || 0,
        // Le champ `month` d'un input mois vaut `AAAA-MM` : l'API attend une
        // date. Il part à chaque enregistrement, création ou correction : sans
        // lui, une période saisie de travers restait telle quelle.
        month: `${document.getElementById('payslipMonth').value}-01`,
        notes: document.getElementById('payslipNotes').value.trim()
    };

    if (!id) {
        payload.member = Number(document.getElementById('payslipMember').value);
    }

    try {
        if (id) {
            await payslipAPI.update(id, payload);
            showToast('Bulletin mis à jour', 'success');
        } else {
            await payslipAPI.create(payload);
            showToast('Bulletin établi', 'success');
        }
        closeModal('payslipModal');
        await loadPayroll();
    } catch (error) {
        console.error('Enregistrement du bulletin:', error);
    }
}

// --- Suivi du personnel ---

async function loadStaff() {
    if (!state.profile?.is_manager) {
        document.getElementById('staffEventsList').innerHTML = '';
        return;
    }

    const month = document.getElementById('staffMonth').value;
    const members = loadStaffMembers();
    const [from, to] = monthBounds(month);

    try {
        const [summary, events] = await Promise.all([
            staffEventAPI.summary(month),
            staffEventAPI.getAll({
                from_date: from,
                to_date: to,
                kind: document.getElementById('staffKindFilter').value,
                member: document.getElementById('staffMemberFilter').value
            })
        ]);

        renderStaffSummary(summary);
        renderStaffEvents(events);
    } catch (error) {
        console.error('Chargement du personnel:', error);
        showLoadError('staffEventsList');
    }

    await members;
}

/** Premier et dernier jour d'un mois `AAAA-MM`, au format ISO. */
function monthBounds(monthValue) {
    const [year, month] = (monthValue || toMonthInputValue(new Date()))
        .split('-').map(Number);
    return [
        toDateInputValue(new Date(year, month - 1, 1)),
        toDateInputValue(new Date(year, month, 0))
    ];
}

function renderStaffSummary(summary) {
    const counts = summary.counts || {};
    setText('staffSubtitle',
        `${capitalize(formatMonth(summary.month))} — ${summary.total} évènement(s)`);
    setText('staffSuspensions', counts.suspension ?? 0);
    setText('staffObservations', counts.observation ?? 0);
    setText('staffLateness', `${summary.late_minutes} min`);
    setText('staffOvertime', `${formatNumber(summary.overtime_hours, 2)} h`);
}

function renderStaffEvents(events) {
    const container = document.getElementById('staffEventsList');

    if (!events.length) {
        container.innerHTML = emptyState(
            'fa-user-clock',
            'Aucun évènement sur ce mois',
            'Mises à pied, observations, retards et heures supplémentaires.'
        );
        return;
    }

    container.innerHTML = events.map(event => {
        const form = staffEventForm(event.kind);
        return `
        <div class="report-card staff-card ${event.is_disciplinary ? 'disciplinary' : ''}"
             data-id="${event.id}">
            <div class="report-head">
                <div>
                    <span class="report-kind">
                        <i class="fas ${form.icon}"></i> ${escapeHtml(event.kind_label)}
                    </span>
                    <h3>${escapeHtml(event.member_name)}</h3>
                    <p class="text-muted">
                        ${escapeHtml(staffEventDates(event))}
                        ${event.summary ? ` · ${escapeHtml(event.summary)}` : ''}
                        ${event.recorded_by_name
                            ? ` · saisi par ${escapeHtml(event.recorded_by_name)}` : ''}
                    </p>
                </div>
                ${event.summary ? `
                    <span class="status-badge ${form.tone}">
                        ${escapeHtml(event.summary)}
                    </span>` : ''}
            </div>

            <p class="report-summary">${escapeHtml(event.reason)}</p>
            ${reportSection('Suite donnée', event.decision)}
            ${event.kind === 'suspension' || event.kind === 'overtime' ? `
                <p class="text-muted staff-solde">
                    ${event.is_paid
                        ? (event.kind === 'suspension' ? 'Avec solde' : 'Heures payées')
                        : (event.kind === 'suspension' ? 'Sans solde' : 'Heures non payées')}
                </p>` : ''}

            <div class="card-actions">
                <button class="btn btn-small btn-secondary edit-staff-event">
                    <i class="fas fa-pen"></i> Modifier
                </button>
                <button class="btn btn-small btn-danger delete-staff-event">
                    <i class="fas fa-trash"></i> Supprimer
                </button>
            </div>
        </div>
    `;
    }).join('');

    container.querySelectorAll('.edit-staff-event').forEach(button => {
        button.addEventListener('click', () => {
            const id = Number(button.closest('.report-card').dataset.id);
            openStaffEventModal(events.find(e => e.id === id));
        });
    });

    container.querySelectorAll('.delete-staff-event').forEach(button => {
        button.addEventListener('click', async () => {
            const id = Number(button.closest('.report-card').dataset.id);
            if (!confirm('Supprimer définitivement cet évènement ?')) return;
            try {
                await staffEventAPI.delete(id);
                showToast('Évènement supprimé', 'success');
                await loadStaff();
            } catch (error) {
                console.error("Suppression de l'évènement:", error);
            }
        });
    });
}

/** Dates d'un évènement : une plage pour une mise à pied, un jour sinon. */
function staffEventDates(event) {
    if (event.kind === 'suspension' && event.end_date) {
        return `du ${formatDate(event.date)} au ${formatDate(event.end_date)}`;
    }
    return formatDate(event.date);
}

function openStaffEventModal(event = null) {
    document.getElementById('staffEventForm').reset();

    document.getElementById('staffEventId').value = event?.id || '';
    document.getElementById('staffEventMember').value = event?.member || '';
    document.getElementById('staffEventKind').value = event?.kind || 'observation';
    document.getElementById('staffEventDate').value =
        event?.date || toDateInputValue(new Date());
    document.getElementById('staffEventEnd').value = event?.end_date || '';
    document.getElementById('staffEventMinutes').value = event?.minutes || '';
    document.getElementById('staffEventHours').value = event?.hours || '';
    document.getElementById('staffEventPaid').checked = Boolean(event?.is_paid);
    document.getElementById('staffEventReason').value = event?.reason || '';
    document.getElementById('staffEventDecision').value = event?.decision || '';

    document.querySelector('#staffEventModal .modal-header h2').textContent =
        event ? "Modifier l'évènement" : 'Nouvel évènement';

    applyStaffEventKind();
    openModal('staffEventModal');
}

/**
 * N'affiche que la mesure correspondant à la nature choisie.
 *
 * Un champ requis mais masqué bloquerait l'envoi sans rien signaler : les
 * contraintes suivent la visibilité.
 */
function applyStaffEventKind() {
    const kind = document.getElementById('staffEventKind').value;
    const form = staffEventForm(kind);

    setText('staffEventDateLabel', form.date);

    const groups = {
        staffEventEndGroup: [Boolean(form.end), 'staffEventEnd'],
        staffEventMinutesGroup: [Boolean(form.minutes), 'staffEventMinutes'],
        staffEventHoursGroup: [Boolean(form.hours), 'staffEventHours'],
        staffEventPaidGroup: [Boolean(form.paid), null]
    };

    Object.entries(groups).forEach(([groupId, [visible, inputId]]) => {
        document.getElementById(groupId).hidden = !visible;
        if (inputId) document.getElementById(inputId).required = visible;
    });

    if (form.paid) setText('staffEventPaidLabel', form.paid);
}

async function submitStaffEvent(event) {
    event.preventDefault();

    const kind = document.getElementById('staffEventKind').value;
    const form = staffEventForm(kind);
    const id = document.getElementById('staffEventId').value;

    const payload = {
        member: Number(document.getElementById('staffEventMember').value),
        kind,
        date: document.getElementById('staffEventDate').value,
        // Les mesures des autres natures repartent à vide : un retard converti
        // en observation ne doit pas garder ses minutes.
        end_date: form.end ? document.getElementById('staffEventEnd').value : null,
        minutes: form.minutes
            ? Number(document.getElementById('staffEventMinutes').value) : null,
        hours: form.hours ? document.getElementById('staffEventHours').value : null,
        is_paid: form.paid ? document.getElementById('staffEventPaid').checked : false,
        reason: document.getElementById('staffEventReason').value.trim(),
        decision: document.getElementById('staffEventDecision').value.trim()
    };

    try {
        if (id) {
            await staffEventAPI.update(id, payload);
            showToast('Évènement mis à jour', 'success');
        } else {
            await staffEventAPI.create(payload);
            showToast('Évènement enregistré', 'success');
        }
        closeModal('staffEventModal');
        await loadStaff();
    } catch (error) {
        console.error("Enregistrement de l'évènement:", error);
    }
}

const PAGE_LOADERS = {
    dashboard: loadDashboard,
    objectives: loadObjectives,
    roadmap: loadRoadmap,
    tasks: loadTasks,
    reports: loadReports,
    team: loadTeam,
    panel: loadPanel,
    accounts: loadAccounts,
    payroll: loadPayroll,
    staff: loadStaff,
    leaves: loadLeaves,
    attendance: loadAttendance
};

/** Conteneur principal de chaque page, et le squelette qui l'occupe. */
const PAGE_SKELETONS = {
    dashboard: [['dashboardTasks', 3, 'card']],
    objectives: [['objectivesList', 2, 'card']],
    roadmap: [['roadmapList', 3, 'card']],
    tasks: [['todayTasksList', 3, 'card']],
    reports: [['reportsList', 2, 'card']],
    team: [['teamTableBody', 3, 'row']],
    panel: [['panelTableBody', 3, 'row']],
    accounts: [['accountsTableBody', 4, 'row']],
    payroll: [['payslipsList', 2, 'card']],
    staff: [['staffEventsList', 3, 'card']],
    leaves: [['leavesList', 2, 'card']],
    attendance: [['attendanceTableBody', 3, 'row'], ['attendanceToday', 2, 'card']]
};

/** Pages dont le chargement est en cours, pour ne pas le relancer en double. */
const loadingPages = new Set();

/**
 * Affiche une page et charge ses données.
 *
 * La vue bascule immédiatement, garnie de squelettes tant que rien n'est
 * arrivé : attendre la réponse avant d'afficher donnait une page vide, sans
 * indication qu'un chargement était en cours.
 */
async function openPage(page) {
    // Quitter le panel coupe sa relecture : rien ne doit interroger le serveur
    // depuis une page qu'on ne regarde plus.
    if (page !== 'panel') stopPanelRefresh();

    setActivePage(page);
    showPageSkeleton(page);

    const loader = PAGE_LOADERS[page];
    // Un clic répété sur la même entrée ne relance pas la requête en cours.
    if (!loader || loadingPages.has(page)) return;

    loadingPages.add(page);
    try {
        await loader();
    } finally {
        loadingPages.delete(page);
    }
}

/** Garnit les conteneurs vides de la page de blocs d'attente. */
function showPageSkeleton(page) {
    (PAGE_SKELETONS[page] || []).forEach(([containerId, count, variant]) => {
        showSkeleton(containerId, count, variant);
    });
}

async function refreshCurrentPage() {
    const active = document.querySelector('.page.active');
    await Promise.all([
        active ? openPage(active.id) : null,
        loadNotifications()
    ]);
}

async function handleLogout() {
    await authAPI.logout();
    window.location.href = 'login.html';
}

function initEventListeners() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', async (event) => {
            event.preventDefault();
            await openPage(link.dataset.page);
        });
    });

    document.getElementById('refreshBtn')
        .addEventListener('click', refreshCurrentPage);
    document.getElementById('logoutBtn').addEventListener('click', async (event) => {
        event.preventDefault();
        await handleLogout();
    });

    // Objectifs
    document.getElementById('addObjectiveBtn')
        .addEventListener('click', () => openObjectiveModal());
    document.getElementById('objectiveForm')
        .addEventListener('submit', submitObjective);
    document.getElementById('objectiveStatusFilter')
        .addEventListener('change', loadObjectives);
    document.getElementById('objectiveDepartmentFilter')
        .addEventListener('change', loadObjectives);
    document.getElementById('exportObjectivesBtn').addEventListener('click', async () => {
        try {
            const filename = await objectiveAPI.exportCSV({
                status: document.getElementById('objectiveStatusFilter').value,
                department: document.getElementById('objectiveDepartmentFilter').value
            });
            showToast(`Export téléchargé : ${filename}`, 'success');
        } catch (error) {
            console.error('Export:', error);
        }
    });

    // Feuille de route
    document.getElementById('addRoadmapBtn')
        .addEventListener('click', () => openRoadmapModal());
    document.getElementById('roadmapForm').addEventListener('submit', submitRoadmap);
    document.getElementById('roadmapStatusFilter')
        .addEventListener('change', loadRoadmap);
    document.getElementById('roadmapSearch')
        .addEventListener('input', debounce(loadRoadmap, 350));
    document.getElementById('roadmapProgress').addEventListener('input', (event) => {
        document.getElementById('roadmapProgressValue').textContent = event.target.value;
    });

    // Tâches
    document.getElementById('quickTaskForm').addEventListener('submit', submitQuickTask);
    document.getElementById('carryOverBtn').addEventListener('click', async () => {
        try {
            const result = await taskAPI.carryOver();
            showToast(
                result.moved
                    ? `${result.moved} tâche(s) reportée(s) sur aujourd'hui`
                    : 'Aucune tâche en retard',
                result.moved ? 'success' : 'info'
            );
            await loadTasks();
        } catch (error) {
            console.error('Report des tâches:', error);
        }
    });

    // Rapports
    document.getElementById('addReportBtn')
        .addEventListener('click', () => openReportModal());
    document.getElementById('reportForm').addEventListener('submit', submitReport);
    document.getElementById('reportPeriodType')
        .addEventListener('change', applyReportType);
    document.getElementById('reportPeriodFilter')
        .addEventListener('change', loadReports);
    document.getElementById('reportStatusFilter')
        .addEventListener('change', loadReports);

    // Équipe
    const teamMonth = document.getElementById('teamMonth');
    teamMonth.value = toMonthInputValue(new Date());
    teamMonth.addEventListener('change', loadTeam);

    // Réactions : le barème pilote la saisie, les points restent ajustables.
    document.getElementById('reactionForm').addEventListener('submit', submitReaction);
    document.getElementById('reactionPoints')
        .addEventListener('input', updateReactionValue);

    // Le mot de passe engendré ne s'affiche qu'une fois : on le copie.
    document.getElementById('credentialCopy')
        .addEventListener('click', copyGeneratedPassword);

    // Mon profil.
    document.getElementById('profileBtn').addEventListener('click', async (event) => {
        event.preventDefault();
        await openProfileModal();
    });
    document.getElementById('passwordForm')
        .addEventListener('submit', submitPassword);

    // Utilisateurs : les listes de pôles servent au filtre et à la modale.
    const optionsPoles = DEPARTMENTS
        .map(([code, nom]) => `<option value="${code}">${nom}</option>`).join('');
    document.getElementById('accountDepartment').innerHTML = optionsPoles;
    document.getElementById('accountDepartmentFilter').innerHTML =
        '<option value="">Tous les pôles</option>' + optionsPoles;

    document.getElementById('addAccountBtn')
        .addEventListener('click', () => openAccountModal());
    document.getElementById('accountForm').addEventListener('submit', submitAccount);
    document.getElementById('accountRole')
        .addEventListener('change', applyAccountRole);
    document.getElementById('accountSearch')
        .addEventListener('input', debounce(loadAccounts, 350));
    document.getElementById('accountRoleFilter')
        .addEventListener('change', loadAccounts);
    document.getElementById('accountDepartmentFilter')
        .addEventListener('change', loadAccounts);

    // Congés : la demande se pose, la direction tranche depuis la liste.
    document.getElementById('addLeaveBtn')
        .addEventListener('click', () => openLeaveModal());
    document.getElementById('leaveForm').addEventListener('submit', submitLeave);
    ['leaveStatusFilter', 'leaveKindFilter', 'leaveMemberFilter'].forEach(id => {
        document.getElementById(id).addEventListener('change', applyLeaveFilters);
    });
    // La durée annoncée suit la saisie : on sait ce qu'on demande avant d'envoyer.
    ['leaveStart', 'leaveEnd', 'leaveHalfDay', 'leaveKind'].forEach(id => {
        document.getElementById(id).addEventListener('change', updateLeaveDaysHint);
    });

    // Pointage : un seul bouton, dont l'état dit ce qu'il fera.
    document.getElementById('punchBtn').addEventListener('click', togglePunch);

    const attendanceMonth = document.getElementById('attendanceMonth');
    attendanceMonth.value = toMonthInputValue(new Date());
    attendanceMonth.addEventListener('change', loadAttendance);

    // Panel du fondateur.
    document.getElementById('panelRefresh')
        .addEventListener('click', () => refreshPanel());
    document.getElementById('panelAuto')
        .addEventListener('change', schedulePanelRefresh);

    // Boîte à suggestions et cloche.
    document.getElementById('suggestionBtn')
        .addEventListener('click', openSuggestionModal);
    document.getElementById('suggestionForm')
        .addEventListener('submit', submitSuggestion);
    document.getElementById('notifBtn').addEventListener('click', (event) => {
        event.stopPropagation();
        toggleNotifications();
    });
    document.getElementById('notifRefresh').addEventListener('click', (event) => {
        event.stopPropagation();
        loadNotifications();
    });
    // Un clic ailleurs referme le panneau, comme tout menu déroulant.
    document.addEventListener('click', (event) => {
        if (!event.target.closest('#notifMenu')) toggleNotifications(false);
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') toggleNotifications(false);
    });

    // Paie et personnel : réservés au gérant.
    const payrollMonth = document.getElementById('payrollMonth');
    payrollMonth.value = toMonthInputValue(new Date());
    payrollMonth.addEventListener('change', loadPayroll);

    document.getElementById('addPayslipBtn')
        .addEventListener('click', () => openPayslipModal());
    document.getElementById('payslipForm').addEventListener('submit', submitPayslip);
    document.getElementById('payslipMemberFilter')
        .addEventListener('change', loadPayroll);

    document.getElementById('payslipMember')
        .addEventListener('change', onPayslipMemberChange);
    // Changer de mois change les évènements et les heures à rappeler sous le
    // formulaire.
    document.getElementById('payslipMonth').addEventListener('change', () => {
        refreshPayslipEvents();
        refreshPayslipHours();
    });
    document.getElementById('payslipHoursApply').addEventListener('click', () => {
        document.getElementById('payslipWorkedHours').value =
            document.getElementById('payslipHoursApply').dataset.hours || 0;
    });
    document.getElementById('payslipBonusApply').addEventListener('click', () => {
        document.getElementById('payslipBonuses').value =
            document.getElementById('payslipBonusApply').dataset.amount || 0;
        updatePayslipPreview();
    });

    // Le net se recalcule à chaque frappe des montants.
    ['payslipBase', 'payslipOvertimeAmount', 'payslipBonuses',
     'payslipDeductions', 'payslipContributions'].forEach(id => {
        document.getElementById(id).addEventListener('input', updatePayslipPreview);
    });

    const staffMonth = document.getElementById('staffMonth');
    staffMonth.value = toMonthInputValue(new Date());
    staffMonth.addEventListener('change', loadStaff);

    document.getElementById('addStaffEventBtn')
        .addEventListener('click', () => openStaffEventModal());
    document.getElementById('staffEventForm')
        .addEventListener('submit', submitStaffEvent);
    document.getElementById('staffEventKind')
        .addEventListener('change', applyStaffEventKind);
    document.getElementById('staffKindFilter').addEventListener('change', loadStaff);
    document.getElementById('staffMemberFilter').addEventListener('change', loadStaff);

    // Pôles disponibles dans le filtre réservé aux fondateurs.
    document.getElementById('objectiveDepartmentFilter').innerHTML =
        '<option value="">Tous les pôles</option>' +
        ['direction', 'commercial', 'marketing', 'produit', 'technique', 'finance',
         'operations']
            .map(value => `<option value="${value}">${capitalize(value)}</option>`)
            .join('');
}

document.addEventListener('DOMContentLoaded', initApp);
