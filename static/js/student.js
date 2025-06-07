// DOM Elements
const specialtyFilter = document.getElementById('specialty-filter');
const caseNumberSearch = document.getElementById('case-number-search');
const casesGrid = document.getElementById('cases-grid');
const startChatButton = document.getElementById('start-chat');
const endChatButton = document.getElementById('end-chat');
const caseSelection = document.getElementById('case-selection');
const chatContainer = document.getElementById('chat-container');
const chatMessages = document.getElementById('chat-messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const currentCaseTitle = document.getElementById('current-case-title');
const timer = document.getElementById('timer');
const evaluationContainer = document.getElementById('evaluation-container');
const evaluationResults = document.getElementById('evaluation-results');
const backToCasesBtn = document.getElementById('back-to-cases');
const downloadEvaluationBtn = document.getElementById('download-evaluation');
const viewCaseImagesBtn = document.getElementById('view-case-images');
// Directives modal functionality
const directivesModal = document.getElementById('directives-modal');
const viewDirectivesBtn = document.getElementById('view-directives-btn');
const directivesContent = document.getElementById('directives-content');
const directivesClose = document.querySelector('.directives-close');

let competitionUpdateInterval = null;
let stationTimer = null;
let countdownTimer = null;
let currentCompetitionId = null;
let currentStationData = null;
let isTimerRunning = false;



let currentCase = null;
let selectedCaseCard = null;
let timerInterval = null;
let remainingTime = 600; // 10 minutes in 
let currentDirectives = null; // Store directives for the current case
let directivesViewed = false; // Track if student has viewed directives





// Filter cases based on selection and search
function filterCases() {
    const selectedSpecialty = specialtyFilter.value;
    const searchCaseNumber = caseNumberSearch.value;
    
    const caseCards = document.querySelectorAll('.case-card');
    
    caseCards.forEach(card => {
        const cardSpecialty = card.getAttribute('data-specialty');
        const cardCaseNumber = card.getAttribute('data-case');
        
        const matchesSpecialty = !selectedSpecialty || cardSpecialty === selectedSpecialty;
        const matchesCaseNumber = !searchCaseNumber || cardCaseNumber === searchCaseNumber;
        
        if (matchesSpecialty && matchesCaseNumber) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

// Update timer display
function updateTimer() {
    const minutes = Math.floor(remainingTime / 60);
    const seconds = remainingTime % 60;
    timer.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    
    if (remainingTime <= 0) {
        clearInterval(timerInterval);
        endConsultation();
    }
}

// Start the timer
function startTimer(minutes = 10) {
    remainingTime = minutes * 60; // Convert minutes to seconds
    updateTimer();
    
    clearInterval(timerInterval); // Clear any existing interval
    timerInterval = setInterval(() => {
        remainingTime--;
        updateTimer();
    }, 1000);
}

// End the consultation
async function endConsultation() {
    clearInterval(timerInterval);
    
    try {
        const response = await fetch('/end_chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to end chat');
        }

        // Hide chat container and show evaluation screen
        chatContainer.classList.add('hidden');
        evaluationContainer.classList.remove('hidden');
        
        // Fetch and display evaluation results with recommendations
        if (data.evaluation) {
            displayEvaluation(data.evaluation, data.recommendations || []);
        }
        
        // Store PDF URL for later download
        if (data.pdf_url) {
            downloadEvaluationBtn.setAttribute('data-pdf-url', data.pdf_url);
        }
        
    } catch (error) {
        console.error('Error:', error);
        alert(`Une erreur est survenue: ${error.message}`);
    }
}

// Display evaluation results
function displayEvaluation(evaluation, recommendations) {
    let totalPoints = evaluation.points_total || 0;
    let earnedPoints = evaluation.points_earned || 0;
    let percentage = evaluation.percentage || 0;
    let resultsHTML = '';
    
    // If points aren't provided via the new format, calculate from checklist
    if (totalPoints === 0 && evaluation.checklist && evaluation.checklist.length > 0) {
        evaluation.checklist.forEach(item => {
            const points = item.points || 1;
            totalPoints += points;
            if (item.completed) {
                earnedPoints += points;
            }
        });
        percentage = totalPoints > 0 ? Math.round((earnedPoints / totalPoints) * 100) : 0;
    }
    
    // Create visual score representation
    const scoreGaugeHTML = createScoreGauge(percentage);
    
    // Add score at the top with gauge
    const scoreHTML = `
    <div class="evaluation-header-section">
        <div class="score-gauge">${scoreGaugeHTML}</div>
        <div class="evaluation-score">
            <div class="score-title">Résultat</div>
            <div class="score-value">${earnedPoints}/${totalPoints}</div>
            <div class="score-percentage">${percentage}%</div>
        </div>
    </div>`;
    
    // Add recommendations section if available
    let recommendationsHTML = '';
    if (recommendations && recommendations.length > 0) {
        recommendationsHTML += '<div class="recommendations-section">';
        recommendationsHTML += '<h3>Conseils personnalisés</h3>';
        recommendationsHTML += '<ul class="recommendations-list">';
        
        recommendations.forEach(rec => {
            recommendationsHTML += `<li class="recommendation-item">${rec}</li>`;
        });
        
        recommendationsHTML += '</ul></div>';
    }
    
    // Add feedback section if available
    let feedbackHTML = '';
    if (evaluation.feedback) {
        feedbackHTML += '<div class="feedback-section">';
        feedbackHTML += '<h3>Retour général</h3>';
        feedbackHTML += `<div class="feedback-content">${evaluation.feedback}</div>`;
        feedbackHTML += '</div>';
    }
    
    // Generate detailed checklist HTML
    let checklistHTML = '';
    if (evaluation.checklist && evaluation.checklist.length > 0) {
        checklistHTML += '<h3>Grille d\'évaluation détaillée</h3>';
        
        // Group items by category if available
        const categories = {};
        let hasCategories = false;
        
        evaluation.checklist.forEach(item => {
            const category = item.category || 'Non catégorisé';
            if (item.category) hasCategories = true;
            
            if (!categories[category]) {
                categories[category] = [];
            }
            categories[category].push(item);
        });
        
        if (hasCategories) {
            // Display items grouped by category
            checklistHTML += '<div class="categories-grid">';
            
            for (const [category, items] of Object.entries(categories)) {
                checklistHTML += `
                <div class="category-group">
                    <div class="category-header">${category}</div>
                    <div class="category-items">
                `;
                
                items.forEach(item => {
                    const itemClass = item.completed ? 'success' : 'failure';
                    const icon = item.completed ? '✅' : '❌';
                    const points = item.points || 1;
                    const earnedItemPoints = item.completed ? points : 0;
                    
                    checklistHTML += `
                    <div class="evaluation-item ${itemClass}">
                        <div class="item-header">
                            <span class="item-icon">${icon}</span> 
                            <span class="item-description">${item.description}</span>
                            <span class="item-points">${earnedItemPoints}/${points}</span>
                        </div>
                    `;
                    
                    // Add justification if available
                    if (item.justification) {
                        checklistHTML += `<div class="item-justification">${item.justification}</div>`;
                    }
                    
                    checklistHTML += `</div>`;
                });
                
                checklistHTML += `</div></div>`;
            }
            
            checklistHTML += '</div>';
        } else {
            // Display items without categories in a simple list
            checklistHTML += '<div class="checklist">';
            
            evaluation.checklist.forEach(item => {
                const itemClass = item.completed ? 'success' : 'failure';
                const icon = item.completed ? '✅' : '❌';
                const points = item.points || 1;
                const earnedItemPoints = item.completed ? points : 0;
                
                checklistHTML += `
                <div class="evaluation-item ${itemClass}">
                    <div class="item-header">
                        <span class="item-icon">${icon}</span> 
                        <span class="item-description">${item.description}</span>
                        <span class="item-points">${earnedItemPoints}/${points}</span>
                    </div>
                `;
                
                // Add justification if available
                if (item.justification) {
                    checklistHTML += `<div class="item-justification">${item.justification}</div>`;
                }
                
                checklistHTML += `</div>`;
            });
            
            checklistHTML += '</div>';
        }
    }

    if (!directivesViewed) {
        const directivesReminder = document.createElement('div');
        directivesReminder.className = 'feedback-section';
        directivesReminder.innerHTML = `
            <h3>Remarque importante</h3>
            <div class="feedback-content" style="border-left: 5px solid #dc3545;">
                <p><strong>Attention :</strong> Vous n'avez pas consulté les directives pendant cette session.
                Les directives contiennent des consignes importantes pour la consultation.</p>
            </div>
        `;
        evaluationResults.prepend(directivesReminder);
    }
    
    // Combine all sections
    resultsHTML = scoreHTML + recommendationsHTML + feedbackHTML + checklistHTML;
    
    // Display the evaluation
    evaluationResults.innerHTML = resultsHTML;
    
    // Add new CSS classes for improved visual display
    addEvaluationStyles();
}

function addEvaluationStyles() {
    // Only add styles if they don't already exist
    if (!document.getElementById('enhanced-evaluation-styles')) {
        const styleElement = document.createElement('style');
        styleElement.id = 'enhanced-evaluation-styles';
        
        styleElement.textContent = `
            .evaluation-header-section {
                display: flex;
                justify-content: center;
                align-items: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            
            .score-gauge {
                width: 120px;
                margin-right: 20px;
            }
            
            .evaluation-score {
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            
            .score-title {
                font-size: 18px;
                font-weight: bold;
                margin-bottom: 5px;
            }
            
            .score-value {
                font-size: 28px;
                font-weight: bold;
            }
            
            .score-percentage {
                font-size: 22px;
                opacity: 0.8;
            }
            
            .recommendations-section, .feedback-section {
                margin-bottom: 25px;
                padding: 15px;
                border-radius: 8px;
                background-color: #f8f9fa;
                border-left: 5px solid #4285f4;
            }
            
            .recommendations-list {
                padding-left: 20px;
            }
            
            .recommendation-item {
                margin-bottom: 10px;
                line-height: 1.5;
            }
            
            .feedback-content {
                padding: 10px;
                background-color: white;
                border-radius: 5px;
                line-height: 1.6;
            }
            
            .categories-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            
            .category-group {
                border: 1px solid #dee2e6;
                border-radius: 8px;
                overflow: hidden;
            }
            
            .category-header {
                padding: 10px 15px;
                background-color: #e9ecef;
                font-weight: bold;
                border-bottom: 1px solid #dee2e6;
            }
            
            .category-items {
                padding: 10px;
            }
            
            .evaluation-item {
                margin-bottom: 15px;
                padding: 10px;
                border-radius: 5px;
                background-color: white;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            
            .evaluation-item.success {
                border-left: 5px solid #28a745;
            }
            
            .evaluation-item.failure {
                border-left: 5px solid #dc3545;
            }
            
            .item-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 5px;
            }
            
            .item-icon {
                font-size: 16px;
                margin-right: 8px;
            }
            
            .item-description {
                flex: 1;
                font-weight: 500;
            }
            
            .item-points {
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 4px;
                background-color: #f8f9fa;
                font-size: 14px;
            }
            
            .item-justification {
                margin-top: 5px;
                padding: 8px;
                background-color: #f8f9fa;
                border-radius: 4px;
                font-size: 14px;
                font-style: italic;
                color: #6c757d;
            }
        `;
        
        document.head.appendChild(styleElement);
    }
}

// Create visual score gauge
function createScoreGauge(percentage) {
    // Create a visual representation of the score using SVG
    const radius = 50;
    const circumference = 2 * Math.PI * radius;
    const dashOffset = circumference * (1 - percentage / 100);
    
    // Determine color based on score
    let color = '#dc3545'; // Red for low scores
    if (percentage >= 80) {
        color = '#28a745'; // Green for high scores
    } else if (percentage >= 60) {
        color = '#ffc107'; // Yellow for medium scores
    }
    
    return `
    <svg width="120" height="120" viewBox="0 0 120 120">
        <circle 
            cx="60" 
            cy="60" 
            r="${radius}" 
            fill="none" 
            stroke="#e9ecef" 
            stroke-width="10"
        />
        <circle 
            cx="60" 
            cy="60" 
            r="${radius}" 
            fill="none" 
            stroke="${color}" 
            stroke-width="10"
            stroke-dasharray="${circumference}"
            stroke-dashoffset="${dashOffset}"
            transform="rotate(-90 60 60)"
        />
        <text 
            x="60" 
            y="60" 
            text-anchor="middle" 
            dominant-baseline="middle" 
            font-size="24" 
            font-weight="bold" 
            fill="${color}"
        >${percentage}%</text>
    </svg>
    `;
}

// Event Listeners
specialtyFilter.addEventListener('change', filterCases);
caseNumberSearch.addEventListener('input', filterCases);  // Add case number search listener

// Case selection
document.addEventListener('click', (event) => {
    if (event.target.classList.contains('select-case-btn')) {
        const caseCard = event.target.closest('.case-card');
        const caseNumber = caseCard.getAttribute('data-case');
        
        // Deselect previous card if exists
        if (selectedCaseCard) {
            selectedCaseCard.classList.remove('selected');
        }
        
        // Select current card
        caseCard.classList.add('selected');
        selectedCaseCard = caseCard;
        currentCase = caseNumber;
        
        // Enable start button
        startChatButton.disabled = false;
    }
});

// Main enhanced initialize chat function (with directives support)
startChatButton.addEventListener('click', async () => {
    if (!currentCase) return;
    
    try {
        // Initialize the chat with selected case
        const response = await fetch('/initialize_chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ case_number: currentCase })
        });

        if (!response.ok) {
            throw new Error('Failed to initialize chat');
        }

        const data = await response.json();
        
        // Store directives if available
        currentDirectives = data.directives || '';
        
        // Reset directives viewed flag
        directivesViewed = false;
        
        // Show case information in chat header
        if (selectedCaseCard) {
            const specialty = selectedCaseCard.getAttribute('data-specialty');
            currentCaseTitle.textContent = `Cas ${currentCase} (${specialty})`;
        }
        
        // Clear previous chat messages
        chatMessages.innerHTML = '';
        
        // Switch to chat interface
        caseSelection.classList.add('hidden');
        chatContainer.classList.remove('hidden');
        
        // Get consultation time from response or use default (10 minutes)
        const configuredTime = data.consultation_time || 10;
        
        // Start the timer with configured time
        startTimer(configuredTime);
        
        // Add initial system message
        addMessageToChat('system', 'Consultation initiée. Vous pouvez commencer à poser vos questions.');
        
        // Auto-show directives if available (optional feature)
        if (currentDirectives) {
            // Flash the directives button to draw attention
            viewDirectivesBtn.classList.add('flash-attention');
            setTimeout(() => {
                viewDirectivesBtn.classList.remove('flash-attention');
            }, 3000);
            
            // Optionally automatically show directives
            // showDirectives(); // Uncomment to auto-show
        }
        
    } catch (error) {
        console.error('Error:', error);
        alert('Une erreur est survenue lors de l\'initialisation du chat');
    }
});

endChatButton.addEventListener('click', endConsultation);

backToCasesBtn.addEventListener('click', () => {
    evaluationContainer.classList.add('hidden');
    caseSelection.classList.remove('hidden');
    chatMessages.innerHTML = '';
    currentCase = null;
    currentDirectives = null;
    directivesViewed = false;
    selectedCaseCard = null;
});

downloadEvaluationBtn.addEventListener('click', () => {
    const pdfUrl = downloadEvaluationBtn.getAttribute('data-pdf-url');
    if (pdfUrl) {
        window.location.href = pdfUrl;
    } else {
        alert('Le PDF n\'est pas disponible');
    }
});

// Add enter key support
userInput.addEventListener('keypress', (event) => {
    if (event.key === 'Enter') {
        event.preventDefault();
        sendBtn.click();
    }
});

sendBtn.addEventListener('click', async () => {
    const message = userInput.value.trim();
    if (!message) return;

    try {
        // Disable input and show loading state
        userInput.disabled = true;
        sendBtn.disabled = true;
        sendBtn.textContent = 'Envoi...';  // Change button text
        
        // Add user message immediately
        addMessageToChat('user', message);
        userInput.value = '';
        
        // Add loading indicator
        const loadingMsg = document.createElement('div');
        loadingMsg.classList.add('message', 'assistant', 'loading');
        loadingMsg.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
        chatMessages.appendChild(loadingMsg);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // Send message to backend
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message })
        });

        // Remove loading indicator
        const loadingElement = document.querySelector('.loading');
        if (loadingElement) {
            loadingElement.remove();
        }

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        if (data.error) {
            addMessageToChat('system', `Erreur: ${data.error}`);
        } else {
            addMessageToChat('assistant', data.reply);
        }

    } catch (error) {
        console.error('Error:', error);
        addMessageToChat('system', 'Une erreur est survenue lors de l\'envoi du message');
    } finally {
        // Reset button and input state
        userInput.disabled = false;
        sendBtn.disabled = false;
        sendBtn.textContent = 'Envoyer';
        userInput.focus();
    }
});
// Improve image handling in chat messages
function addMessageToChat(role, text) {
    const messageElem = document.createElement('div');
    messageElem.classList.add('message', role);
    
    const roleText = role === 'system' ? 'Système' : 
                     role === 'assistant' ? 'Patient' : 
                     'Médecin';
    
    // Check if the message contains any reference to images
    let processedText = text;
    
    // Handle image paths in the message with improved recognition
    if (text.includes('/static/images/')) {
        // Extract all image URLs using a more robust regex
        const imgRegex = /(\/static\/images\/[^\s"'\n]+)/g;
        const matches = text.match(imgRegex);
        
        if (matches && matches.length > 0) {
            // For each image path found
            matches.forEach(imgUrl => {
                // Clean up URL if needed (remove any trailing punctuation)
                const cleanImgUrl = imgUrl.replace(/[.,;:!?]$/, '');
                
                // Create a properly formatted image element with the cleanImgUrl
                const imgHtml = `<div class="message-image">
                                    <img src="${cleanImgUrl}" alt="Image médicale" 
                                         class="medical-image" onclick="openImageModal(this.src)">
                                 </div>`;
                
                // Replace the URL text with the actual image
                processedText = processedText.replace(imgUrl, imgHtml);
            });
        }
    }
    
    // Update message content with processed text
    messageElem.innerHTML = `
        <strong>${roleText}:</strong> 
        <div class="message-content">${processedText}</div>
    `;
    
    chatMessages.appendChild(messageElem);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add to ensure global access
window.openImageModal = function(src) {
    const modal = document.createElement('div');
    modal.classList.add('image-modal');
    
    // Extract image description from path if available
    let imageDescription = "Image médicale";
    const pathParts = src.split('/');
    if (pathParts.length > 0) {
        const filename = pathParts[pathParts.length - 1];
        // Try to extract descriptive parts from filename
        const nameParts = filename.split('_');
        if (nameParts.length > 2) {
            // Use the last part of the filename as a description
            imageDescription = nameParts[nameParts.length - 1].replace(/\.\w+$/, '');
            imageDescription = imageDescription.charAt(0).toUpperCase() + imageDescription.slice(1);
        }
    }
    
    modal.innerHTML = `
        <div class="modal-content">
            <span class="close-modal">&times;</span>
            <div class="image-container">
                <img src="${src}" alt="${imageDescription}" class="modal-image">
            </div>
            <div class="image-caption">${imageDescription}</div>
            <div class="modal-controls">
                <button class="zoom-in">Zoom +</button>
                <button class="zoom-out">Zoom -</button>
                <button class="reset-zoom">Réinitialiser</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // Get the image element
    const img = modal.querySelector('.modal-image');
    const container = modal.querySelector('.image-container');
    let scale = 1;
    
    // Zoom controls
    modal.querySelector('.zoom-in').addEventListener('click', () => {
        scale *= 1.2;
        img.style.transform = `scale(${scale})`;
    });
    
    modal.querySelector('.zoom-out').addEventListener('click', () => {
        scale /= 1.2;
        if (scale < 0.5) scale = 0.5;
        img.style.transform = `scale(${scale})`;
    });
    
    modal.querySelector('.reset-zoom').addEventListener('click', () => {
        scale = 1;
        img.style.transform = `scale(${scale})`;
        // Reset scroll position
        container.scrollLeft = 0;
        container.scrollTop = 0;
    });
    
    // Add scroll wheel zoom support
    container.addEventListener('wheel', (e) => {
        e.preventDefault();
        if (e.deltaY < 0) {
            // Zoom in
            scale *= 1.1;
        } else {
            // Zoom out
            scale /= 1.1;
            if (scale < 0.5) scale = 0.5;
        }
        img.style.transform = `scale(${scale})`;
    });
    
    // Make image movable when zoomed
    let isDragging = false;
    let lastX, lastY;
    
    container.addEventListener('mousedown', (e) => {
        if (scale > 1) {
            isDragging = true;
            lastX = e.clientX;
            lastY = e.clientY;
            container.style.cursor = 'grabbing';
        }
    });
    
    window.addEventListener('mouseup', () => {
        isDragging = false;
        container.style.cursor = 'auto';
    });
    
    container.addEventListener('mousemove', (e) => {
        if (isDragging && scale > 1) {
            const deltaX = e.clientX - lastX;
            const deltaY = e.clientY - lastY;
            lastX = e.clientX;
            lastY = e.clientY;
            
            container.scrollLeft -= deltaX;
            container.scrollTop -= deltaY;
        }
    });
    
    // Close modal when clicking the X or outside the image
    modal.querySelector('.close-modal').onclick = () => modal.remove();
    modal.onclick = (e) => {
        if (e.target === modal) modal.remove();
    };
};

function checkDirectiveCompliance(message) {
    // If there are no directives or they've already been viewed, no need to check
    if (!currentDirectives || directivesViewed) return;
    
    // Look for phrases that might indicate the student is asking about what to do
    const askingAboutDirectives = /que dois[- ]je faire|instructions|directives|consignes|objectifs|tâches/i.test(message);
    
    // If student is asking about what to do, remind them to check directives
    if (askingAboutDirectives) {
        setTimeout(() => {
            addMessageToChat('system', 'Rappel : Consultez les directives en cliquant sur le bouton "Voir les directives" en haut de l\'écran pour connaître les tâches spécifiques à réaliser durant cette consultation.');
            
            // Flash the directives button again
            viewDirectivesBtn.classList.add('flash-attention');
            setTimeout(() => {
                viewDirectivesBtn.classList.remove('flash-attention');
            }, 3000);
        }, 1000);
    }
}

function openImageModal(src) {
    const modal = document.createElement('div');
    modal.classList.add('image-modal');
    
    // Extract image description from path if available
    let imageDescription = "Image médicale";
    const pathParts = src.split('/');
    if (pathParts.length > 0) {
        const filename = pathParts[pathParts.length - 1];
        // Try to extract descriptive parts from filename
        const nameParts = filename.split('_');
        if (nameParts.length > 2) {
            // Use the last part of the filename as a description
            imageDescription = nameParts[nameParts.length - 1].replace(/\.\w+$/, '');
            imageDescription = imageDescription.charAt(0).toUpperCase() + imageDescription.slice(1);
        }
    }
    
    modal.innerHTML = `
        <div class="modal-content">
            <span class="close-modal">&times;</span>
            <div class="image-container">
                <img src="${src}" alt="${imageDescription}" class="modal-image">
            </div>
            <div class="image-caption">${imageDescription}</div>
            <div class="modal-controls">
                <button class="zoom-in">Zoom +</button>
                <button class="zoom-out">Zoom -</button>
                <button class="reset-zoom">Réinitialiser</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // Get the image element
    const img = modal.querySelector('.modal-image');
    const container = modal.querySelector('.image-container');
    let scale = 1;
    
    // Zoom controls
    modal.querySelector('.zoom-in').addEventListener('click', () => {
        scale *= 1.2;
        img.style.transform = `scale(${scale})`;
    });
    
    modal.querySelector('.zoom-out').addEventListener('click', () => {
        scale /= 1.2;
        if (scale < 0.5) scale = 0.5;
        img.style.transform = `scale(${scale})`;
    });
    
    modal.querySelector('.reset-zoom').addEventListener('click', () => {
        scale = 1;
        img.style.transform = `scale(${scale})`;
        // Reset scroll position
        container.scrollLeft = 0;
        container.scrollTop = 0;
    });
    
    // Add scroll wheel zoom support
    container.addEventListener('wheel', (e) => {
        e.preventDefault();
        if (e.deltaY < 0) {
            // Zoom in
            scale *= 1.1;
        } else {
            // Zoom out
            scale /= 1.1;
            if (scale < 0.5) scale = 0.5;
        }
        img.style.transform = `scale(${scale})`;
    });
    
    // Make image movable when zoomed
    let isDragging = false;
    let lastX, lastY;
    
    container.addEventListener('mousedown', (e) => {
        if (scale > 1) {
            isDragging = true;
            lastX = e.clientX;
            lastY = e.clientY;
            container.style.cursor = 'grabbing';
        }
    });
    
    window.addEventListener('mouseup', () => {
        isDragging = false;
        container.style.cursor = 'auto';
    });
    
    container.addEventListener('mousemove', (e) => {
        if (isDragging && scale > 1) {
            const deltaX = e.clientX - lastX;
            const deltaY = e.clientY - lastY;
            lastX = e.clientX;
            lastY = e.clientY;
            
            container.scrollLeft -= deltaX;
            container.scrollTop -= deltaY;
        }
    });
    
    // Close modal when clicking the X or outside the image
    modal.querySelector('.close-modal').onclick = () => modal.remove();
    modal.onclick = (e) => {
        if (e.target === modal) modal.remove();
    };
}

// Add some CSS for the case number search field
const styleElement = document.createElement('style');
styleElement.textContent = `
    .search-input {
        width: 100%;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 16px;
    }
    
    .filter-section {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
        margin-bottom: 20px;
    }
    
    @media (max-width: 768px) {
        .filter-section {
            grid-template-columns: 1fr;
        }
    }
    
    .case-card.selected {
        border: 2px solid #4CAF50;
        box-shadow: 0 5px 15px rgba(76, 175, 80, 0.2);
    }
    
    /* Directives Button States */
    .view-button.viewed {
        background-color: #4CAF50;
    }
    
    .view-button.viewed:before {
        content: "✓";
    }
    
    /* Flash attention animation */
    @keyframes flash {
        0%, 100% { background-color: #4CAF50; }
        50% { background-color: #FFC107; }
    }
    
    .flash-attention {
        animation: flash 1s ease-in-out 3;
    }
    
    /* Timer pulse animation */
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); background-color: rgba(255, 193, 7, 0.2); }
    }
    
    .pulse-attention {
        animation: pulse 0.8s ease-in-out 3;
    }
    
    /* Highlight for time-related instructions */
    .highlight-time {
        background-color: rgba(255, 193, 7, 0.3);
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: bold;
    }
    
    /* Time reminder in directives */
    .time-reminder {
        margin-top: 15px;
        padding: 10px;
        background-color: rgba(255, 193, 7, 0.2);
        border-left: 3px solid #FFC107;
        border-radius: 3px;
    }
`;
document.head.appendChild(styleElement);


// When initializing chat, get directives
startChatButton.addEventListener('click', async () => {
    if (!currentCase) return;
    
    try {
        // Initialize the chat with selected case
        const response = await fetch('/initialize_chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ case_number: currentCase })
        });

        if (!response.ok) {
            throw new Error('Failed to initialize chat');
        }

        const data = await response.json();
        
        // Store directives if available
        currentDirectives = data.directives || '';
        
        // Show case information in chat header
        if (selectedCaseCard) {
            const specialty = selectedCaseCard.getAttribute('data-specialty');
            currentCaseTitle.textContent = `Cas ${currentCase} (${specialty})`;
        }
        
        // Clear previous chat messages
        chatMessages.innerHTML = '';
        
        // Switch to chat interface
        caseSelection.classList.add('hidden');
        chatContainer.classList.remove('hidden');
        
        // Get consultation time from response or use default (10 minutes)
        const configuredTime = data.consultation_time || 10;
        
        // Start the timer with configured time
        startTimer(configuredTime);
        
        // Add initial system message
        addMessageToChat('system', 'Consultation initiée. Vous pouvez commencer à poser vos questions.');
        
        // Auto-show directives at start if available
        if (currentDirectives) {
            showDirectives();
        }
        
    } catch (error) {
        console.error('Error:', error);
        alert('Une erreur est survenue lors de l\'initialisation du chat');
    }
});

// Show directives modal
function showDirectives() {
    if (!currentDirectives) {
        directivesContent.innerHTML = "<p>Aucune directive disponible pour ce cas.</p>";
    } else {
        directivesContent.innerHTML = formatDirectives(currentDirectives);
        
        // Add a reminder about time if directives mention time constraints
        if (currentDirectives.match(/min|minute|temps|durée|chrono/i)) {
            const timeReminder = document.createElement('div');
            timeReminder.className = 'time-reminder';
            timeReminder.innerHTML = `
                <p><strong>Rappel :</strong> Le temps restant pour cette consultation est affiché en haut à droite.</p>
            `;
            directivesContent.appendChild(timeReminder);
        }
    }
    
    // Mark directives as viewed
    directivesViewed = true;
    
    // Show the modal
    directivesModal.classList.add('visible');
    
    // Update button appearance to indicate it's been viewed
    viewDirectivesBtn.classList.add('viewed');
    
    // Optionally add a visual pulse animation to timer if time-critical directives
    if (currentDirectives && currentDirectives.match(/min|minute|temps|durée|chrono/i)) {
        document.querySelector('.timer-container').classList.add('pulse-attention');
        setTimeout(() => {
            document.querySelector('.timer-container').classList.remove('pulse-attention');
        }, 3000);
    }
}

// Format directives text with line breaks and numbering
function formatDirectives(text) {
    if (!text) return '';
    
    // Preserve line breaks
    let formattedText = text.replace(/\n/g, '<br>');
    
    // Format numbered lists (1., 2., etc)
    formattedText = formattedText.replace(/(\d+)\.\s+([^\n<]+)/g, '<strong>$1.</strong> $2');
    
    // Highlight time-related instructions
    formattedText = formattedText.replace(/(\d+)\s*(min|minute)/g, '<span class="highlight-time">$1 $2</span>');
    
    // Add any other formatting enhancements here
    
    return formattedText;
}

// View directives button
viewDirectivesBtn.addEventListener('click', showDirectives);

// Close directives modal
directivesClose.addEventListener('click', () => {
    directivesModal.classList.remove('visible');
});

// Close modal when clicking outside
window.addEventListener('click', (e) => {
    if (e.target === directivesModal) {
        directivesModal.classList.remove('visible');
    }
});

// Tab navigation
function showTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all nav tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    
    // Add active class to clicked nav tab
    event.target.classList.add('active');
    
    // Load content for specific tabs
    if (tabName === 'stats-tab') {
        loadStudentStats();
    } else if (tabName === 'stations-tab') {
        loadStudentStations();
    }
}

// Load student statistics
async function loadStudentStats() {
    try {
        const response = await fetch('/student/stats');
        if (!response.ok) {
            throw new Error('Failed to load stats');
        }
        
        const stats = await response.json();
        
        // Update stats overview
        document.getElementById('total-workouts').textContent = stats.total_workouts;
        document.getElementById('unique-stations').textContent = stats.unique_stations;
        document.getElementById('average-score').textContent = stats.average_score + '%';
        
        // Update recent performances table
        const tableBody = document.getElementById('performance-table-body');
        tableBody.innerHTML = '';
        
        if (stats.recent_performances.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Aucune performance enregistrée</td></tr>';
        } else {
            stats.recent_performances.forEach(perf => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${perf.case_number}</td>
                    <td>${perf.specialty}</td>
                    <td>${perf.score}%</td>
                    <td><span class="grade-badge grade-${perf.grade}">${perf.grade}</span></td>
                    <td><span class="status-badge status-${perf.status.toLowerCase().replace(' ', '-')}">${perf.status}</span></td>
                    <td>${perf.completed_at}</td>
                    <td>${perf.duration}</td>
                `;
                tableBody.appendChild(row);
            });
        }
        
    } catch (error) {
        console.error('Error loading stats:', error);
        document.getElementById('total-workouts').textContent = 'Erreur';
        document.getElementById('unique-stations').textContent = 'Erreur';
        document.getElementById('average-score').textContent = 'Erreur';
    }
}

// Load student stations
async function loadStudentStations(searchQuery = '') {
    try {
        let url = '/student/stations';
        if (searchQuery) {
            url += `?search=${encodeURIComponent(searchQuery)}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to load stations');
        }
        
        const data = await response.json();
        const stationsGrid = document.getElementById('stations-grid');
        stationsGrid.innerHTML = '';
        
        if (data.stations.length === 0) {
            stationsGrid.innerHTML = '<p>Aucune station trouvée.</p>';
        } else {
            data.stations.forEach(station => {
                const stationCard = document.createElement('div');
                stationCard.className = 'station-card';
                
                const gradeDisplay = station.best_score > 0 ? 
                    `<span class="grade-badge grade-${getGradeFromScore(station.best_score)}">${getGradeFromScore(station.best_score)}</span>` : 
                    '<span class="grade-badge grade-none">Non tenté</span>';
                
                const lastAttemptDisplay = station.last_attempt ? 
                    `Dernière tentative: ${station.last_attempt}` : 
                    'Jamais tenté';
                
                stationCard.innerHTML = `
                    <div class="station-header">
                        <h4>Station ${station.case_number}</h4>
                        ${gradeDisplay}
                    </div>
                    <div class="station-info">
                        <p><strong>Spécialité:</strong> ${station.specialty}</p>
                        <p><strong>Durée:</strong> ${station.consultation_time} minutes</p>
                        <p><strong>Tentatives:</strong> ${station.attempts}</p>
                        <p><strong>Meilleur score:</strong> ${station.best_score}%</p>
                        <p class="last-attempt">${lastAttemptDisplay}</p>
                    </div>
                    <div class="station-actions">
                        <button class="select-station-btn" data-case="${station.case_number}" data-specialty="${station.specialty}">
                            ${station.attempts > 0 ? 'Reprendre' : 'Commencer'}
                        </button>
                    </div>
                `;
                
                stationsGrid.appendChild(stationCard);
            });
            
            // Add event listeners to station selection buttons
            document.querySelectorAll('.select-station-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const caseNumber = e.target.getAttribute('data-case');
                    const specialty = e.target.getAttribute('data-specialty');
                    
                    // Switch to cases tab and select the case
                    showTab('cases-tab');
                    selectCase(caseNumber, specialty);
                });
            });
        }
        
    } catch (error) {
        console.error('Error loading stations:', error);
        document.getElementById('stations-grid').innerHTML = '<p>Erreur lors du chargement des stations.</p>';
    }
}

