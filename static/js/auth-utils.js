// static/js/auth-utils.js

// Detect base path from current URL (supports /ecos/ or any prefix)
function getBasePath() {
    const scripts = document.querySelectorAll('script[src*="auth-utils.js"]');
    if (scripts.length > 0) {
        const src = scripts[0].getAttribute('src');
        const idx = src.indexOf('/static/');
        if (idx > 0) return src.substring(0, idx);
    }
    return '';
}

const BASE_PATH = getBasePath();

/**
 * Utility function for making authenticated AJAX requests.
 * Automatically prepends BASE_PATH to absolute URLs.
 */
async function authenticatedFetch(url, options = {}) {
    // Auto-prepend base path for absolute URLs
    if (url.startsWith('/')) {
        url = BASE_PATH + url;
    }

    const finalOptions = {
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        ...options
    };

    if (options.headers) {
        finalOptions.headers = { ...finalOptions.headers, ...options.headers };
    }

    if (finalOptions.body instanceof FormData) {
        delete finalOptions.headers['Content-Type'];
    }

    try {
        const response = await fetch(url, finalOptions);

        if (response.status === 401) {
            try {
                const data = await response.json();
                if (data.auth_required || data.redirect) {
                    console.error('Session expired or unauthorized access');
                    alert('Session expirée. Veuillez vous reconnecter.');
                    window.location.href = BASE_PATH + '/login';
                    return null;
                }
            } catch (e) {
                console.error('Authentication error:', e);
                alert('Erreur d\'authentification. Veuillez vous reconnecter.');
                window.location.href = BASE_PATH + '/login';
                return null;
            }
        }

        return response;
    } catch (error) {
        console.error('Network error:', error);
        throw error;
    }
}

// Check session status
async function checkSessionStatus() {
    try {
        const response = await fetch(BASE_PATH + '/check_session', {
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!response.ok) {
            return { authenticated: false };
        }

        return await response.json();
    } catch (error) {
        console.error('Session check failed:', error);
        return { authenticated: false };
    }
}

// Initialize session check on page load
async function initializeSessionCheck(requiredUserType = null) {
    const sessionData = await checkSessionStatus();

    if (!sessionData.authenticated) {
        console.error('User not authenticated');
        window.location.href = BASE_PATH + '/login';
        return false;
    }

    if (requiredUserType && sessionData.user_type !== requiredUserType) {
        console.error(`Wrong user type. Expected: ${requiredUserType}, Got: ${sessionData.user_type}`);
        alert('Accès non autorisé pour ce type d\'utilisateur.');
        window.location.href = BASE_PATH + '/login';
        return false;
    }

    console.log('Session verified:', sessionData);
    return true;
}

// Periodic session check (every 5 minutes)
function startSessionMonitoring() {
    setInterval(async () => {
        const sessionData = await checkSessionStatus();
        if (!sessionData.authenticated) {
            console.warn('Session expired during monitoring');
            alert('Votre session a expiré. Veuillez vous reconnecter.');
            window.location.href = BASE_PATH + '/login';
        }
    }, 5 * 60 * 1000);
}
