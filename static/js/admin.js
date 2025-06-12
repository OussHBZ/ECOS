
// Global variables for admin interface
let availableStudents = [];
let selectedStudents = [];
let availableStations = [];
let selectedStations = [];

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Admin interface initializing...');
    
    // First, check session status
    const isAuthenticated = await initializeSessionCheck('admin');
    if (!isAuthenticated) {
        return; // Stop initialization if not authenticated
    }
    
    // Start session monitoring
    startSessionMonitoring();
    
    console.log('Admin interface authenticated and initialized');
    
    // Load overview data by default
    await loadOverviewData();
    
    // Set up event listeners for search inputs
    const stationsSearch = document.getElementById('admin-stations-search');
    if (stationsSearch) {
        stationsSearch.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                searchAdminStations();
            }
        });
    }
    
    const studentsSearch = document.getElementById('admin-students-search');
    if (studentsSearch) {
        studentsSearch.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                searchAdminStudents();
            }
        });
    }
    
    // Add event listeners for student and station search in modal
    const studentSearch = document.getElementById('student-search');
    if (studentSearch) {
        studentSearch.addEventListener('input', updateAvailableStudentsList);
    }
    
    const stationSearch = document.getElementById('station-search');
    if (stationSearch) {
        stationSearch.addEventListener('input', updateAvailableStationsList);
    }
    
    // Set up form event listeners - PREVENT DOUBLE BINDING
    // Competition session form
    const competitionForm = document.getElementById('create-competition-session-form');
    if (competitionForm) {
        // Remove any existing event listeners by cloning the form
        const newCompetitionForm = competitionForm.cloneNode(true);
        competitionForm.parentNode.replaceChild(newCompetitionForm, competitionForm);
        
        // Add the event listener to the new form
        newCompetitionForm.addEventListener('submit', createCompetitionSession);
        console.log('Competition session form event listener attached');
    }
    
    // Regular session form
    const createSessionForm = document.getElementById('create-session-form');
    if (createSessionForm) {
        // Remove any existing event listeners by cloning the form
        const newSessionForm = createSessionForm.cloneNode(true);
        createSessionForm.parentNode.replaceChild(newSessionForm, createSessionForm);
        
        // Add the event listener to the new form
        newSessionForm.addEventListener('submit', createSession);
        console.log('Regular session form event listener attached');
    }
    
    // Close modal functionality
    document.querySelectorAll('.close-modal').forEach(closeBtn => {
        closeBtn.addEventListener('click', function() {
            const modal = this.closest('.modal');
            if (modal) {
                modal.classList.remove('visible');
                modal.classList.add('hidden');
            }
        });
    });
    
    // Close modals when clicking outside
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            e.target.classList.remove('visible');
            e.target.classList.add('hidden');
        }
    });
});


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
    
    // FIXED: Merge options properly without recursion
    const finalOptions = { ...options, ...defaultOptions };
    if (options.headers) {
        finalOptions.headers = { ...defaultOptions.headers, ...options.headers };
    }
    
    try {
        // FIXED: Use native fetch instead of calling authenticatedFetch recursively
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


// Tab navigation for admin interface
function showAdminTab(tabName) {
    console.log('Showing admin tab:', tabName);
    
    // Hide all tab contents
    document.querySelectorAll('.admin-tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all nav tabs
    document.querySelectorAll('.admin-nav-tabs .nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab
    const selectedTab = document.getElementById(tabName);
    if (selectedTab) {
        selectedTab.classList.add('active');
    } else {
        console.error('Tab not found:', tabName);
        return;
    }
    
    // Add active class to clicked nav tab
    if (event && event.target) {
        event.target.classList.add('active');
    }
    
    // Load content for specific tabs
    if (tabName === 'overview-tab') {
        loadOverviewData();
    } else if (tabName === 'stations-tab') {
        loadAdminStations();
    } else if (tabName === 'students-tab') {
        loadAdminStudents();
    } else if (tabName === 'competition-sessions-tab') {
        loadAdminCompetitionSessions();
    }
}


// Updated function for competition sessions
async function loadAdminCompetitionSessions() {
    try {
        console.log('Loading admin competition sessions...');
        
        const response = await authenticatedFetch('/admin/competition-sessions');
        if (!response) return; // Authentication failed
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('Competition sessions data:', data);
        
        // Update stats
        const totalSessionsElement = document.getElementById('total-sessions');
        const scheduledSessionsElement = document.getElementById('scheduled-sessions');
        const activeSessionsElement = document.getElementById('active-sessions');
        
        if (totalSessionsElement) totalSessionsElement.textContent = data.total;
        if (scheduledSessionsElement) scheduledSessionsElement.textContent = data.scheduled;
        if (activeSessionsElement) activeSessionsElement.textContent = data.active;
        
        // Update table
        const tableBody = document.getElementById('competition-sessions-table-body');
        if (!tableBody) {
            console.error('Competition sessions table body not found');
            return;
        }
        
        tableBody.innerHTML = '';
        
        if (data.sessions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="9" style="text-align: center;">Aucune session de compétition trouvée</td></tr>';
        } else {
            data.sessions.forEach(session => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${session.name}</td>
                    <td>${session.start_time}</td>
                    <td>${session.end_time}</td>
                    <td><span class="participant-badge">${session.participant_count}</span></td>
                    <td><span class="station-badge">${session.station_count}</span></td>
                    <td><span class="setting-badge">${session.stations_per_session}</span></td>
                    <td><span class="time-badge">${session.time_per_station}min</span></td>
                    <td><span class="status-badge status-${session.status}">${session.status_display}</span></td>
                    <td>
                        <button class="view-button" onclick="viewCompetitionSessionDetails(${session.id})">Voir</button>
                        ${session.status === 'scheduled' && session.can_start ? 
                            `<button class="start-button" onclick="startCompetition(${session.id})">Démarrer</button>` : ''}
                        ${session.status === 'scheduled' ? 
                            `<button class="edit-button" onclick="editCompetitionSession(${session.id})">Modifier</button>` : ''}
                        <button class="delete-button" onclick="deleteCompetitionSession(${session.id})">Supprimer</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
        }
        
        console.log('Competition sessions loaded successfully');
        
    } catch (error) {
        console.error('Error loading admin competition sessions:', error);
        const tableBody = document.getElementById('competition-sessions-table-body');
        if (tableBody) {
            tableBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: red;">Erreur lors du chargement: ${error.message}</td></tr>`;
        }
    }
}

// View competition session details
async function viewCompetitionSessionDetails(sessionId) {
    try {
        console.log(`Viewing competition session details for ID: ${sessionId}`);
        
        const response = await authenticatedFetch(`/admin/competition-sessions/${sessionId}`);
        if (!response.ok) {
            throw new Error('Failed to load session details');
        }
        
        const sessionData = await response.json();
        
        // Create session details HTML
        let detailsHTML = `
            <div class="competition-session-details">
                <h4>${sessionData.name}</h4>
                <p><strong>Description:</strong> ${sessionData.description || 'Aucune description'}</p>
                <p><strong>Début:</strong> ${sessionData.start_time}</p>
                <p><strong>Fin:</strong> ${sessionData.end_time}</p>
                <p><strong>Statut:</strong> <span class="status-badge status-${sessionData.status}">${sessionData.status_display}</span></p>
                
                <div class="competition-settings">
                    <h5>Paramètres de la Compétition</h5>
                    <p><strong>Stations par session:</strong> ${sessionData.stations_per_session}</p>
                    <p><strong>Temps par station:</strong> ${sessionData.time_per_station} minutes</p>
                    <p><strong>Temps entre stations:</strong> ${sessionData.time_between_stations} minutes</p>
                    <p><strong>Stations aléatoires:</strong> ${sessionData.randomize_stations ? 'Oui' : 'Non'}</p>
                </div>
                
                <h5>Participants (${sessionData.participants.length})</h5>
                <div class="participants-list">`;
        
        if (sessionData.participants.length > 0) {
            sessionData.participants.forEach(participant => {
                detailsHTML += `
                    <div class="participant-item">
                        <strong>${participant.name}</strong> (${participant.student_code})
                        <small>Statut: ${getStatusDisplay(participant.status)} | 
                               Station: ${participant.current_station}/${sessionData.stations_per_session} | 
                               Progrès: ${participant.progress}%</small>
                    </div>`;
            });
        } else {
            detailsHTML += '<p>Aucun participant</p>';
        }
        
        detailsHTML += `</div>
                <h5>Banque de Stations (${sessionData.stations.length})</h5>
                <div class="stations-list">`;
        
        if (sessionData.stations.length > 0) {
            sessionData.stations.forEach(station => {
                detailsHTML += `
                    <div class="station-item">
                        <strong>Station ${station.case_number}</strong> - ${station.specialty}
                        <small>Durée: ${station.consultation_time} min</small>
                    </div>`;
            });
        } else {
            detailsHTML += '<p>Aucune station assignée</p>';
        }
        
        detailsHTML += '</div>';
        
        // Add leaderboard if available
        if (sessionData.leaderboard && sessionData.leaderboard.length > 0) {
            detailsHTML += `
                <h5>Classement</h5>
                <div class="leaderboard">
                    <table class="leaderboard-table">
                        <thead>
                            <tr>
                                <th>Rang</th>
                                <th>Étudiant</th>
                                <th>Score Moyen</th>
                                <th>Stations Complétées</th>
                            </tr>
                        </thead>
                        <tbody>`;
            
            sessionData.leaderboard.slice(0, 10).forEach(entry => {
                detailsHTML += `
                    <tr>
                        <td>${entry.rank}</td>
                        <td>${entry.student_name} (${entry.student_code})</td>
                        <td>${entry.average_score}%</td>
                        <td>${entry.stations_completed}</td>
                    </tr>`;
            });
            
            detailsHTML += '</tbody></table></div>';
        }
        
        detailsHTML += '</div>';
        
        // Show in modal
        let modal = document.getElementById('competition-session-details-modal');
        if (!modal) {
            modal = createCompetitionSessionDetailsModal();
        }
        
        document.getElementById('competition-session-details-content').innerHTML = detailsHTML;
        modal.classList.remove('hidden');
        modal.classList.add('visible');
        
    } catch (error) {
        console.error('Error viewing competition session details:', error);
        alert('Erreur lors du chargement des détails de la session de compétition');
    }
}

// Start competition
async function startCompetition(sessionId) {
    if (!confirm('Êtes-vous sûr de vouloir démarrer cette compétition ? Cette action est irréversible.')) {
        return;
    }
    
    try {
        const response = await authenticatedFetch(`/admin/competition-sessions/${sessionId}/start`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            alert(result.message);
            loadAdminCompetitionSessions(); // Refresh sessions list
        } else {
            alert(`Erreur: ${result.error}`);
        }
        
    } catch (error) {
        console.error('Error starting competition:', error);
        alert('Erreur lors du démarrage de la compétition');
    }
}

// Edit competition session
async function editCompetitionSession(sessionId) {
    try {
        console.log(`Editing competition session ID: ${sessionId}`);
        
        // Load current session data
        const response = await authenticatedFetch(`/admin/competition-sessions/${sessionId}/edit`);
        if (!response.ok) {
            throw new Error('Failed to load session data for editing');
        }
        
        const sessionData = await response.json();
        
        // Populate the create competition session modal with existing data
        document.getElementById('competition-session-name').value = sessionData.name;
        document.getElementById('competition-session-description').value = sessionData.description || '';
        document.getElementById('competition-session-start').value = sessionData.start_time.slice(0, 16);
        document.getElementById('competition-session-end').value = sessionData.end_time.slice(0, 16);
        document.getElementById('stations-per-session').value = sessionData.stations_per_session;
        document.getElementById('time-per-station').value = sessionData.time_per_station;
        document.getElementById('time-between-stations').value = sessionData.time_between_stations;
        document.getElementById('randomize-stations').checked = sessionData.randomize_stations;
        
        // Load available students and stations
        await loadAvailableStudents();
        await loadAvailableStations();
        
        // Pre-select participants
        selectedStudents = availableStudents.filter(student => 
            sessionData.participants.includes(student.id)
        );
        
        // Pre-select stations
        selectedStations = availableStations.filter(station => 
            sessionData.stations.includes(station.case_number)
        );
        
        updateSelectedStudentsList();
        updateSelectedStationsList();
        
        // Change form behavior for editing
        const form = document.getElementById('create-competition-session-form');
        form.dataset.editMode = 'true';
        form.dataset.sessionId = sessionId;
        
        // Change modal title
        const modalTitle = document.querySelector('#create-competition-session-modal h3');
        modalTitle.textContent = 'Modifier la Session de Compétition';
        
        // Change submit button text
        const submitButton = document.querySelector('#create-competition-session-form button[type="submit"]');
        submitButton.textContent = 'Mettre à jour la Session';
        
        // Show modal
        document.getElementById('create-competition-session-modal').classList.remove('hidden');
        document.getElementById('create-competition-session-modal').classList.add('visible');
        
    } catch (error) {
        console.error('Error editing competition session:', error);
        alert('Erreur lors du chargement des données de la session');
    }
}

// Delete competition session
async function deleteCompetitionSession(sessionId) {
    if (!confirm('Êtes-vous sûr de vouloir supprimer cette session de compétition ? Cette action est irréversible.')) {
        return;
    }
    
    try {
        console.log(`Deleting competition session ID: ${sessionId}`);
        
        const response = await authenticatedFetch(`/admin/competition-sessions/${sessionId}/delete`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            alert(result.message);
            loadAdminCompetitionSessions(); // Refresh sessions list
        } else {
            alert(`Erreur: ${result.error}`);
        }
        
    } catch (error) {
        console.error('Error deleting competition session:', error);
        alert('Erreur lors de la suppression de la session de compétition');
    }
}

// Competition session functions (add more as needed)
function openCreateCompetitionSessionModal() {
    console.log('Opening create competition session modal...');
    
    // Reset form to creation mode
    const form = document.getElementById('create-competition-session-form');
    if (form) {
        form.reset();
        delete form.dataset.editMode;
        delete form.dataset.sessionId;
    }
    
    // Reset modal title and button text
    const modalTitle = document.querySelector('#create-competition-session-modal h3');
    if (modalTitle) {
        modalTitle.textContent = 'Créer une Nouvelle Session de Compétition';
    }
    
    const submitButton = document.querySelector('#create-competition-session-form button[type="submit"]');
    if (submitButton) {
        submitButton.textContent = 'Créer la Session';
    }
    
    // Reset selections
    selectedStudents = [];
    selectedStations = [];
    
    // Load data
    loadAvailableStudents();
    loadAvailableStations();
    
    // Show modal
    const modal = document.getElementById('create-competition-session-modal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('visible');
        console.log('Modal opened successfully');
    } else {
        console.error('Create competition session modal not found!');
    }
}



// Close create competition session modal
function closeCreateCompetitionSessionModal() {
    const modal = document.getElementById('create-competition-session-modal');
    const form = document.getElementById('create-competition-session-form');
    
    // Reset edit mode
    delete form.dataset.editMode;
    delete form.dataset.sessionId;
    
    // Reset modal title
    const modalTitle = document.querySelector('#create-competition-session-modal h3');
    modalTitle.textContent = 'Créer une Nouvelle Session de Compétition';
    
    // Reset submit button text
    const submitButton = document.querySelector('#create-competition-session-form button[type="submit"]');
    submitButton.textContent = 'Créer la Session';
    
    // Hide modal and reset form
    modal.classList.remove('visible');
    modal.classList.add('hidden');
    form.reset();
    selectedStudents = [];
    selectedStations = [];
    updateSelectedStudentsList();
    updateSelectedStationsList();
}

// Create competition session details modal if it doesn't exist
function createCompetitionSessionDetailsModal() {
    const modalHTML = `
        <div id="competition-session-details-modal" class="modal hidden">
            <div class="modal-content">
                <span class="close-modal">&times;</span>
                <h3>Détails de la Session de Compétition</h3>
                <div id="competition-session-details-content"></div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Add close functionality
    const modal = document.getElementById('competition-session-details-modal');
    const closeBtn = modal.querySelector('.close-modal');
    closeBtn.addEventListener('click', () => {
        modal.classList.remove('visible');
        modal.classList.add('hidden');
    });
    
    return modal;
}

// Create competition session
async function createCompetitionSession(event) {
    event.preventDefault();
    event.stopPropagation(); // Prevent event bubbling
    
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    
    // Prevent double submission by disabling the submit button
    if (submitButton.disabled) {
        console.log('Form already being submitted, ignoring duplicate submission');
        return false;
    }
    
    // Disable submit button to prevent double submission
    submitButton.disabled = true;
    const originalButtonText = submitButton.textContent;
    submitButton.textContent = 'Création en cours...';
    
    const isEditMode = form.dataset.editMode === 'true';
    const sessionId = form.dataset.sessionId;
    
    console.log(isEditMode ? 'Updating competition session...' : 'Creating competition session...');
    
    try {
        const formData = new FormData(form);
        
        // Validate required fields
        const sessionName = formData.get('session_name');
        const startTime = formData.get('start_time');
        const endTime = formData.get('end_time');
        const stationsPerSession = formData.get('stations_per_session');
        const timePerStation = formData.get('time_per_station');
        
        if (!sessionName || !startTime || !endTime || !stationsPerSession || !timePerStation) {
            alert('Veuillez remplir tous les champs obligatoires');
            return;
        }
        
        if (selectedStudents.length === 0) {
            alert('Veuillez sélectionner au moins un participant');
            return;
        }
        
        if (selectedStations.length === 0) {
            alert('Veuillez sélectionner au moins une station');
            return;
        }
        
        if (selectedStations.length < parseInt(stationsPerSession)) {
            alert(`La banque de stations doit contenir au moins ${stationsPerSession} stations`);
            return;
        }
        
        // Format datetime for backend
        const startDateTime = new Date(startTime).toISOString();
        const endDateTime = new Date(endTime).toISOString();
        
        const sessionData = {
            name: sessionName,
            description: formData.get('session_description') || '',
            start_time: startDateTime,
            end_time: endDateTime,
            stations_per_session: parseInt(stationsPerSession),
            time_per_station: parseInt(timePerStation),
            time_between_stations: parseInt(formData.get('time_between_stations') || 2),
            randomize_stations: formData.get('randomize_stations') === 'on',
            participants: selectedStudents.map(s => s.id),
            stations: selectedStations.map(s => s.case_number)
        };
        
        console.log('Competition session data to send:', sessionData);
        
        const url = isEditMode ? `/admin/competition-sessions/${sessionId}/edit` : '/admin/create-competition-session';
        const response = await authenticatedFetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(sessionData)
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            const message = isEditMode ? 'Session de compétition mise à jour avec succès!' : `Session de compétition créée avec succès! ID: ${result.session_id}`;
            alert(message);
            closeCreateCompetitionSessionModal();
            loadAdminCompetitionSessions(); // Refresh sessions list
        } else {
            console.error('Error response:', result);
            alert(`Erreur: ${result.error || 'Erreur inconnue'}`);
        }
        
    } catch (error) {
        console.error('Network or parsing error:', error);
        alert('Erreur de connexion lors de la création/modification de la session de compétition');
    } finally {
        // Re-enable submit button
        submitButton.disabled = false;
        submitButton.textContent = originalButtonText;
    }
    
    return false; // Prevent any default form submission
}

// Helper function to get status display in French
function getStatusDisplay(status) {
    const statusMap = {
        'registered': 'Inscrit',
        'logged_in': 'Connecté',
        'active': 'En cours',
        'between_stations': 'Entre stations',
        'completed': 'Terminé'
    };
    return statusMap[status] || status;
}

// Add CSS styles for competition sessions
const competitionStyles = `
/* Competition Session Styles */
.competition-session-details {
    max-height: 70vh;
    overflow-y: auto;
}

.competition-settings {
    background: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
}

.competition-settings h5 {
    margin-top: 0;
    color: #ff7e5f;
}

.participants-list,
.stations-list {
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid #eee;
    border-radius: 6px;
    padding: 10px;
    margin: 10px 0;
    background: #f9f9f9;
}

.participant-item,
.station-item {
    padding: 8px;
    margin-bottom: 8px;
    background: white;
    border-radius: 4px;
    border-left: 3px solid #2196F3;
}

.participant-item small,
.station-item small {
    display: block;
    color: #666;
    font-size: 12px;
    margin-top: 4px;
}

.leaderboard {
    margin: 15px 0;
}

.leaderboard-table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.leaderboard-table th {
    background: linear-gradient(135deg, #ff7e5f, #feb47b);
    color: white;
    padding: 12px;
    text-align: left;
    font-weight: bold;
}

.leaderboard-table td {
    padding: 10px 12px;
    border-bottom: 1px solid #eee;
}

.leaderboard-table tr:hover {
    background: #f8f9fa;
}

/* Competition Session Form Styles */
.competition-form-section {
    background: #f8f9fa;
    padding: 20px;
    border-radius: 8px;
    margin: 20px 0;
    border-left: 4px solid #ff7e5f;
}

.competition-form-section h4 {
    margin-top: 0;
    color: #ff7e5f;
}

.form-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 15px;
    margin-bottom: 15px;
}

.form-group-inline {
    display: flex;
    align-items: center;
    gap: 10px;
}

.form-group-inline input[type="checkbox"] {
    transform: scale(1.2);
}

/* Badge styles for competition */
.setting-badge {
    background: #E8F5E8;
    color: #2E7D32;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: bold;
}

.time-badge {
    background: #FFF3E0;
    color: #EF6C00;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: bold;
}

.start-button {
    background: #4CAF50;
    color: white;
    border: none;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    margin-right: 5px;
}

.start-button:hover {
    background: #45a049;
}

/* Responsive design for competition */
@media (max-width: 768px) {
    .form-row {
        grid-template-columns: 1fr;
    }
    
    .competition-settings {
        padding: 10px;
    }
    
    .leaderboard-table {
        font-size: 12px;
    }
    
    .leaderboard-table th,
    .leaderboard-table td {
        padding: 8px;
    }
}
`;

// Add the competition styles to the document
const competitionStyleSheet = document.createElement('style');
competitionStyleSheet.textContent = competitionStyles;
document.head.appendChild(competitionStyleSheet);

// Load overview data
async function loadOverviewData() {
    try {
        const response = await authenticatedFetch('/admin/overview');
        if (!response) return; // Authentication failed
        
        if (!response.ok) {
            throw new Error('Failed to load overview data');
        }
        
        const data = await response.json();
        
        // Update overview stats
        document.getElementById('total-stations-overview').textContent = data.total_stations;
        document.getElementById('total-students-overview').textContent = data.total_students;
        document.getElementById('active-sessions-overview').textContent = data.active_sessions;
        document.getElementById('total-consultations-overview').textContent = data.total_consultations;
        
        // Update recent activity
        const activityBody = document.getElementById('recent-activity-body');
        activityBody.innerHTML = '';
        
        if (data.recent_activity.length === 0) {
            activityBody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Aucune activité récente</td></tr>';
        } else {
            data.recent_activity.forEach(activity => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${activity.date}</td>
                    <td>${activity.student_name} (${activity.student_code})</td>
                    <td>${activity.case_number}</td>
                    <td><span class="score-badge score-${getScoreClass(activity.score)}">${activity.score}%</span></td>
                    <td><span class="status-badge status-${activity.status.toLowerCase().replace(' ', '-')}">${activity.status}</span></td>
                `;
                activityBody.appendChild(row);
            });
        }
        
    } catch (error) {
        console.error('Error loading overview data:', error);
    }
}