// Search stations
function searchStations() {
    const searchQuery = document.getElementById('stations-search').value.trim();
    loadStudentStations(searchQuery);
}

// Helper function to get grade from score
function getGradeFromScore(score) {
    if (score >= 90) return 'A';
    if (score >= 80) return 'B';
    if (score >= 70) return 'C';
    if (score >= 60) return 'D';
    return 'F';
}

// FIXED: Tab switching function
function showStudentTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.student-tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all nav tabs
    document.querySelectorAll('.student-nav-tabs .nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    
    // Add active class to clicked nav tab
    document.querySelector(`.student-nav-tabs .nav-tab[onclick*="${tabName}"]`).classList.add('active');
    
    // Load content for specific tabs
    if (tabName === 'practice-tab') {
        loadPracticeData();
    } else if (tabName === 'competition-tab') {
        loadAvailableCompetitions();
    } else if (tabName === 'stats-tab') {
        loadStudentStats();
    }
    
    // Stop competition polling if leaving competition tab
    if (tabName !== 'competition-tab') {
        stopCompetitionPolling();
    }
}

// Competition status polling with proper cleanup
function startCompetitionPolling(sessionId) {
    if (competitionUpdateInterval) {
        clearInterval(competitionUpdateInterval);
    }
    currentCompetitionId = sessionId;
    console.log('Starting competition polling for session:', sessionId);
    updateCompetitionStatus(sessionId); // Initial immediate update
    competitionUpdateInterval = setInterval(() => updateCompetitionStatus(sessionId), 3000); // Poll every 3 seconds
}

