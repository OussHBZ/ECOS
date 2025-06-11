// static/js/auth-utils.js

// Utility function for authenticated AJAX requests
async function authenticatedFetch(url, options = {}) {
    const defaultOptions = {
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
            ...options.headers
        },
        credentials: 'same-origin' // Important for session cookies
    };
    
    // Merge options
    const finalOptions = { ...options, ...defaultOptions };
    if (options.headers) {
        finalOptions.headers = { ...defaultOptions.headers, ...options.headers };
    }
    
    try {
        const response = await fetch(url, finalOptions);
        
        // Handle authentication errors
        if (response.status === 401) {
            try {
                const data = await response.json();
                if (data.auth_required || data.redirect) {
                    console.error('Session expired or unauthorized access');
                    alert('Session expirée. Veuillez vous reconnecter.');
                    window.location.href = data.redirect || '/login';
                    return null;
                }
            } catch (e) {
                // If response is not JSON, still handle as auth error
                console.error('Authentication error:', e);
                alert('Erreur d\'authentification. Veuillez vous reconnecter.');
                window.location.href = '/login';
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
        const response = await fetch('/check_session', {
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });
        
        if (!response.ok) {
            return { authenticated: false };
        }
        
        const sessionData = await response.json();
        return sessionData;
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
        window.location.href = '/login';
        return false;
    }
    
    // Check if user type matches required type
    if (requiredUserType && sessionData.user_type !== requiredUserType) {
        console.error(`Wrong user type. Expected: ${requiredUserType}, Got: ${sessionData.user_type}`);
        alert('Accès non autorisé pour ce type d\'utilisateur.');
        window.location.href = '/login';
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
            window.location.href = '/login';
        }
    }, 5 * 60 * 1000); // 5 minutes
}