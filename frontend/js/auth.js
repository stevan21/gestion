// ===========================
// PAGE DE CONNEXION
// ===========================

/** Destination après connexion, transmise par ?next= lors d'une redirection 401. */
function getRedirectTarget() {
    const next = new URLSearchParams(window.location.search).get('next');
    if (!next) return 'index.html';

    // On n'accepte qu'un chemin relatif : une URL absolue serait une redirection ouverte.
    const decoded = decodeURIComponent(next);
    if (/^https?:\/\//i.test(decoded) || decoded.startsWith('//')) return 'index.html';
    return decoded;
}

function showAuthError(message) {
    const box = document.getElementById('authError');
    box.textContent = message;
    box.classList.add('visible');
}

function clearAuthError() {
    document.getElementById('authError').classList.remove('visible');
}

function switchTab(name) {
    clearAuthError();

    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === name);
    });
    document.getElementById('loginForm').hidden = name !== 'login';
    document.getElementById('registerForm').hidden = name !== 'register';
}

/** Bloque le formulaire pendant l'appel réseau pour éviter les doubles soumissions. */
function setFormBusy(form, busy) {
    form.querySelectorAll('input, button').forEach(el => { el.disabled = busy; });
}

async function handleLogin(event) {
    event.preventDefault();
    clearAuthError();

    const form = event.currentTarget;
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;

    if (!username || !password) {
        showAuthError('Renseignez votre nom d\'utilisateur et votre mot de passe.');
        return;
    }

    setFormBusy(form, true);
    try {
        const { user } = await authAPI.login(username, password);
        showToast(`Bienvenue ${user.first_name || user.username} !`, 'success');
        window.location.href = getRedirectTarget();
    } catch (error) {
        showAuthError(error.message);
        document.getElementById('loginPassword').value = '';
    } finally {
        setFormBusy(form, false);
    }
}

async function handleRegister(event) {
    event.preventDefault();
    clearAuthError();

    const form = event.currentTarget;
    const email = document.getElementById('registerEmail').value.trim();
    const password = document.getElementById('registerPassword').value;
    const passwordConfirm = document.getElementById('registerPasswordConfirm').value;

    if (!isValidEmail(email)) {
        showAuthError('Adresse email invalide.');
        return;
    }
    if (password !== passwordConfirm) {
        showAuthError('Les mots de passe ne correspondent pas.');
        return;
    }

    const payload = {
        username: document.getElementById('registerUsername').value.trim(),
        email,
        first_name: document.getElementById('registerFirstName').value.trim(),
        last_name: document.getElementById('registerLastName').value.trim(),
        job_title: document.getElementById('registerJobTitle').value.trim(),
        department: document.getElementById('registerDepartment').value,
        password,
        password_confirm: passwordConfirm
    };

    setFormBusy(form, true);
    try {
        await authAPI.register(payload);
        showToast('Compte créé avec succès', 'success');
        window.location.href = getRedirectTarget();
    } catch (error) {
        showAuthError(error.message);
    } finally {
        setFormBusy(form, false);
    }
}

function initAuthPage() {
    initTheme();

    // Une session encore valide n'a pas à repasser par la connexion.
    if (session.isAuthenticated()) {
        window.location.replace(getRedirectTarget());
        return;
    }

    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    document.getElementById('loginForm').addEventListener('submit', handleLogin);
    document.getElementById('registerForm').addEventListener('submit', handleRegister);
    document.getElementById('loginUsername').focus();
}

document.addEventListener('DOMContentLoaded', initAuthPage);