// FIXED: Update competition interface with better state management
function updateCompetitionInterface(status) {
    console.log('Updating competition interface with status:', status);
    
    // Update session name and progress
    document.getElementById('competition-session-name').textContent = status.session_name;
    
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    
    if (progressFill && progressText) {
        progressFill.style.width = `${status.progress_percentage}%`;
        progressText.textContent = `${status.completed_stations}/${status.total_stations} stations`;
    }

    // Handle different student states
    switch (status.student_status) {
        case 'logged_in':
            showWaitingState();
            break;
        case 'active':
            if (status.current_station) {
                showStationInterface(status.current_station, status.time_per_station, status.total_stations);
            }
            break;
        case 'between_stations':
            showBetweenStations(status.time_between_stations);
            break;
        case 'completed':
            showFinalResults(status);
            stopCompetitionPolling();
            break;
        default:
            console.log('Unknown student status:', status.student_status);
    }
}

// FIXED: Station interface with proper initialization
function showStationInterface(station, timePerStation, totalStations) {
    console.log('Showing station interface for:', station);
    
    hideAllCompetitionScreens();
    document.getElementById('station-interface').classList.remove('hidden');
    
    // Update station info
    document.getElementById('current-station-number').textContent = station.station_order;
    document.getElementById('total-station-count').textContent = totalStations;
    document.getElementById('station-specialty').textContent = station.specialty;
    
    // Only start timer if not already running
    if (!isTimerRunning) {
        startStationTimer(timePerStation * 60); // Convert to seconds
    }
    
    // Initialize chat if this is a new station
    if (!currentStationData || currentStationData.case_number !== station.case_number) {
        currentStationData = station;
        initializeCompetitionStationChat(station.case_number);
    }
}