// Load admin stations
async function loadAdminStations(searchQuery = '') {
    try {
        let url = '/admin/stations';
        if (searchQuery) {
            url += `?search=${encodeURIComponent(searchQuery)}`;
        }
        
        const response = await authenticatedFetch(url);
        if (!response) return; // Authentication failed
        
        if (!response.ok) {
            throw new Error('Failed to load stations');
        }
        
        const data = await response.json();
        
        // Update stats
        document.getElementById('total-stations').textContent = data.total;
        document.getElementById('avg-station-score').textContent = data.avg_score + '%';
        document.getElementById('most-used-specialty').textContent = data.most_used_specialty || 'N/A';
        
        // Update table
        const tableBody = document.getElementById('admin-stations-table-body');
        tableBody.innerHTML = '';
        
        if (data.stations.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Aucune station trouvée</td></tr>';
        } else {
            data.stations.forEach(station => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${station.case_number}</td>
                    <td>${station.specialty}</td>
                    <td>${station.consultation_time}</td>
                    <td>${station.created_at}</td>
                    <td><span class="completion-badge">${station.usage_count}</span></td>
                    <td><span class="score-badge score-${getScoreClass(station.average_score)}">${station.average_score}%</span></td>
                    <td>
                        <button class="view-button" onclick="viewStationDetails('${station.case_number}')">Voir</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
        }
        
    } catch (error) {
        console.error('Error loading admin stations:', error);
        document.getElementById('admin-stations-table-body').innerHTML = 
            '<tr><td colspan="7" style="text-align: center;">Erreur lors du chargement</td></tr>';
    }
}
// View session details
async function viewSessionDetails(sessionId) {
    try {
        console.log(`Viewing session details for ID: ${sessionId}`);
        
        const response = await authenticatedFetch(`/admin/sessions/${sessionId}`);
        if (!response.ok) {
            throw new Error('Failed to load session details');
        }
        
        const sessionData = await response.json();
        
        // Create session details HTML
        let detailsHTML = `
            <div class="session-details">
                <h4>${sessionData.name}</h4>
                <p><strong>Description:</strong> ${sessionData.description || 'Aucune description'}</p>
                <p><strong>Début:</strong> ${sessionData.start_time}</p>
                <p><strong>Fin:</strong> ${sessionData.end_time}</p>
                <p><strong>Statut:</strong> <span class="status-badge status-${sessionData.status}">${sessionData.status_display}</span></p>
                <p><strong>Créé le:</strong> ${sessionData.created_at} par ${sessionData.created_by}</p>
                
                <h5>Participants (${sessionData.participants.length})</h5>
                <div class="participants-list">`;
        
        if (sessionData.participants.length > 0) {
            sessionData.participants.forEach(participant => {
                detailsHTML += `
                    <div class="participant-item">
                        <strong>${participant.name}</strong> (${participant.student_code})
                        <small>Ajouté le ${participant.added_at}</small>
                    </div>`;
            });
        } else {
            detailsHTML += '<p>Aucun participant</p>';
        }
        
        detailsHTML += `</div>
                <h5>Stations (${sessionData.stations.length})</h5>
                <div class="stations-list">`;
        
        if (sessionData.stations.length > 0) {
            sessionData.stations.forEach(station => {
                detailsHTML += `
                    <div class="station-item">
                        <strong>Station ${station.case_number}</strong> - ${station.specialty}
                        <small>Durée: ${station.consultation_time} min | Ordre: ${station.station_order}</small>
                    </div>`;
            });
        } else {
            detailsHTML += '<p>Aucune station assignée</p>';
        }
        
        detailsHTML += '</div></div>';
        
        // Show in modal (create modal if it doesn't exist)
        let modal = document.getElementById('session-details-modal');
        if (!modal) {
            modal = createSessionDetailsModal();
        }
        
        document.getElementById('session-details-content').innerHTML = detailsHTML;
        modal.classList.remove('hidden');
        modal.classList.add('visible');
        
    } catch (error) {
        console.error('Error viewing session details:', error);
        alert('Erreur lors du chargement des détails de la session');
    }
}

// Edit session
async function editSession(sessionId) {
    try {
        console.log(`Editing session ID: ${sessionId}`);
        
        // Load current session data
        const response = await authenticatedFetch(`/admin/sessions/${sessionId}/edit`);
        if (!response.ok) {
            throw new Error('Failed to load session data for editing');
        }
        
        const sessionData = await response.json();
        
        // Populate the create session modal with existing data
        document.getElementById('session-name').value = sessionData.name;
        document.getElementById('session-description').value = sessionData.description || '';
        document.getElementById('session-start').value = sessionData.start_time.slice(0, 16); // Format for datetime-local
        document.getElementById('session-end').value = sessionData.end_time.slice(0, 16);
        
        // Load available students and stations
        await loadAvailableStudents();
        await loadAvailableStations();
        
        // Pre-select participants
        selectedStudents = availableStudents.filter(student => 
            sessionData.participants.includes(student.id)
        );
        
        // Pre-select stations
        selectedStations = availableStations.filter(station => 
            sessionData.stations.includes(station.case_number)
        );
        
        updateSelectedStudentsList();
        updateSelectedStationsList();
        
        // Change form behavior for editing
        const form = document.getElementById('create-session-form');
        form.dataset.editMode = 'true';
        form.dataset.sessionId = sessionId;
        
        // Change modal title
        const modalTitle = document.querySelector('#create-session-modal h3');
        modalTitle.textContent = 'Modifier la Session OSCE';
        
        // Change submit button text
        const submitButton = document.querySelector('#create-session-form button[type="submit"]');
        submitButton.textContent = 'Mettre à jour la Session';
        
        // Show modal
        document.getElementById('create-session-modal').classList.remove('hidden');
        document.getElementById('create-session-modal').classList.add('visible');
        
    } catch (error) {
        console.error('Error editing session:', error);
        alert('Erreur lors du chargement des données de la session');
    }
}

// Delete session
async function deleteSession(sessionId) {
    if (!confirm('Êtes-vous sûr de vouloir supprimer cette session ? Cette action est irréversible.')) {
        return;
    }
    
    try {
        console.log(`Deleting session ID: ${sessionId}`);
        
        const response = await authenticatedFetch(`/admin/sessions/${sessionId}/delete`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            alert(result.message);
            loadAdminSessions(); // Refresh sessions list
        } else {
            alert(`Erreur: ${result.error}`);
        }
        
    } catch (error) {
        console.error('Error deleting session:', error);
        alert('Erreur lors de la suppression de la session');
    }
}

// Load admin students
async function loadAdminStudents(searchQuery = '') {
    try {
        let url = '/admin/students';
        if (searchQuery) {
            url += `?search=${encodeURIComponent(searchQuery)}`;
        }
        
        const response = await authenticatedFetch(url);
        if (!response) return; // Authentication failed
        
        if (!response.ok) {
            throw new Error('Failed to load students');
        }
        
        const data = await response.json();
        
        // Update stats
        document.getElementById('total-students').textContent = data.total;
        document.getElementById('active-students').textContent = data.active;
        document.getElementById('avg-student-score').textContent = data.avg_score + '%';
        
        // Update table
        const tableBody = document.getElementById('admin-students-table-body');
        tableBody.innerHTML = '';
        
        if (data.students.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Aucun étudiant trouvé</td></tr>';
        } else {
            data.students.forEach(student => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${student.student_code}</td>
                    <td>${student.name}</td>
                    <td>${student.created_at}</td>
                    <td>${student.last_login || 'Jamais'}</td>
                    <td><span class="workout-badge">${student.total_consultations}</span></td>
                    <td><span class="score-badge score-${getScoreClass(student.average_score)}">${student.average_score}%</span></td>
                    <td>
                        <button class="detail-button" onclick="viewStudentDetails(${student.id}, '${student.name}', '${student.student_code}')">Détails</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
        }
        
    } catch (error) {
        console.error('Error loading admin students:', error);
        document.getElementById('admin-students-table-body').innerHTML = 
            '<tr><td colspan="7" style="text-align: center;">Erreur lors du chargement</td></tr>';
    }
}

// Load admin sessions
async function loadAdminSessions() {
    try {
        const response = await authenticatedFetch('/admin/sessions');
        if (!response.ok) {
            throw new Error('Failed to load sessions');
        }
        
        const data = await response.json();
        
        // Update stats
        document.getElementById('total-sessions').textContent = data.total;
        document.getElementById('scheduled-sessions').textContent = data.scheduled;
        document.getElementById('active-sessions').textContent = data.active;
        
        // Update table
        const tableBody = document.getElementById('sessions-table-body');
        tableBody.innerHTML = '';
        
        if (data.sessions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Aucune session trouvée</td></tr>';
        } else {
            data.sessions.forEach(session => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${session.name}</td>
                    <td>${session.start_time}</td>
                    <td>${session.end_time}</td>
                    <td><span class="participant-badge">${session.participant_count}</span></td>
                    <td><span class="station-badge">${session.station_count}</span></td>
                    <td><span class="status-badge status-${session.status}">${session.status_display}</span></td>
                    <td>
                        <button class="view-button" onclick="viewSessionDetails(${session.id})">Voir</button>
                        <button class="edit-button" onclick="editSession(${session.id})">Modifier</button>
                        <button class="delete-button" onclick="deleteSession(${session.id})">Supprimer</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
        }
        
    } catch (error) {
        console.error('Error loading admin sessions:', error);
        document.getElementById('sessions-table-body').innerHTML = 
            '<tr><td colspan="7" style="text-align: center;">Erreur lors du chargement</td></tr>';
    }
}

// Search functions
function searchAdminStations() {
    const searchQuery = document.getElementById('admin-stations-search').value.trim();
    loadAdminStations(searchQuery);
}

function searchAdminStudents() {
    const searchQuery = document.getElementById('admin-students-search').value.trim();
    loadAdminStudents(searchQuery);
}

// View station details
async function viewStationDetails(caseNumber) {
    try {
        const response = await authenticatedFetch(`/get_case/${caseNumber}`);
        if (!response.ok) {
            throw new Error('Failed to load station details');
        }
        
        const data = await response.json();
        
        // Format station details
        let detailsHTML = `
            <div class="station-details">
                <h4>Station ${data.case_number}</h4>
                <p><strong>Spécialité:</strong> ${data.specialty}</p>
                <p><strong>Durée:</strong> ${data.consultation_time} minutes</p>
                
                <h5>Informations du patient</h5>
                <p><strong>Nom:</strong> ${data.patient_info?.name || 'Non spécifié'}</p>
                <p><strong>Âge:</strong> ${data.patient_info?.age || 'Non spécifié'}</p>
                <p><strong>Sexe:</strong> ${data.patient_info?.gender || 'Non spécifié'}</p>
                
                <h5>Symptômes (${data.symptoms?.length || 0})</h5>
                <ul>`;
        
        if (data.symptoms && data.symptoms.length > 0) {
            data.symptoms.forEach(symptom => {
                detailsHTML += `<li>${symptom}</li>`;
            });
        } else {
            detailsHTML += '<li>Aucun symptôme défini</li>';
        }
        
        detailsHTML += `</ul>
                <h5>Grille d'évaluation (${data.evaluation_checklist?.length || 0} éléments)</h5>
                <ul>`;
        
        if (data.evaluation_checklist && data.evaluation_checklist.length > 0) {
            data.evaluation_checklist.forEach(item => {
                detailsHTML += `<li>${item.description} (${item.points} points)</li>`;
            });
        } else {
            detailsHTML += '<li>Aucun élément d\'évaluation défini</li>';
        }
        
        detailsHTML += '</ul></div>';
        
        // Show in modal
        document.getElementById('station-details-content').innerHTML = detailsHTML;
        document.getElementById('station-details-modal').classList.remove('hidden');
        document.getElementById('station-details-modal').classList.add('visible');
        
    } catch (error) {
        console.error('Error loading station details:', error);
        alert('Erreur lors du chargement des détails de la station');
    }
}

// View student details
async function viewStudentDetails(studentId, studentName, studentCode) {
    try {
        const response = await authenticatedFetch(`/admin/students/${studentId}/details`);
        if (!response.ok) {
            throw new Error('Failed to load student details');
        }
        
        const data = await response.json();
        
        // Update modal header
        document.getElementById('student-details-name').textContent = `${studentName} (${studentCode})`;
        
        // Update stats
        document.getElementById('student-total-consultations').textContent = data.total_consultations;
        document.getElementById('student-unique-stations').textContent = data.unique_stations;
        document.getElementById('student-avg-score').textContent = data.average_score + '%';
        
        // Update performance table
        const tableBody = document.getElementById('student-performance-table-body');
        tableBody.innerHTML = '';
        
        if (data.performances.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Aucune performance enregistrée</td></tr>';
        } else {
            data.performances.forEach(perf => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${perf.completed_at}</td>
                    <td>${perf.case_number}</td>
                    <td>${perf.specialty}</td>
                    <td>${perf.score}%</td>
                    <td><span class="grade-badge grade-${perf.grade}">${perf.grade}</span></td>
                    <td>${perf.duration}</td>
                    <td>
                        <button class="view-evaluation-btn" onclick="downloadStudentReport(${perf.id})">
                            Télécharger PDF
                        </button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
        }
        
        // Show modal
        document.getElementById('student-details-modal').classList.remove('hidden');
        document.getElementById('student-details-modal').classList.add('visible');
        
    } catch (error) {
        console.error('Error loading student details:', error);
        alert('Erreur lors du chargement des détails de l\'étudiant');
    }
}

// Download student report
function downloadStudentReport(performanceId) {
    window.location.href = `/admin/download_student_report/${performanceId}`;
}

// Session management functions
function openCreateSessionModal() {
    console.log('Opening create session modal...');
    
    // Reset selections
    selectedStudents = [];
    selectedStations = [];
    
    // Load data
    loadAvailableStudents();
    loadAvailableStations();
    
    // Show modal
    const modal = document.getElementById('create-session-modal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('visible');
        console.log('Modal opened successfully');
    } else {
        console.error('Create session modal not found!');
    }
}

function closeCreateSessionModal() {
    const modal = document.getElementById('create-session-modal');
    const form = document.getElementById('create-session-form');
    
    // Reset edit mode
    delete form.dataset.editMode;
    delete form.dataset.sessionId;
    
    // Reset modal title
    const modalTitle = document.querySelector('#create-session-modal h3');
    modalTitle.textContent = 'Créer une Nouvelle Session OSCE';
    
    // Reset submit button text
    const submitButton = document.querySelector('#create-session-form button[type="submit"]');
    submitButton.textContent = 'Créer la Session';
    
    // Hide modal and reset form
    modal.classList.remove('visible');
    modal.classList.add('hidden');
    form.reset();
    selectedStudents = [];
    selectedStations = [];
    updateSelectedStudentsList();
    updateSelectedStationsList();
}
// Create session details modal if it doesn't exist
function createSessionDetailsModal() {
    const modalHTML = `
        <div id="session-details-modal" class="modal hidden">
            <div class="modal-content">
                <span class="close-modal">&times;</span>
                <h3>Détails de la Session</h3>
                <div id="session-details-content"></div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Add close functionality
    const modal = document.getElementById('session-details-modal');
    const closeBtn = modal.querySelector('.close-modal');
    closeBtn.addEventListener('click', () => {
        modal.classList.remove('visible');
        modal.classList.add('hidden');
    });
    
    return modal;
}
// Load available students for session creation
async function loadAvailableStudents() {
    try {
        console.log('Loading available students...');
        const response = await authenticatedFetch('/admin/available-students');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('Loaded students:', data.students.length);
        
        availableStudents = data.students;
        updateAvailableStudentsList();
        
    } catch (error) {
        console.error('Error loading available students:', error);
        alert('Erreur lors du chargement de la liste des étudiants');
    }
}

// Load available stations for session creation
async function loadAvailableStations() {
    try {
        console.log('Loading available stations...');
        const response = await authenticatedFetch('/admin/available-stations');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('Loaded stations:', data.stations.length);
        
        availableStations = data.stations;
        updateAvailableStationsList();
        
    } catch (error) {
        console.error('Error loading available stations:', error);
        alert('Erreur lors du chargement de la liste des stations');
    }
}

// Update available students list
function updateAvailableStudentsList() {
    const container = document.getElementById('available-students-list');
    const searchTerm = document.getElementById('student-search').value.toLowerCase();
    
    container.innerHTML = '';
    
    availableStudents
        .filter(student => 
            student.name.toLowerCase().includes(searchTerm) || 
            student.student_code.includes(searchTerm)
        )
        .forEach(student => {
            const item = document.createElement('div');
            item.className = 'selection-item';
            item.innerHTML = `
                <input type="checkbox" id="student-${student.id}" value="${student.id}">
                <label for="student-${student.id}">${student.name} (${student.student_code})</label>
            `;
            container.appendChild(item);
        });
}

// Update available stations list
function updateAvailableStationsList() {
    const container = document.getElementById('available-stations-list');
    const searchTerm = document.getElementById('station-search').value.toLowerCase();
    
    container.innerHTML = '';
    
    availableStations
        .filter(station => 
            station.case_number.includes(searchTerm) || 
            station.specialty.toLowerCase().includes(searchTerm)
        )
        .forEach(station => {
            const item = document.createElement('div');
            item.className = 'selection-item';
            item.innerHTML = `
                <input type="checkbox" id="station-${station.case_number}" value="${station.case_number}">
                <label for="station-${station.case_number}">Station ${station.case_number} - ${station.specialty}</label>
            `;
            container.appendChild(item);
        });
}

// Add selected students to session
function addSelectedStudents() {
    console.log('Adding selected students...');
    const checkboxes = document.querySelectorAll('#available-students-list input[type="checkbox"]:checked');
    console.log('Found checked student checkboxes:', checkboxes.length);
    
    checkboxes.forEach(checkbox => {
        const studentId = parseInt(checkbox.value);
        const student = availableStudents.find(s => s.id === studentId);
        
        console.log(`Processing student ID ${studentId}:`, student);
        
        if (student && !selectedStudents.find(s => s.id === studentId)) {
            selectedStudents.push(student);
            console.log(`Added student: ${student.name} (${student.student_code})`);
        }
        
        checkbox.checked = false;
    });
    
    console.log('Total selected students:', selectedStudents.length);
    updateSelectedStudentsList();
}

// Remove selected students from session
function removeSelectedStudents() {
    const checkboxes = document.querySelectorAll('#selected-students-list input[type="checkbox"]:checked');
    
    checkboxes.forEach(checkbox => {
        const studentId = parseInt(checkbox.value);
        selectedStudents = selectedStudents.filter(s => s.id !== studentId);
    });
    
    updateSelectedStudentsList();
}

// Add selected stations to session
function addSelectedStations() {
    console.log('Adding selected stations...');
    const checkboxes = document.querySelectorAll('#available-stations-list input[type="checkbox"]:checked');
    console.log('Found checked station checkboxes:', checkboxes.length);
    
    checkboxes.forEach(checkbox => {
        const caseNumber = checkbox.value;
        const station = availableStations.find(s => s.case_number === caseNumber);
        
        console.log(`Processing station ${caseNumber}:`, station);
        
        if (station && !selectedStations.find(s => s.case_number === caseNumber)) {
            selectedStations.push(station);
            console.log(`Added station: ${station.case_number} - ${station.specialty}`);
        }
        
        checkbox.checked = false;
    });
    
    console.log('Total selected stations:', selectedStations.length);
    updateSelectedStationsList();
}

// Remove selected stations from session
function removeSelectedStations() {
    const checkboxes = document.querySelectorAll('#selected-stations-list input[type="checkbox"]:checked');
    
    checkboxes.forEach(checkbox => {
        const caseNumber = checkbox.value;
        selectedStations = selectedStations.filter(s => s.case_number !== caseNumber);
    });
    
    updateSelectedStationsList();
}

// Update selected students list
function updateSelectedStudentsList() {
    const container = document.getElementById('selected-students-list');
    container.innerHTML = '';
    
    selectedStudents.forEach(student => {
        const item = document.createElement('div');
        item.className = 'selection-item';
        item.innerHTML = `
            <input type="checkbox" id="selected-student-${student.id}" value="${student.id}">
            <label for="selected-student-${student.id}">${student.name} (${student.student_code})</label>
        `;
        container.appendChild(item);
    });
}

// Update selected stations list
function updateSelectedStationsList() {
    const container = document.getElementById('selected-stations-list');
    container.innerHTML = '';
    
    selectedStations.forEach(station => {
        const item = document.createElement('div');
        item.className = 'selection-item';
        item.innerHTML = `
            <input type="checkbox" id="selected-station-${station.case_number}" value="${station.case_number}">
            <label for="selected-station-${station.case_number}">Station ${station.case_number} - ${station.specialty}</label>
        `;
        container.appendChild(item);
    });
}

// Create session
async function createSession(event) {
    event.preventDefault();
    event.stopPropagation(); // Prevent event bubbling
    
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    
    // Prevent double submission by disabling the submit button
    if (submitButton.disabled) {
        console.log('Form already being submitted, ignoring duplicate submission');
        return false;
    }
    
    // Disable submit button to prevent double submission
    submitButton.disabled = true;
    const originalButtonText = submitButton.textContent;
    submitButton.textContent = 'Création en cours...';
    
    const isEditMode = form.dataset.editMode === 'true';
    const sessionId = form.dataset.sessionId;
    
    console.log(isEditMode ? 'Updating session...' : 'Creating session...');
    
    try {
        const formData = new FormData(form);
        
        // Validate required fields
        const sessionName = formData.get('session_name');
        const startTime = formData.get('start_time');
        const endTime = formData.get('end_time');
        
        if (!sessionName || !startTime || !endTime) {
            alert('Veuillez remplir tous les champs obligatoires');
            return;
        }
        
        if (selectedStudents.length === 0) {
            alert('Veuillez sélectionner au moins un étudiant');
            return;
        }
        
        if (selectedStations.length === 0) {
            alert('Veuillez sélectionner au moins une station');
            return;
        }
        
        // Format datetime for backend
        const startDateTime = new Date(startTime).toISOString();
        const endDateTime = new Date(endTime).toISOString();
        
        const sessionData = {
            name: sessionName,
            description: formData.get('session_description') || '',
            start_time: startDateTime,
            end_time: endDateTime,
            participants: selectedStudents.map(s => s.id),
            stations: selectedStations.map(s => s.case_number)
        };
        
        console.log('Session data to send:', sessionData);
        
        const url = isEditMode ? `/admin/sessions/${sessionId}/edit` : '/admin/create-session';
        const response = await authenticatedFetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(sessionData)
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            const message = isEditMode ? 'Session mise à jour avec succès!' : `Session créée avec succès! ID: ${result.session_id}`;
            alert(message);
            closeCreateSessionModal();
            loadAdminSessions(); // Refresh sessions list
        } else {
            console.error('Error response:', result);
            alert(`Erreur: ${result.error || 'Erreur inconnue'}`);
        }
        
    } catch (error) {
        console.error('Network or parsing error:', error);
        alert('Erreur de connexion lors de la création/modification de la session');
    } finally {
        // Re-enable submit button
        submitButton.disabled = false;
        submitButton.textContent = originalButtonText;
    }
    
    return false; // Prevent any default form submission
}

// Helper function to get score class
function getScoreClass(score) {
    if (score >= 90) return 'excellent';
    if (score >= 80) return 'good';
    if (score >= 70) return 'average';
    if (score >= 60) return 'below-average';
    return 'poor';
}


// Debug function to check if everything is loaded correctly
function debugAdminInterface() {
    console.log('=== ADMIN INTERFACE DEBUG ===');
    console.log('Competition sessions table:', document.getElementById('competition-sessions-table-body'));
    console.log('Create session modal:', document.getElementById('create-competition-session-modal'));
    console.log('Create session form:', document.getElementById('create-competition-session-form'));
    console.log('Available students list:', document.getElementById('available-students-list'));
    console.log('Selected students list:', document.getElementById('selected-students-list'));
    console.log('Available stations list:', document.getElementById('available-stations-list'));
    console.log('Selected stations list:', document.getElementById('selected-stations-list'));
    console.log('Tab elements:', {
        overviewTab: document.getElementById('overview-tab'),
        stationsTab: document.getElementById('stations-tab'),
        studentsTab: document.getElementById('students-tab'),
        competitionSessionsTab: document.getElementById('competition-sessions-tab')
    });
}

// Make debug function available globally
window.debugAdminInterface = debugAdminInterface;

// Add CSS styles for admin interface
const adminStyles = `
/* Admin Navigation Tabs */
.admin-nav-tabs {
    display: flex;
    margin-bottom: 20px;
    border-bottom: 2px solid #e0e0e0;
    background: white;
    border-radius: 8px 8px 0 0;
    overflow: hidden;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.admin-nav-tabs .nav-tab {
    flex: 1;
    padding: 15px 20px;
    background: #f5f5f5;
    border: none;
    cursor: pointer;
    font-size: 16px;
    font-weight: bold;
    color: #666;
    transition: all 0.3s;
    border-bottom: 3px solid transparent;
}

.admin-nav-tabs .nav-tab.active {
    background: white;
    color: #ff7e5f;
    border-bottom-color: #ff7e5f;
}

.admin-nav-tabs .nav-tab:hover {
    background: #ffeaa7;
    color: #e17055;
}

/* Admin Tab Content */
.admin-tab-content {
    display: none;
}

.admin-tab-content.active {
    display: block;
}

/* Overview styles */
.overview-container,
.stations-management-container,
.students-management-container,
.sessions-management-container {
    background: white;
    padding: 30px;
    border-radius: 15px;
    box-shadow: 0 8px 25px rgba(0,0,0,0.1);
}

.overview-stats,
.stations-stats,
.students-stats,
.sessions-stats,
.student-details-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

/* Selection lists for session creation */
.participants-selection,
.stations-selection {
    display: grid;
    grid-template-columns: 2fr 1fr 2fr;
    gap: 20px;
    align-items: start;
}

.selection-list {
    border: 1px solid #ddd;
    border-radius: 8px;
    max-height: 300px;
    overflow-y: auto;
    padding: 10px;
    background: #f9f9f9;
}

.selection-item {
    padding: 8px;
    margin-bottom: 5px;
    background: white;
    border-radius: 4px;
    border: 1px solid #eee;
}

.selection-item input[type="checkbox"] {
    margin-right: 10px;
}

.selection-controls {
    display: flex;
    flex-direction: column;
    gap: 10px;
    justify-content: center;
}

/* Badges */
.participant-badge,
.status-scheduled { background: #E3F2FD; color: #1565C0; }
.status-active { background: #E8F5E8; color: #2E7D32; }
.status-completed { background: #F3E5F5; color: #7B1FA2; }
.status-cancelled { background: #FFEBEE; color: #C62828; }

/* Tables */
.activity-table-container,
.student-performance-table-container {
    background: white;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    margin-top: 20px;
}

.activity-table,
.sessions-table,
.student-performance-table {
    width: 100%;
    border-collapse: collapse;
}

.activity-table th,
.sessions-table th,
.student-performance-table th {
    background: linear-gradient(135deg, #ff7e5f, #feb47b);
    color: white;
    padding: 15px;
    text-align: left;
    font-weight: bold;
}

.activity-table td,
.sessions-table td,
.student-performance-table td {
    padding: 12px 15px;
    border-bottom: 1px solid #eee;
}

.activity-table tr:hover,
.sessions-table tr:hover,
.student-performance-table tr:hover {
    background: #f8f9fa;
}

/* Responsive design */
@media (max-width: 768px) {
    .admin-nav-tabs {
        flex-direction: column;
    }
    
    .overview-stats,
    .stations-stats,
    .students-stats,
    .sessions-stats,
    .student-details-stats {
        grid-template-columns: 1fr;
    }
    
    .participants-selection,
    .stations-selection {
        grid-template-columns: 1fr;
    }
    
    .selection-controls {
        flex-direction: row;
        justify-content: center;
    }
}
`;

// Add the admin styles to the document
const adminStyleSheet = document.createElement('style');
adminStyleSheet.textContent = adminStyles;
document.head.appendChild(adminStyleSheet);

const debugStyles = `
.selection-item {
    padding: 8px;
    margin-bottom: 5px;
    background: white;
    border-radius: 4px;
    border: 1px solid #eee;
    transition: background-color 0.2s;
}

.selection-item:hover {
    background-color: #f0f8ff;
}

.selection-item input[type="checkbox"] {
    margin-right: 10px;
    transform: scale(1.2);
}

.selection-item input[type="checkbox"]:checked + label {
    font-weight: bold;
    color: #2196F3;
}

/* Debug borders for troubleshooting */
.debug-mode .selection-list {
    border: 2px solid red;
}

.debug-mode .selection-item {
    border: 1px solid blue;
}
`;

// Add debug styles to document
const debugStyleSheet = document.createElement('style');
debugStyleSheet.textContent = debugStyles;
document.head.appendChild(debugStyleSheet);

// Add a debug function that can be called from console
window.debugSessionCreation = function() {
    console.log('=== SESSION CREATION DEBUG INFO ===');
    console.log('Available Students:', availableStudents);
    console.log('Selected Students:', selectedStudents);
    console.log('Available Stations:', availableStations);
    console.log('Selected Stations:', selectedStations);
    console.log('Modal elements:');
    console.log('- Create session modal:', document.getElementById('create-session-modal'));
    console.log('- Create session form:', document.getElementById('create-session-form'));
    console.log('- Available students list:', document.getElementById('available-students-list'));
    console.log('- Selected students list:', document.getElementById('selected-students-list'));
    console.log('- Available stations list:', document.getElementById('available-stations-list'));
    console.log('- Selected stations list:', document.getElementById('selected-stations-list'));
};

// Add styles for session details
const sessionDetailsStyles = `
.session-details {
    max-height: 70vh;
    overflow-y: auto;
}

.participants-list,
.stations-list {
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid #eee;
    border-radius: 6px;
    padding: 10px;
    margin: 10px 0;
    background: #f9f9f9;
}

.participant-item,
.station-item {
    padding: 8px;
    margin-bottom: 8px;
    background: white;
    border-radius: 4px;
    border-left: 3px solid #2196F3;
}

.participant-item small,
.station-item small {
    display: block;
    color: #666;
    font-size: 12px;
    margin-top: 4px;
}
`;

// Add session details styles
const sessionStyleSheet = document.createElement('style');
sessionStyleSheet.textContent = sessionDetailsStyles;
document.head.appendChild(sessionStyleSheet);