// FIXED: Station timer with proper cleanup
function startStationTimer(seconds) {
    // Prevent multiple timers
    if (isTimerRunning) {
        console.log('Timer already running, skipping...');
        return;
    }
    
    if (stationTimer) {
        clearInterval(stationTimer);
    }
    
    isTimerRunning = true;
    let timeLeft = seconds;
    const timerElement = document.getElementById('station-timer');
    
    if (!timerElement) {
        console.error('Timer element not found');
        isTimerRunning = false;
        return;
    }
    
    function updateTimer() {
        const minutes = Math.floor(timeLeft / 60);
        const secs = timeLeft % 60;
        timerElement.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;
        
        // Change color when time is running out
        if (timeLeft <= 60) {
            timerElement.style.background = '#FFCDD2';
            timerElement.style.color = '#D32F2F';
        } else if (timeLeft <= 180) {
            timerElement.style.background = '#FFF3E0';
            timerElement.style.color = '#F57C00';
        } else {
            timerElement.style.background = '#FFEBEE';
            timerElement.style.color = '#C62828';
        }
        
        if (timeLeft <= 0) {
            clearInterval(stationTimer);
            isTimerRunning = false;
            // Auto-end station
            endCurrentStation();
        }
        timeLeft--;
    }
    
    updateTimer();
    stationTimer = setInterval(updateTimer, 1000);
    console.log('Station timer started with', seconds, 'seconds');
}

// FIXED: Initialize competition station chat
async function initializeCompetitionStationChat(caseNumber) {
    try {
        console.log('Initializing station chat for case:', caseNumber);
        
        const response = await fetch(`/student/competition/${currentCompetitionId}/start-station`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const data = await response.json();
            console.log('Station initialized:', data);
            
            // Display directives
            const directivesElement = document.getElementById('station-directives');
            if (data.directives && directivesElement) {
                directivesElement.innerHTML = 
                    `<p><strong>Instructions:</strong> ${data.directives.replace(/\n/g, '<br>')}</p>`;
            }
            
            // Clear chat messages
            const chatMessages = document.getElementById('competition-chat-messages');
            if (chatMessages) {
                chatMessages.innerHTML = '';
            }
            
            // Handle images
            if (data.images && data.images.length > 0) {
                document.getElementById('view-competition-images').style.display = 'inline-block';
                // Store images for viewing
                window.currentStationImages = data.images;
            }
            
        } else {
            throw new Error('Failed to start station');
        }
    } catch (error) {
        console.error('Error initializing station:', error);
        showError('Erreur lors de l\'initialisation de la station');
    }
}


async function sendCompetitionMessage() {
    const input = document.getElementById('competition-chat-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Add user message to chat
    addMessageToCompetitionChat('user', message);
    input.value = '';
    
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            addMessageToCompetitionChat('ai', data.reply);
        } else {
            throw new Error('Failed to send message');
        }
    } catch (error) {
        console.error('Error sending message:', error);
        addMessageToCompetitionChat('system', 'Erreur lors de l\'envoi du message');
    }
}

// FIXED: Add message to competition chat with image display
function addMessageToCompetitionChat(sender, message) {
    const chatMessages = document.getElementById('competition-chat-messages');
    if (!chatMessages) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    
    // Process message for images
    let processedMessage = message;
    
    // Check for image markers in the format [IMAGE:path|description]
    const imageRegex = /\[IMAGE:([^|]+)\|([^\]]+)\]/g;
    processedMessage = processedMessage.replace(imageRegex, (match, path, description) => {
        return `<div class="message-image">
            <img src="${path}" alt="${description}" onclick="showImageModal('${path}', '${description}')" style="max-width: 200px; cursor: pointer; border-radius: 8px; margin: 10px 0;">
            <p style="font-style: italic; margin: 5px 0;">${description}</p>
        </div>`;
    });
    
    // Also check for direct image paths
    if (processedMessage.includes('/static/images/')) {
        document.getElementById('view-competition-images').style.display = 'inline-block';
    }
    
    if (sender === 'user') {
        messageDiv.innerHTML = `<strong>Vous:</strong> ${processedMessage}`;
    } else if (sender === 'ai') {
        messageDiv.innerHTML = `<strong>Patient:</strong> ${processedMessage}`;
    } else {
        messageDiv.innerHTML = processedMessage;
    }
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// FIXED: Show between stations with proper countdown
function showBetweenStations(timeBetween) {
    hideAllCompetitionScreens();
    document.getElementById('between-stations').classList.remove('hidden');
    
    // Start countdown timer
    startCountdownTimer(timeBetween * 60); // Convert to seconds
}

// FIXED: Countdown timer with proper cleanup
function startCountdownTimer(seconds) {
    if (countdownTimer) {
        clearInterval(countdownTimer);
    }
    
    let timeLeft = seconds;
    const countdownElement = document.getElementById('countdown-timer');
    const startButton = document.getElementById('start-next-station');
    
    if (!countdownElement || !startButton) {
        console.error('Countdown elements not found');
        return;
    }
    
    function updateCountdown() {
        countdownElement.textContent = timeLeft;
        
        if (timeLeft <= 0) {
            clearInterval(countdownTimer);
            startButton.disabled = false;
            startButton.textContent = 'Démarrer la prochaine station';
        }
        timeLeft--;
    }
    
    updateCountdown();
    countdownTimer = setInterval(updateCountdown, 1000);
}

// FIXED: Start next station function
async function startNextStation() {
    const button = document.getElementById('start-next-station');
    if (button) {
        button.disabled = true;
        button.textContent = 'Préparation...';
    }
    
    // The polling system will handle the transition
    console.log('Starting next station...');
}

// FIXED: End current station
async function endCurrentStation() {
    // Stop the timer
    if (stationTimer) {
        clearInterval(stationTimer);
        isTimerRunning = false;
    }
    
    try {
        const response = await fetch('/student/competition/complete-station', {
            method: 'POST'
        });
        
        if (response.ok) {
            const result = await response.json();
            
            if (result.success) {
                showStationFeedback(result);
            } else {
                throw new Error('Failed to complete station');
            }
        } else {
            throw new Error('Failed to complete station');
        }
    } catch (error) {
        console.error('Error ending station:', error);
        showError('Erreur lors de la finalisation de la station');
    }
}

// FIXED: Show station feedback
function showStationFeedback(result) {
    hideAllCompetitionScreens();
    document.getElementById('between-stations').classList.remove('hidden');
    
    // Update feedback display
    document.getElementById('completed-station-number').textContent = result.current_station;
    document.getElementById('station-score').textContent = `${result.evaluation.percentage || 0}%`;
    
    // Display detailed feedback
    const feedbackDetails = document.getElementById('feedback-details');
    let feedbackHTML = '<h5>Détails de l\'évaluation:</h5>';
    
    if (result.evaluation.checklist) {
        feedbackHTML += '<ul class="feedback-list">';
        result.evaluation.checklist.forEach(item => {
            const status = item.completed ? '✅' : '❌';
            feedbackHTML += `<li class="${item.completed ? 'completed' : 'not-completed'}">
                ${status} ${item.description} (${item.points} pts)
                ${item.justification ? `<br><small>${item.justification}</small>` : ''}
            </li>`;
        });
        feedbackHTML += '</ul>';
    }
    
    if (result.recommendations && result.recommendations.length > 0) {
        feedbackHTML += '<h6>Recommandations:</h6><ul class="recommendations-list">';
        result.recommendations.forEach(rec => {
            feedbackHTML += `<li>${rec}</li>`;
        });
        feedbackHTML += '</ul>';
    }
    
    feedbackDetails.innerHTML = feedbackHTML;
    
    // If not finished, start countdown
    if (!result.is_finished) {
        startCountdownTimer(result.next_station_delay || 120);
    } else {
        // Show final results after a short delay
        setTimeout(() => {
            showFinalResults(result);
        }, 3000);
    }
}

// FIXED: Stop competition polling with proper cleanup
function stopCompetitionPolling() {
    console.log('Stopping competition polling...');
    
    if (competitionUpdateInterval) {
        clearInterval(competitionUpdateInterval);
        competitionUpdateInterval = null;
    }
    if (stationTimer) {
        clearInterval(stationTimer);
        stationTimer = null;
    }
    if (countdownTimer) {
        clearInterval(countdownTimer);
        countdownTimer = null;
    }
    
    isTimerRunning = false;
    currentStationData = null;
}

// FIXED: View competition images
function viewCompetitionImages() {
    if (window.currentStationImages && window.currentStationImages.length > 0) {
        showImagesModal(window.currentStationImages);
    } else {
        showError('Aucune image disponible pour cette station');
    }
}

// FIXED: Show images modal
function showImagesModal(images) {
    const modal = document.getElementById('images-modal');
    const content = document.getElementById('images-content');
    
    if (!modal || !content) {
        console.error('Images modal elements not found');
        return;
    }
    
    let imagesHTML = '<div class="images-grid">';
    
    images.forEach((image, index) => {
        imagesHTML += `
            <div class="image-item">
                <h4>${image.description || `Image ${index + 1}`}</h4>
                <img src="${image.path}" alt="${image.description || 'Image médicale'}" 
                     onclick="showImageModal('${image.path}', '${image.description || 'Image médicale'}')"
                     style="max-width: 100%; cursor: pointer; border-radius: 8px;">
            </div>
        `;
    });
    
    imagesHTML += '</div>';
    content.innerHTML = imagesHTML;
    modal.classList.remove('hidden');
}

// FIXED: Show single image modal
function showImageModal(imagePath, description) {
    // Create full-screen image modal
    const fullModal = document.createElement('div');
    fullModal.className = 'full-image-modal';
    fullModal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.9);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        cursor: pointer;
    `;
    
    fullModal.innerHTML = `
        <div style="max-width: 90%; max-height: 90%; text-align: center;">
            <img src="${imagePath}" alt="${description}" 
                 style="max-width: 100%; max-height: 80vh; object-fit: contain;">
            <p style="color: white; margin-top: 20px; font-size: 18px;">${description}</p>
            <p style="color: #ccc; margin-top: 10px;">Cliquez pour fermer</p>
        </div>
    `;
    
    fullModal.onclick = () => document.body.removeChild(fullModal);
    document.body.appendChild(fullModal);
}

// FIXED: Close images modal
function closeImagesModal() {
    const modal = document.getElementById('images-modal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// FIXED: Handle competition chat keypress
function handleCompetitionChatKeypress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendCompetitionMessage();
    }
}

// FIXED: Load available competitions
async function loadAvailableCompetitions() {
    try {
        const response = await fetch('/student/available-competitions');
        if (!response.ok) throw new Error('Failed to load competitions');
        
        const data = await response.json();
        displayAvailableCompetitions(data.competitions);
        
    } catch (error) {
        console.error('Error loading competitions:', error);
        document.getElementById('available-competitions-container').innerHTML = 
            '<div class="error-message">Erreur lors du chargement des compétitions</div>';
    }
}

// FIXED: Display available competitions
function displayAvailableCompetitions(competitions) {
    const container = document.getElementById('available-competitions-container');
    
    if (!container) {
        console.error('Competitions container not found');
        return;
    }
    
    if (competitions.length === 0) {
        container.innerHTML = `
            <div class="no-competitions">
                <h3>Aucune compétition disponible</h3>
                <p>Vous n'êtes inscrit(e) à aucune compétition pour le moment.</p>
            </div>
        `;
        return;
    }

    let html = '<div class="competitions-grid">';
    
    competitions.forEach(competition => {
        const canJoin = competition.can_join && competition.student_status === 'registered';
        const canContinue = competition.can_continue && ['logged_in', 'active', 'between_stations'].includes(competition.student_status);
        
        html += `
            <div class="competition-card ${competition.status}">
                <div class="competition-header">
                    <h3>${competition.name}</h3>
                    <span class="competition-status-badge status-${competition.status}">${competition.status_display}</span>
                </div>
                
                <div class="competition-info">
                    <p><strong>Début:</strong> ${competition.start_time}</p>
                    <p><strong>Fin:</strong> ${competition.end_time}</p>
                    <p><strong>Stations:</strong> ${competition.stations_per_session} stations de ${competition.time_per_station} min</p>
                    <p><strong>Participants:</strong> ${competition.logged_in_count}/${competition.participant_count} connectés</p>
                </div>

                <div class="student-progress">
                    <p><strong>Mon statut:</strong> ${getStudentStatusDisplay(competition.student_status)}</p>
                    ${competition.progress > 0 ? `<p><strong>Progrès:</strong> ${competition.progress}%</p>` : ''}
                </div>

                <div class="competition-actions">
                    ${canJoin ? `<button onclick="joinCompetition(${competition.id})" class="submit-button">Rejoindre</button>` : ''}
                    ${canContinue ? `<button onclick="continueCompetition(${competition.id})" class="submit-button">Continuer</button>` : ''}
                    ${competition.status === 'completed' ? `<button onclick="viewCompetitionResults(${competition.id})" class="secondary-button">Voir Résultats</button>` : ''}
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

// FIXED: Join competition
async function joinCompetition(sessionId) {
    try {
        const response = await fetch(`/student/join-competition/${sessionId}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.success) {
            currentCompetitionId = sessionId;
            
            // Hide competitions list and show competition interface
            document.getElementById('available-competitions-container').style.display = 'none';
            document.getElementById('competition-session-interface').classList.remove('hidden');
            
            if (result.waiting_for_others) {
                showWaitingRoom(sessionId);
            } else {
                startCompetitionSession(sessionId);
            }
        } else {
            showError(result.error || 'Erreur lors de la connexion');
        }
        
    } catch (error) {
        console.error('Error joining competition:', error);
        showError('Erreur lors de la connexion à la compétition');
    }
}

// FIXED: Continue competition
async function continueCompetition(sessionId) {
    currentCompetitionId = sessionId;
    
    // Hide competitions list and show competition interface
    document.getElementById('available-competitions-container').style.display = 'none';
    document.getElementById('competition-session-interface').classList.remove('hidden');
    
    await updateCompetitionStatus(sessionId);
}

// FIXED: Show waiting room
function showWaitingRoom(sessionId) {
    hideAllCompetitionScreens();
    document.getElementById('waiting-room').classList.remove('hidden');
    
    // Start polling for status updates
    startCompetitionPolling(sessionId);
}

// FIXED: Start competition session
function startCompetitionSession(sessionId) {
    hideAllCompetitionScreens();
    
    // Start status updates
    startCompetitionPolling(sessionId);
}

// FIXED: Hide all competition screens
function hideAllCompetitionScreens() {
    const screens = ['waiting-room', 'station-interface', 'between-stations', 'final-results'];
    screens.forEach(screenId => {
        const element = document.getElementById(screenId);
        if (element) {
            element.classList.add('hidden');
        }
    });
}

// FIXED: Return to competitions
function returnToCompetitions() {
    stopCompetitionPolling();
    hideAllCompetitionScreens();
    
    // Hide competition interface and show competitions list
    document.getElementById('competition-session-interface').classList.add('hidden');
    document.getElementById('available-competitions-container').style.display = 'block';
    
    currentCompetitionId = null;
    currentStationData = null;
    window.currentStationImages = null;
    
    // Reload competitions
    loadAvailableCompetitions();
}

// FIXED: Update competition status
async function updateCompetitionStatus(sessionId) {
    try {
        const response = await fetch(`/student/competition/${sessionId}/status`);
        if (!response.ok) {
            console.error('Failed to get competition status:', response.status);
            return;
        }
        
        const status = await response.json();
        updateCompetitionInterface(status);
        
    } catch (error) {
        console.error('Error updating competition status:', error);
        // Don't show error to user for polling failures
    }
}
// Helper functions
function getStudentStatusDisplay(status) {
    const statusMap = {
        'registered': 'Inscrit',
        'logged_in': 'Connecté',
        'active': 'En cours',
        'between_stations': 'Entre stations',
        'completed': 'Terminé'
    };
    return statusMap[status] || status;
}

function showError(message) {
    // Create a better error display
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-notification';
    errorDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #f44336;
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        z-index: 9999;
        max-width: 300px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    `;
    errorDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span>${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; color: white; font-size: 18px; cursor: pointer; margin-left: 10px;">&times;</button>
        </div>
    `;
    
    document.body.appendChild(errorDiv);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (errorDiv.parentElement) {
            errorDiv.remove();
        }
    }, 5000);
}

// FIXED: Show final results
function showFinalResults(result) {
    hideAllCompetitionScreens();
    document.getElementById('final-results').classList.remove('hidden');
    
    // Update final scores and ranking
    if (result.final_score !== undefined) {
        document.getElementById('final-average-score').textContent = `${result.final_score}%`;
    }
    
    if (result.rank !== undefined) {
        document.getElementById('final-rank').textContent = result.rank;
        document.getElementById('total-competitors').textContent = result.total_participants || 0;
    }
    
    if (result.total_stations !== undefined) {
        document.getElementById('total-stations-completed').textContent = result.total_stations;
    }
    
    if (result.total_score !== undefined) {
        document.getElementById('total-score-earned').textContent = result.total_score;
    }
    
    // Display leaderboard
    if (result.leaderboard) {
        displayFinalLeaderboard(result.leaderboard);
    }
}

// FIXED: Display final leaderboard
function displayFinalLeaderboard(leaderboard) {
    const container = document.getElementById('final-leaderboard');
    
    if (!container) return;
    
    let html = '<table class="leaderboard-table"><thead><tr>';
    html += '<th>Rang</th><th>Étudiant</th><th>Score Moyen</th></tr></thead><tbody>';
    
    leaderboard.forEach(entry => {
        html += `<tr>
            <td>${entry.rank}</td>
            <td>${entry.student_name}</td>
            <td>${entry.average_score}%</td>
        </tr>`;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

// Practice functions (preserved)
function loadPracticeData() {
    console.log('Loading practice data...');
}

function filterPracticeCases() {
    const caseNumber = document.getElementById('case-number-search')?.value || '';
    const specialty = document.getElementById('specialty-filter')?.value || '';
    
    const cases = document.querySelectorAll('.practice-case-card');
    cases.forEach(caseCard => {
        const cardCaseNumber = caseCard.dataset.case;
        const cardSpecialty = caseCard.dataset.specialty;
        
        const matchesNumber = !caseNumber || cardCaseNumber.includes(caseNumber);
        const matchesSpecialty = !specialty || cardSpecialty === specialty;
        
        if (matchesNumber && matchesSpecialty) {
            caseCard.style.display = 'block';
        } else {
            caseCard.style.display = 'none';
        }
    });
}

function selectPracticeCase(caseNumber) {
    startPracticeConsultation(caseNumber);
}

async function startPracticeConsultation(caseNumber) {
    // Implementation for practice mode
    console.log('Starting practice consultation for case:', caseNumber);
}

// Load student stats
async function loadStudentStats() {
    try {
        const response = await fetch('/student/stats');
        if (response.ok) {
            const data = await response.json();
            
            // Update overview stats
            const totalWorkouts = document.getElementById('total-workouts');
            const uniqueStations = document.getElementById('unique-stations-played');
            const avgScore = document.getElementById('overall-average-score');
            
            if (totalWorkouts) totalWorkouts.textContent = data.total_workouts;
            if (uniqueStations) uniqueStations.textContent = data.unique_stations;
            if (avgScore) avgScore.textContent = data.average_score + '%';
            
            // Update performance table
            const tableBody = document.getElementById('student-performance-table-body');
            if (tableBody) {
                tableBody.innerHTML = '';
                
                if (data.recent_performances && data.recent_performances.length > 0) {
                    data.recent_performances.forEach(perf => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${perf.completed_at}</td>
                            <td>${perf.case_number}</td>
                            <td>${perf.specialty}</td>
                            <td><span class="score-badge score-${getScoreClass(perf.score)}">${perf.score}%</span></td>
                            <td><span class="grade-badge grade-${perf.grade}">${perf.grade}</span></td>
                            <td><span class="status-badge status-${perf.status.toLowerCase().replace(' ', '-')}">${perf.status}</span></td>
                            <td>${perf.duration}</td>
                        `;
                        tableBody.appendChild(row);
                    });
                } else {
                    tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Aucune performance enregistrée</td></tr>';
                }
            }
            
            // Update practice stats
            const attemptsCount = document.getElementById('my-attempts-count');
            const bestScore = document.getElementById('my-best-score');
            
            if (attemptsCount) attemptsCount.textContent = data.total_workouts;
            if (bestScore) bestScore.textContent = data.average_score + '%';
        }
    } catch (error) {
        console.error('Error loading student stats:', error);
    }
}

function getScoreClass(score) {
    if (score >= 90) return 'excellent';
    if (score >= 80) return 'good';
    if (score >= 70) return 'average';
    if (score >= 60) return 'below-average';
    return 'poor';
}

// View competition results
async function viewCompetitionResults(sessionId) {
    try {
        const response = await fetch(`/student/competition/${sessionId}/leaderboard`);
        if (response.ok) {
            const data = await response.json();
            console.log('Competition results:', data);
            // Display results in a modal or redirect to results page
        }
    } catch (error) {
        console.error('Error loading competition results:', error);
    }
}

function downloadCompetitionReport() {
    console.log('Download competition report - to be implemented');
}
    
// Function to select a case programmatically
function selectCase(caseNumber, specialty) {
    // Find the case card and select it
    const caseCards = document.querySelectorAll('.case-card');
    caseCards.forEach(card => {
        if (card.getAttribute('data-case') === caseNumber) {
            // Deselect previous card if exists
            if (selectedCaseCard) {
                selectedCaseCard.classList.remove('selected');
            }
            
            // Select current card
            card.classList.add('selected');
            selectedCaseCard = card;
            currentCase = caseNumber;
            
            // Enable start button
            const startButton = document.getElementById('start-chat');
            if (startButton) {
                startButton.disabled = false;
            }
            
            // Scroll to the case
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    });
}

// Add search functionality for stations
document.addEventListener('DOMContentLoaded', function() {
    // Add enter key support for stations search
    const stationsSearch = document.getElementById('stations-search');
    if (stationsSearch) {
        stationsSearch.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                searchStations();
            }
        });
    }
    
    // Load stats when page loads
    if (document.getElementById('stats-tab').classList.contains('active')) {
        loadStudentStats();
    }
    
    // Update your existing end_chat function to refresh stats after consultation
    const originalEndConsultation = endConsultation;
    endConsultation = async function() {
        await originalEndConsultation();
        // Refresh stats if stats tab is visible
        if (document.getElementById('stats-tab').classList.contains('active')) {
            setTimeout(loadStudentStats, 1000);
        }
    };
});

document.addEventListener('DOMContentLoaded', function() {
    loadStudentStats();
    loadAvailableCompetitions();
    
    // Set up filter event listeners
    const caseNumberSearch = document.getElementById('case-number-search');
    const specialtyFilter = document.getElementById('specialty-filter');
    
    if (caseNumberSearch) {
        caseNumberSearch.addEventListener('input', filterPracticeCases);
    }
    if (specialtyFilter) {
        specialtyFilter.addEventListener('change', filterPracticeCases);
    }
});

// Add CSS styles for the new elements
const newStyles = `
/* Navigation Tabs */
.student-nav-tabs {
    display: flex;
    margin-bottom: 20px;
    border-bottom: 2px solid #e0e0e0;
    background: white;
    border-radius: 8px 8px 0 0;
    overflow: hidden;
}

.nav-tab {
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

.nav-tab.active {
    background: white;
    color: #2196F3;
    border-bottom-color: #2196F3;
}

.nav-tab:hover {
    background: #e8f4fd;
    color: #1976D2;
}

/* Tab Content */
.tab-content {
    display: none;
}

.tab-content.active {
    display: block;
}

.teacher-tab-content {
    display: none;
}

.teacher-tab-content.active {
    display: block;
}

/* Stats Overview */
.stats-overview {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

.stat-card {
    background: white;
    padding: 20px;
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    text-align: center;
    border-left: 4px solid #2196F3;
}

.stat-number {
    font-size: 2.5em;
    font-weight: bold;
    color: #2196F3;
    margin-bottom: 10px;
}

.stat-label {
    font-size: 1.1em;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Performance Table */
.performance-table-container {
    background: white;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.performance-table {
    width: 100%;
    border-collapse: collapse;
}

.performance-table th {
    background: #2196F3;
    color: white;
    padding: 15px;
    text-align: left;
    font-weight: bold;
}

.performance-table td {
    padding: 12px 15px;
    border-bottom: 1px solid #eee;
}

.performance-table tr:hover {
    background: #f8f9fa;
}

/* Stations Grid */
.stations-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 20px;
    margin-top: 20px;
}

.station-card {
    background: white;
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    transition: transform 0.2s, box-shadow 0.2s;
}

.station-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 5px 20px rgba(0,0,0,0.15);
}

.station-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
    padding-bottom: 10px;
    border-bottom: 1px solid #eee;
}

.station-header h4 {
    margin: 0;
    color: #333;
}

.station-info p {
    margin: 8px 0;
    color: #666;
}

.station-info .last-attempt {
    font-style: italic;
    color: #999;
    font-size: 0.9em;
}

.station-actions {
    margin-top: 15px;
    text-align: center;
}

.select-station-btn {
    background: #4CAF50;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 5px;
    cursor: pointer;
    font-size: 14px;
    font-weight: bold;
    transition: background 0.3s;
}

.select-station-btn:hover {
    background: #45a049;
}

/* Grade and Status Badges */
.grade-badge {
    padding: 4px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: bold;
    text-transform: uppercase;
}

.grade-A { background: #4CAF50; color: white; }
.grade-B { background: #8BC34A; color: white; }
.grade-C { background: #FFC107; color: black; }
.grade-D { background: #FF9800; color: white; }
.grade-F { background: #F44336; color: white; }
.grade-none { background: #9E9E9E; color: white; }

.status-badge {
    padding: 4px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: bold;
}

.status-excellent { background: #E8F5E8; color: #2E7D32; }
.status-bon { background: #E3F2FD; color: #1565C0; }
.status-satisfaisant { background: #FFF3E0; color: #EF6C00; }
.status-à-améliorer { background: #FFEBEE; color: #C62828; }

/* Search Container */
.search-container {
    display: flex;
    gap: 10px;
    align-items: center;
}

.search-btn {
    background: #2196F3;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
}

.search-btn:hover {
    background: #1976D2;
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    padding-bottom: 15px;
    border-bottom: 1px solid #eee;
}

.section-header h2 {
    margin: 0;
    color: #333;
}
`;

// Add the styles to the document
const styleSheet = document.createElement('style');
styleSheet.textContent = newStyles;
document.head.appendChild(styleSheet);