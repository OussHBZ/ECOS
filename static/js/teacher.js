// Global variables
const uploadForm = document.getElementById('upload-form');
const uploadStatus = document.getElementById('upload-status');
const processingMessage = document.getElementById('processing-message');
const extractionResults = document.getElementById('extraction-results');
const fileTabBtn = document.getElementById('file-tab-btn');
const manualTabBtn = document.getElementById('manual-tab-btn');
const fileUploadSection = document.getElementById('file-upload-section');
const manualEntrySection = document.getElementById('manual-entry-section');
const manualEntryForm = document.getElementById('manual-entry-form');
const addSymptomBtn = document.getElementById('add-symptom');
const addChecklistItemBtn = document.getElementById('add-checklist-item');
const manualImageFile = document.getElementById('manual-image-file');
const imagesPreview = document.getElementById('manual-images-preview');
const addCustomSectionBtn = document.getElementById('add-custom-section');
const customSectionsContainer = document.getElementById('custom-sections-container');
const caseDetailsModal = document.getElementById('case-details-modal');
const caseDetailsContent = document.getElementById('case-details-content');
const closeModal = document.querySelector('.close-modal');
const editCaseModal = document.getElementById('edit-case-modal');
const editCaseForm = document.getElementById('edit-case-form');
const editCaseNumberTitle = document.getElementById('edit-case-number-title');
const editCancelBtn = document.getElementById('edit-cancel-btn');
let currentEditingCaseNumber = null;

// Variables for tracking data
let extractedData = null;
let uploadedImages = [];

// Main initialization when DOM is ready
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Teacher interface initializing...');
    
    // First, check session status
    const isAuthenticated = await initializeSessionCheck('teacher');
    if (!isAuthenticated) {
        return; // Stop initialization if not authenticated
    }
    
    // Start session monitoring
    startSessionMonitoring();
    
    console.log('Teacher interface authenticated and initialized');
    
    // Initialize UI components
    setupTabSwitching();
    setupFormHandlers();
    setupImageHandlers();
    setupModalHandlers();
    
    // Initialize validation for extraction preview forms
    setupValidation();
    
    // Set up case number validation for both forms
    const fileUploadCaseNumber = document.getElementById('case-number');
    const manualEntryCaseNumber = document.getElementById('manual-case-number');
    
    if (fileUploadCaseNumber) {
        setupCaseNumberValidation(fileUploadCaseNumber, false);
    }
    
    if (manualEntryCaseNumber) {
        setupCaseNumberValidation(manualEntryCaseNumber, false);
    }
    
    // IMPORTANT: Set manual entry as default active tab
    // This ensures the correct form is visible on page load
    if (manualTabBtn && fileTabBtn) {
        // Ensure manual tab is active and file tab is not
        manualTabBtn.classList.add('active');
        fileTabBtn.classList.remove('active');
        
        // Show manual entry section and hide file upload section
        if (manualEntrySection) {
            manualEntrySection.classList.remove('hidden');
        }
        if (fileUploadSection) {
            fileUploadSection.classList.add('hidden');
        }
    }
    
    console.log('Teacher interface ready with Numéro d\'Apogée support');
});

// Set up tab switching between file upload and manual entry
function setupTabSwitching() {
    if (fileTabBtn && manualTabBtn) {
        fileTabBtn.addEventListener('click', () => {
            fileTabBtn.classList.add('active');
            manualTabBtn.classList.remove('active');
            fileUploadSection.classList.remove('hidden');
            manualEntrySection.classList.add('hidden');
        });
        
        manualTabBtn.addEventListener('click', () => {
            manualTabBtn.classList.add('active');
            fileTabBtn.classList.remove('active');
            manualEntrySection.classList.remove('hidden');
            fileUploadSection.classList.add('hidden');
        });
    }
}

// Set up form handlers for adding/removing items
function setupFormHandlers() {
    // Add symptom entry
    if (addSymptomBtn) {
        addSymptomBtn.addEventListener('click', () => {
            const symptomsContainer = document.getElementById('symptoms-container');
            const newSymptomEntry = document.createElement('div');
            newSymptomEntry.classList.add('symptom-entry');
            
            newSymptomEntry.innerHTML = `
                <button type="button" class="remove-btn">&times;</button>
                <div class="form-group">
                    <label>Symptôme :</label>
                    <input type="text" name="symptoms[]">
                </div>
                <div class="form-group">
                    <label>Depuis quand :</label>
                    <input type="text" name="symptom_duration[]">
                </div>
                <div class="form-group">
                    <label>Intensité/Description :</label>
                    <textarea name="symptom_description[]" rows="2"></textarea>
                </div>
            `;
            
            symptomsContainer.appendChild(newSymptomEntry);
            
            // Add event listener to the new remove button
            const removeBtn = newSymptomEntry.querySelector('.remove-btn');
            removeBtn.addEventListener('click', () => {
                symptomsContainer.removeChild(newSymptomEntry);
            });
        });
    }
    
    // Add checklist item
    if (addChecklistItemBtn) {
        addChecklistItemBtn.addEventListener('click', () => {
            const checklistContainer = document.getElementById('checklist-container');
            const newChecklistItem = document.createElement('div');
            newChecklistItem.classList.add('checklist-item');
            
            newChecklistItem.innerHTML = `
                <button type="button" class="remove-btn">&times;</button>
                <div class="form-group">
                    <label>Description :</label>
                    <input type="text" name="checklist_descriptions[]" placeholder="Ex: Questionne sur la durée des symptômes">
                </div>
                <div class="form-group points-group">
                    <label>Points :</label>
                    <input type="number" name="checklist_points[]" value="1">
                </div>
                <div class="form-group">
                    <label>Catégorie :</label>
                    <select name="checklist_categories[]">
                        <option value="Anamnèse">Anamnèse</option>
                        <option value="Examen physique">Examen physique</option>
                        <option value="Communication">Communication</option>
                        <option value="Diagnostic">Diagnostic</option>
                        <option value="Prise en charge">Prise en charge</option>
                    </select>
                </div>
            `;
            
            checklistContainer.appendChild(newChecklistItem);
            
            // Add event listener to the new remove button
            const removeBtn = newChecklistItem.querySelector('.remove-btn');
            removeBtn.addEventListener('click', () => {
                checklistContainer.removeChild(newChecklistItem);
            });
        });
    }
    
    // Add custom section
    if (addCustomSectionBtn) {
        addCustomSectionBtn.addEventListener('click', () => {
            const sectionId = Date.now(); // Use timestamp as unique identifier
            const newSection = document.createElement('div');
            newSection.classList.add('custom-section');
            newSection.dataset.sectionId = sectionId;
            
            newSection.innerHTML = `
                <div class="custom-section-header">
                    <button type="button" class="remove-btn custom-section-remove">&times;</button>
                    <div class="form-group">
                        <label>Titre de la section :</label>
                        <input type="text" name="custom_section_titles[]" placeholder="Ex: Examen neurologique">
                    </div>
                </div>
                <div class="form-group">
                    <label>Contenu :</label>
                    <textarea name="custom_section_contents[]" rows="4" placeholder="Entrez les informations pour cette section"></textarea>
                </div>
            `;
            
            customSectionsContainer.appendChild(newSection);
            
            // Add event listener to the new remove button
            const removeBtn = newSection.querySelector('.custom-section-remove');
            removeBtn.addEventListener('click', () => {
                customSectionsContainer.removeChild(newSection);
            });
        });
    }
    
    // Set up form submission handlers
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleUploadFormSubmit);
    }
    
    if (manualEntryForm) {
        manualEntryForm.addEventListener('submit', handleManualFormSubmit);
        
        // Clear uploaded images when form is reset
        manualEntryForm.addEventListener('reset', () => {
            uploadedImages = [];
            updateImagesPreview();
        });
    }
}

// Set up image handling
function setupImageHandlers() {
    if (manualImageFile) {
        manualImageFile.addEventListener('change', (event) => {
            if (event.target.files && event.target.files.length > 0) {
                // Process the new uploaded files
                Array.from(event.target.files).forEach((file) => {
                    // Create a unique identifier for this file
                    const fileId = Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                    
                    // Add to our tracked images
                    uploadedImages.push({
                        id: fileId,
                        file: file,
                        description: ''
                    });
                });
                
                // Refresh the preview display
                updateImagesPreview();
                
                // Clear the input so the same file can be selected again
                event.target.value = '';
            }
        });
    }
    
    const fileUploadImages = document.getElementById('image-files');
    if (fileUploadImages) {
        fileUploadImages.addEventListener('change', (event) => {
            const fileImagesPreview = document.getElementById('file-images-preview');
            fileImagesPreview.innerHTML = '';
            
            if (event.target.files && event.target.files.length > 0) {
                // Display counter for multiple files
                const fileCount = event.target.files.length;
                const fileCountIndicator = document.createElement('div');
                fileCountIndicator.className = 'file-count-indicator';
                fileCountIndicator.textContent = `${fileCount} image${fileCount > 1 ? 's' : ''} sélectionnée${fileCount > 1 ? 's' : ''}`;
                fileImagesPreview.appendChild(fileCountIndicator);
                
                // Create a grid container
                const previewGrid = document.createElement('div');
                previewGrid.className = 'images-preview-grid';
                fileImagesPreview.appendChild(previewGrid);
                
                // Process each file for preview
                Array.from(event.target.files).forEach((file, index) => {
                    const reader = new FileReader();
                    
                    reader.onload = (e) => {
                        const previewItem = document.createElement('div');
                        previewItem.classList.add('image-preview-item');
                        previewItem.innerHTML = `
                            <div class="image-number">#${index + 1}</div>
                            <img src="${e.target.result}" alt="Preview ${index + 1}" onclick="previewImageLarge(this.src)">
                            <div class="image-file-name">${file.name}</div>
                        `;
                        previewGrid.appendChild(previewItem);
                    };
                    
                    reader.readAsDataURL(file);
                });
            }
        });
    }
}

// Set up modal handlers
function setupModalHandlers() {
    // Close modal functionality (existing code)
    if (closeModal && caseDetailsModal) {
        closeModal.addEventListener('click', () => {
            caseDetailsModal.classList.remove('visible');
            caseDetailsModal.classList.add('hidden');
        });
        
        // Close when clicking outside of content
        window.addEventListener('click', (e) => {
            if (e.target === caseDetailsModal) {
                caseDetailsModal.classList.remove('visible');
                caseDetailsModal.classList.add('hidden');
            }
            // Add edit modal close functionality
            if (e.target === editCaseModal) {
                closeEditModal();
            }
        });
    }
    
    // NEW: Edit modal handlers
    if (editCaseModal) {
        // Close edit modal with X button
        const editCloseBtn = editCaseModal.querySelector('.edit-close');
        if (editCloseBtn) {
            editCloseBtn.addEventListener('click', closeEditModal);
        }
        
        // Cancel button
        if (editCancelBtn) {
            editCancelBtn.addEventListener('click', closeEditModal);
        }
        
        // Edit form submission
        if (editCaseForm) {
            editCaseForm.addEventListener('submit', handleEditFormSubmit);
        }
    }
}

// Function to populate edit form with case data
function populateEditForm(caseData) {
    // Basic information
    document.getElementById('edit-specialty').value = caseData.specialty || '';
    document.getElementById('edit-consultation-time-edit').value = caseData.consultation_time || 10;
    
    // Patient information
    const patientInfo = caseData.patient_info || {};
    document.getElementById('edit-patient-name').value = patientInfo.name || '';
    document.getElementById('edit-patient-age').value = patientInfo.age || '';
    document.getElementById('edit-patient-gender').value = patientInfo.gender || '';
    document.getElementById('edit-patient-occupation').value = patientInfo.occupation || '';
    
    // Medical history
    populateEditMedicalHistory(patientInfo.medical_history || []);
    
    // Symptoms
    populateEditSymptoms(caseData.symptoms || []);
    
    // Evaluation checklist
    populateEditChecklist(caseData.evaluation_checklist || []);
    
    // Additional information
    document.getElementById('edit-diagnosis').value = caseData.diagnosis || '';
    document.getElementById('edit-differential-diagnosis').value = 
        Array.isArray(caseData.differential_diagnosis) ? 
        caseData.differential_diagnosis.join(', ') : 
        (caseData.differential_diagnosis || '');
    document.getElementById('edit-directives').value = caseData.directives || '';
    document.getElementById('edit-additional-notes').value = caseData.additional_notes || '';
    
    // Custom sections
    populateEditCustomSections(caseData.custom_sections || []);
    
    // Images (display only)
    populateEditImages(caseData.images || []);
    setupEditModalEventHandlers();
}

function setupEditModalEventHandlers() {
    // Remove any existing event listeners to prevent duplicates
    const existingHandlers = document.querySelectorAll('[data-edit-handler]');
    existingHandlers.forEach(element => {
        element.removeAttribute('data-edit-handler');
    });

    // Add Medical History button
    const addMedicalHistoryBtn = document.getElementById('edit-add-medical-history');
    if (addMedicalHistoryBtn && !addMedicalHistoryBtn.hasAttribute('data-edit-handler')) {
        addMedicalHistoryBtn.setAttribute('data-edit-handler', 'true');
        addMedicalHistoryBtn.addEventListener('click', function() {
            addEditMedicalHistoryItem('');
        });
    }

    // Add Symptom button
    const addSymptomBtn = document.getElementById('edit-add-symptom');
    if (addSymptomBtn && !addSymptomBtn.hasAttribute('data-edit-handler')) {
        addSymptomBtn.setAttribute('data-edit-handler', 'true');
        addSymptomBtn.addEventListener('click', function() {
            addEditSymptomItem('');
        });
    }

    // Add Checklist Item button
    const addChecklistBtn = document.getElementById('edit-add-checklist-item');
    if (addChecklistBtn && !addChecklistBtn.hasAttribute('data-edit-handler')) {
        addChecklistBtn.setAttribute('data-edit-handler', 'true');
        addChecklistBtn.addEventListener('click', function() {
            addEditChecklistItem('', 1, 'Général');
        });
    }

    // Add Custom Section button
    const addCustomSectionBtn = document.getElementById('edit-add-custom-section');
    if (addCustomSectionBtn && !addCustomSectionBtn.hasAttribute('data-edit-handler')) {
        addCustomSectionBtn.setAttribute('data-edit-handler', 'true');
        addCustomSectionBtn.addEventListener('click', function() {
            addEditCustomSection('', '');
        });
    }

    console.log('Edit modal event handlers set up successfully');
}

// Populate medical history section
function populateEditMedicalHistory(medicalHistory) {
    const container = document.getElementById('edit-medical-history-container');
    container.innerHTML = '';
    
    if (medicalHistory.length === 0) {
        addEditMedicalHistoryItem('');
    } else {
        medicalHistory.forEach(history => {
            addEditMedicalHistoryItem(history);
        });
    }
}

// Function to open edit modal and populate with case data
async function openEditModal(caseNumber) {
    if (!caseNumber || caseNumber === 'None' || caseNumber === 'null') {
        alert("Erreur: Numéro de cas invalide");
        return;
    }
    
    currentEditingCaseNumber = caseNumber;
    editCaseNumberTitle.textContent = caseNumber;
    
    try {
        // Fetch case data - UPDATED URL
        const response = await authenticatedFetch(`/get_case/${caseNumber}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const caseData = await response.json();
        
        // Populate the edit form with case data
        populateEditForm(caseData);
        
        // Set up event handlers for the edit modal buttons
        setupEditModalEventHandlers();
        
        // Show the modal
        editCaseModal.classList.remove('hidden');
        editCaseModal.classList.add('visible');
        
    } catch (error) {
        console.error('Error:', error);
        alert(`Erreur lors de la récupération des données du cas: ${error.message}`);
    }
}
// Add medical history item to edit form
function addEditMedicalHistoryItem(value = '') {
    const container = document.getElementById('edit-medical-history-container');
    
    const historyDiv = document.createElement('div');
    historyDiv.className = 'edit-medical-history';
    historyDiv.innerHTML = `
        <input type="text" class="medical-history-input" value="${value}" placeholder="Entrez l'antécédent médical">
        <button type="button" class="remove-medical-history">×</button>
    `;
    
    container.appendChild(historyDiv);
    
    // Add remove functionality
    historyDiv.querySelector('.remove-medical-history').addEventListener('click', function() {
        historyDiv.remove();
    });
}

// NEW: Populate symptoms section
function populateEditSymptoms(symptoms) {
    const container = document.getElementById('edit-symptoms-container');
    container.innerHTML = '';
    
    if (symptoms.length === 0) {
        addEditSymptomItem('');
    } else {
        symptoms.forEach(symptom => {
            addEditSymptomItem(symptom);
        });
    }
}

// NEW: Add symptom item to edit form
function addEditSymptomItem(value = '') {
    const container = document.getElementById('edit-symptoms-container');
    
    const symptomDiv = document.createElement('div');
    symptomDiv.className = 'edit-symptom';
    symptomDiv.innerHTML = `
        <input type="text" class="symptom-input" value="${value}" placeholder="Décrivez le symptôme">
        <button type="button" class="remove-symptom">×</button>
    `;
    
    container.appendChild(symptomDiv);
    
    // Add remove functionality
    symptomDiv.querySelector('.remove-symptom').addEventListener('click', function() {
        symptomDiv.remove();
    });
}

// NEW: Populate checklist section
function populateEditChecklist(checklist) {
    const container = document.getElementById('edit-checklist-container');
    container.innerHTML = '';
    
    if (checklist.length === 0) {
        addEditChecklistItem();
    } else {
        checklist.forEach(item => {
            addEditChecklistItem(item.description || '', item.points || 1, item.category || '');
        });
    }
}

// NEW: Add checklist item to edit form
function addEditChecklistItem(description = '', points = 1, category = '') {
    const container = document.getElementById('edit-checklist-container');
    
    const itemDiv = document.createElement('div');
    itemDiv.className = 'checklist-item';
    itemDiv.innerHTML = `
        <div class="form-group">
            <label>Description :</label>
            <input type="text" name="checklist_descriptions[]" value="${description}" placeholder="Ex: Questionne sur la durée des symptômes">
        </div>
        <div class="form-group points-group">
            <label>Points :</label>
            <input type="number" name="checklist_points[]" value="${points}" min="1">
        </div>
        <div class="form-group">
            <label>Catégorie :</label>
            <select name="checklist_categories[]">
                <option value="Anamnèse" ${category === 'Anamnèse' ? 'selected' : ''}>Anamnèse</option>
                <option value="Examen physique" ${category === 'Examen physique' ? 'selected' : ''}>Examen physique</option>
                <option value="Communication" ${category === 'Communication' ? 'selected' : ''}>Communication</option>
                <option value="Diagnostic" ${category === 'Diagnostic' ? 'selected' : ''}>Diagnostic</option>
                <option value="Prise en charge" ${category === 'Prise en charge' ? 'selected' : ''}>Prise en charge</option>
                <option value="Général" ${category === 'Général' || category === '' ? 'selected' : ''}>Général</option>
            </select>
        </div>
        <button type="button" class="remove-btn">×</button>
    `;
    
    container.appendChild(itemDiv);
    
    // Add remove functionality
    itemDiv.querySelector('.remove-btn').addEventListener('click', function() {
        itemDiv.remove();
    });
}


// NEW: Populate custom sections
function populateEditCustomSections(customSections) {
    const container = document.getElementById('edit-custom-sections-container');
    container.innerHTML = '';
    
    customSections.forEach(section => {
        addEditCustomSection(section.title || '', section.content || '');
    });
}

// NEW: Add custom section to edit form
function addEditCustomSection(title = '', content = '') {
    const container = document.getElementById('edit-custom-sections-container');
    
    const sectionDiv = document.createElement('div');
    sectionDiv.className = 'custom-section';
    sectionDiv.innerHTML = `
        <button type="button" class="remove-btn">&times;</button>
        <div class="form-group">
            <label>Titre de la section :</label>
            <input type="text" name="custom_section_titles[]" value="${title}" placeholder="Ex: Examen neurologique">
        </div>
        <div class="form-group">
            <label>Contenu :</label>
            <textarea name="custom_section_contents[]" rows="4" placeholder="Entrez les informations pour cette section">${content}</textarea>
        </div>
    `;
    
    container.appendChild(sectionDiv);
    
    // Add remove functionality
    sectionDiv.querySelector('.remove-btn').addEventListener('click', function() {
        sectionDiv.remove();
    });
}

// NEW: Display images (read-only)
function populateEditImages(images) {
    const container = document.getElementById('edit-images-container');
    container.innerHTML = '';
    
    if (images.length === 0) {
        container.innerHTML = '<p>Aucune image associée à ce cas.</p>';
        return;
    }
    
    const imagesGrid = document.createElement('div');
    imagesGrid.className = 'case-images-grid';
    
    images.forEach((image, index) => {
        const imageDiv = document.createElement('div');
        imageDiv.className = 'case-image-item';
        imageDiv.innerHTML = `
            <p>${image.description || `Image ${index + 1}`}</p>
            <img src="${image.path}" alt="${image.description || 'Image médicale'}" class="case-image" onclick="previewImageLarge('${image.path}')">
        `;
        imagesGrid.appendChild(imageDiv);
    });
    
    container.appendChild(imagesGrid);
}

// NEW: Close edit modal
function closeEditModal() {
    editCaseModal.classList.remove('visible');
    editCaseModal.classList.add('hidden');
    currentEditingCaseNumber = null;
    
    // Reset form
    editCaseForm.reset();
}

// NEW: Handle edit form submission
async function handleEditFormSubmit(event) {
    event.preventDefault();
    
    if (!currentEditingCaseNumber) {
        alert('Erreur: Aucun cas en cours de modification');
        return;
    }
    
    console.log('Submitting edit form for case:', currentEditingCaseNumber);
    
    // Disable form during submission
    const submitButton = document.querySelector('#edit-case-form button[type="submit"]');
    const originalText = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.textContent = 'Sauvegarde en cours...';
    
    try {
        // Collect form data
        const editedData = collectEditFormData();
        
        console.log('Sending edit request with data:', editedData);
        
        // Send update request
        const response = await authenticatedFetch(`/teacher/edit_case/${currentEditingCaseNumber}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                edited_data: editedData
            })
        });
        
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Response error:', errorText);
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.error) {
            alert(`Erreur: ${data.error}`);
        } else {
            alert('Cas modifié avec succès!');
            closeEditModal();
            // Add a small delay before refresh to ensure the save completed
            setTimeout(() => {
                window.location.reload();
            }, 500);
        }
        
    } catch (error) {
        console.error('Error submitting edit form:', error);
        alert(`Erreur lors de la modification du cas: ${error.message}`);
    } finally {
        // Re-enable form
        submitButton.disabled = false;
        submitButton.textContent = originalText;
    }
}

// NEW: Collect edit form data
function collectEditFormData() {
    console.log('Collecting edit form data...');
    
    // Basic information
    const specialty = document.getElementById('edit-specialty').value.trim();
    const consultationTimeInput = document.getElementById('edit-consultation-time-edit');
    const consultationTime = consultationTimeInput ? parseInt(consultationTimeInput.value) || 10 : 10;
    
    console.log('Basic info:', { specialty, consultationTime });
    
    // Patient information
    const patientInfo = {};
    
    // Get patient name
    const nameInput = document.getElementById('edit-patient-name');
    if (nameInput && nameInput.value.trim()) {
        patientInfo.name = nameInput.value.trim();
    }
    
    // Get patient gender
    const genderInput = document.getElementById('edit-patient-gender');
    if (genderInput && genderInput.value) {
        patientInfo.gender = genderInput.value;
    }
    
    // Get patient occupation
    const occupationInput = document.getElementById('edit-patient-occupation');
    if (occupationInput && occupationInput.value.trim()) {
        patientInfo.occupation = occupationInput.value.trim();
    }
    
    // Get patient age
    const ageInput = document.getElementById('edit-patient-age');
    if (ageInput && ageInput.value && ageInput.value.trim() !== '') {
        const ageValue = parseInt(ageInput.value);
        if (!isNaN(ageValue) && ageValue > 0) {
            patientInfo.age = ageValue;
        }
    }
    
    // Collect medical history
    const medicalHistory = [];
    const medicalHistoryInputs = document.querySelectorAll('#edit-medical-history-container .medical-history-input');
    medicalHistoryInputs.forEach(input => {
        if (input.value && input.value.trim()) {
            medicalHistory.push(input.value.trim());
        }
    });
    
    if (medicalHistory.length > 0) {
        patientInfo.medical_history = medicalHistory;
    }
    
    console.log('Patient info:', patientInfo);
    
    // Collect symptoms
    const symptoms = [];
    const symptomInputs = document.querySelectorAll('#edit-symptoms-container .symptom-input');
    symptomInputs.forEach(input => {
        if (input.value && input.value.trim()) {
            symptoms.push(input.value.trim());
        }
    });
    
    console.log('Symptoms:', symptoms);
    
    // Collect evaluation checklist
    const checklist = [];
    const checklistItems = document.querySelectorAll('#edit-checklist-container .checklist-item');
    
    checklistItems.forEach((item, index) => {
        const descriptionInput = item.querySelector('input[name="checklist_descriptions[]"]');
        const pointsInput = item.querySelector('input[name="checklist_points[]"]');
        const categorySelect = item.querySelector('select[name="checklist_categories[]"]');
        
        if (descriptionInput && descriptionInput.value && descriptionInput.value.trim()) {
            const description = descriptionInput.value.trim();
            const points = pointsInput ? (parseInt(pointsInput.value) || 1) : 1;
            const category = categorySelect ? categorySelect.value : 'Général';
            
            checklist.push({
                description: description,
                points: points,
                category: category,
                completed: false
            });
        }
    });
    
    console.log('Evaluation checklist:', checklist);
    
    // Additional information
    const diagnosisInput = document.getElementById('edit-diagnosis');
    const diagnosis = diagnosisInput ? diagnosisInput.value.trim() : '';
    
    const differentialInput = document.getElementById('edit-differential-diagnosis');
    const differentialDiagnosis = differentialInput ? differentialInput.value.trim() : '';
    
    const directivesInput = document.getElementById('edit-directives');
    const directives = directivesInput ? directivesInput.value.trim() : '';
    
    const notesInput = document.getElementById('edit-additional-notes');
    const additionalNotes = notesInput ? notesInput.value.trim() : '';
    
    console.log('Additional info:', { diagnosis, differentialDiagnosis, directives, additionalNotes });
    
    // Collect custom sections
    const customSections = [];
    const customSectionTitles = document.querySelectorAll('#edit-custom-sections-container input[name="custom_section_titles[]"]');
    const customSectionContents = document.querySelectorAll('#edit-custom-sections-container textarea[name="custom_section_contents[]"]');
    
    for (let i = 0; i < customSectionTitles.length; i++) {
        const title = customSectionTitles[i] ? customSectionTitles[i].value.trim() : '';
        const content = customSectionContents[i] ? customSectionContents[i].value.trim() : '';
        
        if (title && content) {
            customSections.push({
                title: title,
                content: content
            });
        }
    }
    
    console.log('Custom sections:', customSections);
    
    // Build final data object
    const editedData = {
        case_number: currentEditingCaseNumber,
        specialty: specialty,
        patient_info: patientInfo,
        symptoms: symptoms,
        evaluation_checklist: checklist,
        consultation_time: consultationTime,
        custom_sections: customSections
    };
    
    // Add optional fields only if they have values
    if (diagnosis) editedData.diagnosis = diagnosis;
    if (differentialDiagnosis) editedData.differential_diagnosis = differentialDiagnosis;
    if (directives) editedData.directives = directives;
    if (additionalNotes) editedData.additional_notes = additionalNotes;
    
    console.log('Final edited data:', editedData);
    
    return editedData;
}   



// Set up validation handlers
function setupValidation() {
    // Add event listeners for form validation in preview/edit mode
    document.addEventListener('input', function(event) {
        // For validation in extraction preview mode
        if (event.target.matches(
            '.edit-field input, .edit-field select, ' + 
            '.symptom-input, .category-symptoms .symptom-input, ' +
            '.checklist-description, .category-items .checklist-description'
        )) {
            if (typeof validateEditedForm === 'function') {
                validateEditedForm();
            } else {
                // Fallback to simpler validation if the full validation system isn't loaded
                updateValidationWarnings();
            }
        }
    });
    
    // Initialize validation (with a slight delay to ensure DOM is ready)
    setTimeout(function() {
        const warningBox = document.querySelector('.extraction-issues');
        if (warningBox) {
            // Check if we have the full validation system
            if (typeof validateEditedForm === 'function') {
                validateEditedForm();
            } else {
                // Fallback
                updateValidationWarnings();
            }
        }
    }, 100);
}

// Handle file upload form submission
async function handleUploadFormSubmit(event) {
    event.preventDefault();
    
    // Get case number and validate it
    const caseNumberInput = document.getElementById('case-number');
    const caseNumber = caseNumberInput.value.trim();
    
    // Validate case number before proceeding
    const isValidCaseNumber = await validateCaseNumberBeforeSubmit(caseNumber, caseNumberInput);
    
    if (!isValidCaseNumber) {
        alert('Veuillez corriger le numéro de cas avant de continuer.');
        caseNumberInput.focus();
        return;
    }
    
    // Show processing status
    uploadStatus.classList.remove('hidden');
    processingMessage.textContent = 'Téléchargement et traitement du fichier en cours...';
    extractionResults.innerHTML = '';
    
    // Get form data
    const formData = new FormData(uploadForm);
    
    // Get image files from the input 
    const imageFiles = document.getElementById('image-files').files;
    
    // Add all image files to formData if there are any
    if (imageFiles && imageFiles.length > 0) {
        for (let i = 0; i < imageFiles.length; i++) {
            formData.append('image_files', imageFiles[i]);
        }
    }
    
    try {
        // Send file to backend for processing - UPDATED URL
        const response = await authenticatedFetch('/teacher/process_case_file', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        if (data.error) {
            processingMessage.textContent = `Erreur: ${data.error}`;
        } else {
            processingMessage.textContent = 'Extraction réussie!';
            
            // Store extracted data
            extractedData = data.extracted_data;
            
            // Show preview and edit interface
            showExtractionPreview(data);
        }
    } catch (error) {
        console.error('Error:', error);
        processingMessage.textContent = `Une erreur est survenue: ${error.message}`;
    }
}


// Handle manual entry form submission
async function handleManualFormSubmit(event) {
    event.preventDefault();
    
    // Get case number and validate it
    const caseNumberInput = document.getElementById('manual-case-number');
    const caseNumber = caseNumberInput.value.trim();
    
    // Validate case number before proceeding
    const isValidCaseNumber = await validateCaseNumberBeforeSubmit(caseNumber, caseNumberInput);
    
    if (!isValidCaseNumber) {
        alert('Veuillez corriger le numéro de cas avant de continuer.');
        caseNumberInput.focus();
        return;
    }
    
    // Show processing status
    uploadStatus.classList.remove('hidden');
    processingMessage.textContent = 'Traitement des données en cours...';
    extractionResults.innerHTML = '';
    
    // Create FormData from manual form
    const formData = new FormData(manualEntryForm);
    
    // Add all tracked uploaded images to the form data
    uploadedImages.forEach((image, index) => {
        formData.append('manual_images', image.file);
    });
    
    // Process custom sections
    const customSections = [];
    const customSectionTitles = formData.getAll('custom_section_titles[]');
    const customSectionContents = formData.getAll('custom_section_contents[]');
    
    for (let i = 0; i < customSectionTitles.length; i++) {
        if (customSectionTitles[i].trim() && customSectionContents[i].trim()) {
            customSections.push({
                title: customSectionTitles[i].trim(),
                content: customSectionContents[i].trim()
            });
        }
    }
    
    // Add custom sections as JSON string
    if (customSections.length > 0) {
        formData.append('custom_sections', JSON.stringify(customSections));
    }
    
    // Add flag to indicate this is manual entry
    formData.append('is_manual_entry', 'true');
    
    try {
        // Send manual data to backend for processing - CORRECTED URL
        const response = await authenticatedFetch('/teacher/process_manual_case', {  
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            processingMessage.textContent = `Erreur: ${data.error}`;
        } else {
            processingMessage.textContent = 'Cas créé avec succès!';
            
            // Display creation results
            let resultsHTML = '<h4>Cas créé:</h4>';
            resultsHTML += '<ul>';
            resultsHTML += `<li><strong>Cas:</strong> ${data.case_number}</li>`;
            resultsHTML += `<li><strong>Spécialité:</strong> ${data.specialty}</li>`;
            
            if (data.patient_info) {
                resultsHTML += '<li><strong>Information patient:</strong> Ajoutées</li>';
            }
            
            if (data.symptoms && data.symptoms.length > 0) {
                resultsHTML += `<li><strong>Symptômes:</strong> ${data.symptoms.length} symptômes ajoutés</li>`;
            }
            
            if (data.evaluation_checklist && data.evaluation_checklist.length > 0) {
                resultsHTML += `<li><strong>Grille d'évaluation:</strong> ${data.evaluation_checklist.length} éléments ajoutés</li>`;
            }
            
            if (data.images && data.images.length > 0) {
                resultsHTML += `<li><strong>Images:</strong> ${data.images.length} images ajoutées</li>`;
            }
            
            if (data.custom_sections && data.custom_sections.length > 0) {
                resultsHTML += `<li><strong>Sections personnalisées:</strong> ${data.custom_sections.length} sections ajoutées</li>`;
            }
            
            resultsHTML += '</ul>';
            
            extractionResults.innerHTML = resultsHTML;
            
            // Reset form
            manualEntryForm.reset();
            uploadedImages = []; // Clear tracked images
            imagesPreview.innerHTML = '';
            customSectionsContainer.innerHTML = '';
            
            // Clear validation state
            clearCaseNumberValidation(caseNumberInput);
            lastValidatedCaseNumber = null;
            isCurrentCaseNumberValid = false;
            
            // Refresh the page after 3 seconds to show updated case list
            setTimeout(() => {
                window.location.reload();
            }, 3000);
        }
    } catch (error) {
        console.error('Error:', error);
        processingMessage.textContent = `Une erreur est survenue: ${error.message}`;
    }
}

// Function to show extraction preview with editor
function showExtractionPreview(data) {
    // Validate the extraction data
    const issues = validateExtraction ? validateExtraction(data.extracted_data) : [];
    
    // Display extracted data with edit options
    let previewHTML = '<h4>Données extraites - Veuillez vérifier et corriger si nécessaire:</h4>';
    
    // Show any issues detected
    if (issues.length > 0) {
        previewHTML += '<div class="extraction-issues">';
        previewHTML += '<h5>Problèmes détectés:</h5><ul>';
        issues.forEach(issue => {
            previewHTML += `<li>${issue}</li>`;
        });
        previewHTML += '</ul></div>';
    }
    
    // Build editable preview interface
    previewHTML += buildEditablePreview(data.extracted_data);
    
    // Add save and cancel buttons
    previewHTML += `
        <div class="extraction-actions">
            <button id="save-extraction" class="submit-button" ${issues.length > 0 ? 'disabled' : ''}>Enregistrer le cas</button>
            <button id="cancel-extraction" class="cancel-button">Annuler</button>
        </div>
    `;
    
    // Display the preview
    extractionResults.innerHTML = previewHTML;
    
    // IMPORTANT: Set up event handlers for the dynamically created buttons
    setupExtractionPreviewEventHandlers();
    
    // Add event listeners for save and cancel buttons
    document.getElementById('save-extraction').addEventListener('click', () => {
        // Use the advanced validation if available, otherwise proceed
        if (validateEditedForm) {
            if (validateEditedForm()) {
                saveEditedCase(data);
            }
        } else {
            saveEditedCase(data);
        }
    });
    
    document.getElementById('cancel-extraction').addEventListener('click', () => {
        extractionResults.innerHTML = '';
        uploadForm.reset();
    });
    
    // Add real-time validation for form fields
    document.querySelectorAll('.edit-field input, .edit-field select, .symptom-input, .checklist-description')
        .forEach(element => {
            element.addEventListener('input', () => {
                if (validateEditedForm) {
                    validateEditedForm();
                } else {
                    updateValidationWarnings();
                }
            });
        });
}

// handles event listeners for extraction preview buttons
function setupExtractionPreviewEventHandlers() {
    console.log('Setting up extraction preview event handlers...');
    
    // Add Patient Field button
    const addPatientFieldBtn = document.getElementById('add-patient-field');
    if (addPatientFieldBtn) {
        addPatientFieldBtn.addEventListener('click', function() {
            addCustomPatientField();
        });
    }

    // Add Medical History button
    const addMedicalHistoryBtn = document.getElementById('add-medical-history-btn');
    if (addMedicalHistoryBtn) {
        addMedicalHistoryBtn.addEventListener('click', function() {
            addPreviewMedicalHistoryItem('');
        });
    }

    // Add Symptom button
    const addSymptomBtn = document.getElementById('add-symptom-btn');
    if (addSymptomBtn) {
        addSymptomBtn.addEventListener('click', function() {
            addPreviewSymptomItem('');
        });
    }

    // Add Symptom Category button
    const addSymptomCategoryBtn = document.getElementById('add-symptom-category');
    if (addSymptomCategoryBtn) {
        addSymptomCategoryBtn.addEventListener('click', function() {
            addSymptomCategory();
        });
    }

    // Add Checklist Item button
    const addChecklistBtn = document.getElementById('add-checklist-btn');
    if (addChecklistBtn) {
        addChecklistBtn.addEventListener('click', function() {
            addPreviewChecklistItem('', 1, 'Général');
        });
    }

    // Add Checklist Category button
    const addChecklistCategoryBtn = document.getElementById('add-checklist-category');
    if (addChecklistCategoryBtn) {
        addChecklistCategoryBtn.addEventListener('click', function() {
            addChecklistCategory();
        });
    }

    // Add Differential Diagnosis button
    const addDifferentialBtn = document.getElementById('add-differential-btn');
    if (addDifferentialBtn) {
        addDifferentialBtn.addEventListener('click', function() {
            addDifferentialDiagnosis('');
        });
    }

    // Add Custom Section button
    const addPreviewCustomSectionBtn = document.getElementById('add-preview-custom-section');
    if (addPreviewCustomSectionBtn) {
        addPreviewCustomSectionBtn.addEventListener('click', function() {
            addPreviewCustomSection('', '');
        });
    }

    // Set up existing remove buttons
    setupExistingRemoveButtons();
    
    console.log('Extraction preview event handlers set up successfully');
}

// Function to set up remove buttons for existing items
function setupExistingRemoveButtons() {
    // Medical history remove buttons
    document.querySelectorAll('.remove-medical-history').forEach(btn => {
        btn.addEventListener('click', function() {
            this.closest('.edit-medical-history').remove();
        });
    });

    // Symptom remove buttons
    document.querySelectorAll('.remove-symptom').forEach(btn => {
        btn.addEventListener('click', function() {
            this.closest('.edit-symptom').remove();
        });
    });

    // Category remove buttons
    document.querySelectorAll('.remove-category').forEach(btn => {
        btn.addEventListener('click', function() {
            this.closest('.symptom-category, .checklist-category').remove();
        });
    });

    // Checklist item remove buttons
    document.querySelectorAll('.remove-checklist-item').forEach(btn => {
        btn.addEventListener('click', function() {
            this.closest('.edit-checklist-item').remove();
        });
    });

    // Differential diagnosis remove buttons
    document.querySelectorAll('.remove-differential').forEach(btn => {
        btn.addEventListener('click', function() {
            this.closest('.edit-differential').remove();
        });
    });

    // Custom section remove buttons
    document.querySelectorAll('.remove-custom-section').forEach(btn => {
        btn.addEventListener('click', function() {
            this.closest('.edit-custom-section').remove();
        });
    });

    // Custom field remove buttons
    document.querySelectorAll('.remove-custom-field').forEach(btn => {
        btn.addEventListener('click', function() {
            this.closest('.custom-field').remove();
        });
    });
}

// Add custom patient field
function addCustomPatientField() {
    const container = document.querySelector('.editable-preview .preview-section');
    
    const fieldDiv = document.createElement('div');
    fieldDiv.className = 'edit-field custom-field';
    fieldDiv.innerHTML = `
        <label>Nom du champ:</label>
        <input type="text" class="custom-field-name" value="">
        <label>Valeur:</label>
        <input type="text" class="custom-field-value" value="">
        <button type="button" class="remove-custom-field">×</button>
    `;
    
    // Insert before the "add patient field" button
    const addBtn = document.getElementById('add-patient-field');
    addBtn.parentNode.insertBefore(fieldDiv, addBtn);
    
    // Add remove functionality
    fieldDiv.querySelector('.remove-custom-field').addEventListener('click', function() {
        fieldDiv.remove();
    });
}

// Add medical history item in preview
function addPreviewMedicalHistoryItem(value = '') {
    const container = document.getElementById('edit-medical-history-container');
    
    const historyDiv = document.createElement('div');
    historyDiv.className = 'edit-medical-history';
    historyDiv.innerHTML = `
        <input type="text" class="medical-history-input" value="${value}" placeholder="Entrez l'antécédent médical">
        <button type="button" class="remove-medical-history">×</button>
    `;
    
    container.appendChild(historyDiv);
    
    // Add remove functionality
    historyDiv.querySelector('.remove-medical-history').addEventListener('click', function() {
        historyDiv.remove();
    });
}

// Add symptom item in preview
function addPreviewSymptomItem(value = '') {
    const container = document.getElementById('edit-symptoms-container');
    
    const symptomDiv = document.createElement('div');
    symptomDiv.className = 'edit-symptom';
    symptomDiv.innerHTML = `
        <input type="text" class="symptom-input" value="${value}" placeholder="Décrivez le symptôme">
        <button type="button" class="remove-symptom">×</button>
    `;
    
    container.appendChild(symptomDiv);
    
    // Add remove functionality
    symptomDiv.querySelector('.remove-symptom').addEventListener('click', function() {
        symptomDiv.remove();
    });
}

// Add symptom category
function addSymptomCategory() {
    const container = document.getElementById('edit-symptoms-container');
    
    const categoryDiv = document.createElement('div');
    categoryDiv.className = 'symptom-category';
    categoryDiv.innerHTML = `
        <div class="category-header">
            <input type="text" class="category-name" value="" placeholder="Nom de la catégorie">
            <button type="button" class="remove-category">×</button>
        </div>
        <div class="category-symptoms">
        </div>
        <button type="button" class="add-category-symptom secondary-button">+ Ajouter un symptôme à cette catégorie</button>
    `;
    
    container.appendChild(categoryDiv);
    
    // Add remove functionality for category
    categoryDiv.querySelector('.remove-category').addEventListener('click', function() {
        categoryDiv.remove();
    });
    
    // Add functionality for adding symptoms to this category
    categoryDiv.querySelector('.add-category-symptom').addEventListener('click', function() {
        const categorySymptoms = categoryDiv.querySelector('.category-symptoms');
        
        const symptomDiv = document.createElement('div');
        symptomDiv.className = 'edit-symptom';
        symptomDiv.innerHTML = `
            <input type="text" class="symptom-input" value="" placeholder="Décrivez le symptôme">
            <button type="button" class="remove-symptom">×</button>
        `;
        
        categorySymptoms.appendChild(symptomDiv);
        
        // Add remove functionality
        symptomDiv.querySelector('.remove-symptom').addEventListener('click', function() {
            symptomDiv.remove();
        });
    });
}

// Add checklist item in preview
function addPreviewChecklistItem(description = '', points = 1, category = '') {
    const container = document.getElementById('edit-checklist-container');
    
    const itemDiv = document.createElement('div');
    itemDiv.className = 'edit-checklist-item';
    itemDiv.innerHTML = `
        <div class="edit-field-group">
            <label>Description:</label>
            <input type="text" class="checklist-description" value="${description}" placeholder="Description de l'élément">
        </div>
        <div class="edit-field-group small">
            <label>Points:</label>
            <input type="number" class="checklist-points" value="${points}" min="1">
        </div>
        <div class="edit-field-group">
            <label>Catégorie:</label>
            <input type="text" class="checklist-category" value="${category}" placeholder="Catégorie">
        </div>
        <button type="button" class="remove-checklist-item">×</button>
    `;
    
    container.appendChild(itemDiv);
    
    // Add remove functionality
    itemDiv.querySelector('.remove-checklist-item').addEventListener('click', function() {
        itemDiv.remove();
    });
}

// Add checklist category
function addChecklistCategory() {
    const container = document.getElementById('edit-checklist-container');
    
    const categoryDiv = document.createElement('div');
    categoryDiv.className = 'checklist-category';
    categoryDiv.innerHTML = `
        <div class="category-header">
            <input type="text" class="category-name" value="" placeholder="Nom de la catégorie">
            <button type="button" class="remove-category">×</button>
        </div>
        <div class="category-items">
        </div>
        <button type="button" class="add-category-item secondary-button">+ Ajouter un élément à cette catégorie</button>
    `;
    
    container.appendChild(categoryDiv);
    
    // Add remove functionality for category
    categoryDiv.querySelector('.remove-category').addEventListener('click', function() {
        categoryDiv.remove();
    });
    
    // Add functionality for adding items to this category
    categoryDiv.querySelector('.add-category-item').addEventListener('click', function() {
        const categoryItems = categoryDiv.querySelector('.category-items');
        
        const itemDiv = document.createElement('div');
        itemDiv.className = 'edit-checklist-item';
        itemDiv.innerHTML = `
            <div class="edit-field-group">
                <label>Description:</label>
                <input type="text" class="checklist-description" value="" placeholder="Description de l'élément">
            </div>
            <div class="edit-field-group small">
                <label>Points:</label>
                <input type="number" class="checklist-points" value="1" min="1">
            </div>
            <button type="button" class="remove-checklist-item">×</button>
        `;
        
        categoryItems.appendChild(itemDiv);
        
        // Add remove functionality
        itemDiv.querySelector('.remove-checklist-item').addEventListener('click', function() {
            itemDiv.remove();
        });
    });
}

// Add differential diagnosis
function addDifferentialDiagnosis(value = '') {
    const container = document.getElementById('edit-differential-container');
    
    const differentialDiv = document.createElement('div');
    differentialDiv.className = 'edit-differential';
    differentialDiv.innerHTML = `
        <input type="text" class="differential-input" value="${value}" placeholder="Diagnostic différentiel">
        <button type="button" class="remove-differential">×</button>
    `;
    
    container.appendChild(differentialDiv);
    
    // Add remove functionality
    differentialDiv.querySelector('.remove-differential').addEventListener('click', function() {
        differentialDiv.remove();
    });
}

// Add custom section in preview
function addPreviewCustomSection(title = '', content = '') {
    const container = document.getElementById('edit-custom-sections-container');
    
    const sectionDiv = document.createElement('div');
    sectionDiv.className = 'edit-custom-section';
    sectionDiv.innerHTML = `
        <div class="edit-field">
            <label>Titre:</label>
            <input type="text" class="custom-section-title" value="${title}" placeholder="Titre de la section">
        </div>
        <div class="edit-field">
            <label>Contenu:</label>
            <textarea class="custom-section-content" rows="4" placeholder="Contenu de la section">${content}</textarea>
        </div>
        <button type="button" class="remove-custom-section">×</button>
    `;
    
    container.appendChild(sectionDiv);
    
    // Add remove functionality
    sectionDiv.querySelector('.remove-custom-section').addEventListener('click', function() {
        sectionDiv.remove();
    });
}


// Function to save edited case data
function saveEditedCase(previewData) {
    console.log('saveEditedCase called with:', previewData);
    
    // Collect edited data from the extraction preview form
    let editedData;
    
    try {
        // Try to collect data using the advanced function if available
        if (typeof collectEditedFormData === 'function') {
            editedData = collectEditedFormData();
        } else {
            // Fallback: collect basic data from the preview form
            editedData = collectBasicEditedData();
        }
        
        console.log('Collected edited data:', editedData);
        
        // Ensure required fields are present
        if (!editedData.case_number && previewData.case_number) {
            editedData.case_number = previewData.case_number;
        }
        
        if (!editedData.specialty && previewData.specialty) {
            editedData.specialty = previewData.specialty;
        }
        
        // Validate that we have essential data
        if (!editedData.case_number || !editedData.specialty) {
            throw new Error('Missing required case number or specialty');
        }
        
        console.log('Final edited data being sent:', editedData);
        
    } catch (error) {
        console.error('Error collecting edited data:', error);
        processingMessage.textContent = `Erreur lors de la collecte des données: ${error.message}`;
        return;
    }
    
    // Show saving status
    processingMessage.textContent = 'Sauvegarde en cours...';
    
    // Send the edited data to the backend
    authenticatedFetch('/teacher/save_edited_case', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            edited_data: editedData,
            case_number: previewData.case_number,
            specialty: previewData.specialty
        })
    })
    .then(response => {
        console.log('Response status:', response.status);
        if (!response.ok) {
            return response.text().then(text => {
                console.error('Response error text:', text);
                throw new Error(`HTTP ${response.status}: ${text}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Response data:', data);
        if (data.error) {
            processingMessage.textContent = `Erreur: ${data.error}`;
        } else {
            // Show success message based on action
            const action = data.action === 'updated' ? 'mis à jour' : 'enregistré';
            processingMessage.textContent = `Cas ${action} avec succès!`;
            
            // Clear the extraction results
            extractionResults.innerHTML = '';
            
            // Reset the upload form if it exists
            if (uploadForm) {
                uploadForm.reset();
                // Clear file input previews
                const fileImagesPreview = document.getElementById('file-images-preview');
                if (fileImagesPreview) {
                    fileImagesPreview.innerHTML = '';
                }
                
                // Clear case number validation
                const caseNumberInput = document.getElementById('case-number');
                if (caseNumberInput) {
                    clearCaseNumberValidation(caseNumberInput);
                    lastValidatedCaseNumber = null;
                    isCurrentCaseNumberValid = false;
                }
            }
            
            // Show success message for a bit longer, then refresh
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        }
    })
    .catch(error => {
        console.error('Error saving case:', error);
        processingMessage.textContent = `Une erreur est survenue lors de l'enregistrement: ${error.message}`;
    });
}


function collectBasicEditedData() {
    console.log('Using basic data collection');
    
    // Get basic patient info
    const patientInfo = {};
    
    const nameField = document.getElementById('edit-patient-name');
    if (nameField && nameField.value.trim()) {
        patientInfo.name = nameField.value.trim();
    }
    
    const ageField = document.getElementById('edit-patient-age');
    if (ageField && ageField.value) {
        patientInfo.age = parseInt(ageField.value) || null;
    }
    
    const genderField = document.getElementById('edit-patient-gender');
    if (genderField && genderField.value) {
        patientInfo.gender = genderField.value;
    }
    
    const occupationField = document.getElementById('edit-patient-occupation');
    if (occupationField && occupationField.value.trim()) {
        patientInfo.occupation = occupationField.value.trim();
    }
    
    // Collect symptoms from the preview
    const symptoms = [];
    const symptomInputs = document.querySelectorAll('.symptom-input');
    symptomInputs.forEach(input => {
        if (input.value && input.value.trim()) {
            symptoms.push(input.value.trim());
        }
    });
    
    // Collect checklist items from the preview
    const checklist = [];
    const checklistItems = document.querySelectorAll('.edit-checklist-item, .checklist-item');
    
    checklistItems.forEach(item => {
        const descInput = item.querySelector('.checklist-description') || 
                         item.querySelector('input[name="checklist_descriptions[]"]');
        const pointsInput = item.querySelector('.checklist-points') || 
                           item.querySelector('input[name="checklist_points[]"]');
        const categoryInput = item.querySelector('.checklist-category') || 
                             item.querySelector('select[name="checklist_categories[]"]');
        
        if (descInput && descInput.value && descInput.value.trim()) {
            const description = descInput.value.trim();
            const points = pointsInput ? (parseInt(pointsInput.value) || 1) : 1;
            const category = categoryInput ? (categoryInput.value || 'Général') : 'Général';
            
            checklist.push({
                description: description,
                points: points,
                category: category,
                completed: false
            });
        }
    });
    
    // Get other fields
    const diagnosisField = document.getElementById('edit-diagnosis');
    const diagnosis = diagnosisField ? diagnosisField.value.trim() : '';
    
    const directivesField = document.getElementById('edit-directives');
    const directives = directivesField ? directivesField.value.trim() : '';
    
    const consultationTimeField = document.getElementById('edit-consultation-time');
    const consultationTime = consultationTimeField ? (parseInt(consultationTimeField.value) || 10) : 10;
    
    // Collect custom sections
    const customSections = [];
    const customSectionTitles = document.querySelectorAll('.custom-section-title');
    const customSectionContents = document.querySelectorAll('.custom-section-content');
    
    for (let i = 0; i < customSectionTitles.length; i++) {
        const title = customSectionTitles[i] ? customSectionTitles[i].value.trim() : '';
        const content = customSectionContents[i] ? customSectionContents[i].value.trim() : '';
        
        if (title && content) {
            customSections.push({
                title: title,
                content: content
            });
        }
    }
    
    // Collect image descriptions
    const images = [];
    const imageDescriptions = document.querySelectorAll('.image-description');
    imageDescriptions.forEach((input, index) => {
        const description = input.value.trim() || 'Image médicale';
        const imageContainer = input.closest('.image-preview-item');
        if (imageContainer) {
            const img = imageContainer.querySelector('img');
            if (img && img.src) {
                images.push({
                    path: img.src,
                    description: description,
                    index: index
                });
            }
        }
    });
    
    const editedData = {
        patient_info: patientInfo,
        symptoms: symptoms,
        evaluation_checklist: checklist,
        diagnosis: diagnosis,
        directives: directives,
        consultation_time: consultationTime,
        custom_sections: customSections,
        images: images
    };
    
    console.log('Basic edited data collected:', editedData);
    return editedData;
}

// Function to validate extraction data
function validateExtraction(extractedData) {
    const issues = [];
    
    // Check patient info
    const patientInfo = extractedData.patient_info || {};
    
    // Check age - consider both None and 0 as invalid, but accept any other value
    const age = patientInfo.age;
    if (age === null || age === undefined || age === 0 || age === '') {
        issues.push("L'âge du patient est manquant ou non valide");
    }
    
    // Check gender - must be a non-empty string
    const gender = patientInfo.gender;
    if (!gender || typeof gender !== 'string' || gender.trim() === '') {
        issues.push("Le sexe du patient est manquant");
    }
    
    // Check symptoms - must have at least one non-empty symptom
    const symptoms = extractedData.symptoms || [];
    if (!symptoms.length || symptoms.every(symptom => !symptom || symptom.trim() === '')) {
        issues.push("Aucun symptôme n'a été détecté");
    }
    
    // Check evaluation checklist - must have at least 3 items
    const checklist = extractedData.evaluation_checklist || [];
    if (checklist.length < 3) {
        issues.push("Grille d'évaluation incomplète ou manquante (minimum 3 éléments requis)");
    }
    
    return issues;
}

// Function to update the extraction issues UI
function updateExtractionIssuesUI(issues, container) {
    // Find or create issues section
    let issuesSection = container.querySelector('.extraction-issues');
    
    if (issues.length > 0) {
        // Create issues section if it doesn't exist
        if (!issuesSection) {
            issuesSection = document.createElement('div');
            issuesSection.className = 'extraction-issues';
            container.prepend(issuesSection);
        }
        
        // Update content
        let issuesHTML = '<h5>Problèmes détectés:</h5><ul>';
        issues.forEach(issue => {
            issuesHTML += `<li>${issue}</li>`;
        });
        issuesHTML += '</ul>';
        
        issuesSection.innerHTML = issuesHTML;
        issuesSection.style.display = '';
    } else if (issuesSection) {
        // Hide issues section if no issues
        issuesSection.style.display = 'none';
    }
}

// Function to collect form data as structured object
function collectEditedFormData() {
    // Get the case number and specialty from the preview data or form
    const caseNumberInput = document.getElementById('case-number') || document.getElementById('edit-case-number');
    const specialtyInput = document.getElementById('specialty') || document.getElementById('edit-specialty');
    
    // Basic patient info
    const patientInfo = {
        name: document.getElementById('edit-patient-name')?.value || '',
        gender: document.getElementById('edit-patient-gender')?.value || ''
    };
    
    // Get age with proper handling
    const ageInput = document.getElementById('edit-patient-age')?.value;
    if (ageInput && ageInput.trim() !== '') {
        patientInfo.age = parseInt(ageInput, 10);
    }
    
    // Add occupation if the field exists and has a value
    const occupationField = document.getElementById('edit-patient-occupation');
    if (occupationField && occupationField.value.trim()) {
        patientInfo.occupation = occupationField.value.trim();
    }
    
    // Collect custom patient fields
    document.querySelectorAll('.custom-field').forEach(field => {
        const fieldName = field.querySelector('.custom-field-name')?.value.trim();
        const fieldValue = field.querySelector('.custom-field-value')?.value.trim();
        
        if (fieldName && fieldValue) {
            patientInfo[fieldName] = fieldValue;
        }
    });
    
    // Collect medical history
    const medicalHistoryContainer = document.getElementById('edit-medical-history-container');
    if (medicalHistoryContainer) {
        const medicalHistory = [];
        medicalHistoryContainer.querySelectorAll('.medical-history-input').forEach(input => {
            if (input.value.trim()) {
                medicalHistory.push(input.value.trim());
            }
        });
        
        if (medicalHistory.length > 0) {
            patientInfo.medical_history = medicalHistory;
        }
    }
    
    // Lab results if present
    const labResultsField = document.getElementById('edit-lab-results');
    if (labResultsField && labResultsField.value.trim()) {
        patientInfo.lab_results = labResultsField.value.trim();
    }
    
    // Collect all symptoms
    const symptoms = [];
    
    // First get uncategorized symptoms
    document.querySelectorAll('#edit-symptoms-container > .edit-symptom .symptom-input').forEach(input => {
        if (input.value.trim()) {
            symptoms.push(input.value.trim());
        }
    });
    
    // Then get categorized symptoms
    document.querySelectorAll('.symptom-category').forEach(category => {
        const categoryName = category.querySelector('.category-name')?.value.trim();
        if (categoryName) {
            category.querySelectorAll('.category-symptoms .symptom-input').forEach(input => {
                if (input.value.trim()) {
                    symptoms.push(`${categoryName}: ${input.value.trim()}`);
                }
            });
        }
    });
    
    // Collect checklist items
    const checklist = [];
    
    // First get items with explicit category fields
    document.querySelectorAll('#edit-checklist-container > .edit-checklist-item').forEach(item => {
        const description = item.querySelector('.checklist-description')?.value.trim();
        if (description) {
            const categoryInput = item.querySelector('.checklist-category');
            const category = categoryInput ? categoryInput.value.trim() : 'Général';
            const pointsInput = item.querySelector('.checklist-points');
            const points = pointsInput ? parseInt(pointsInput.value, 10) || 1 : 1;
            
            checklist.push({
                description: description,
                points: points,
                category: category,
                completed: false
            });
        }
    });
    
    // Then get items from category groups
    document.querySelectorAll('.checklist-category').forEach(category => {
        const categoryName = category.querySelector('.category-name')?.value.trim() || 'Général';
        
        category.querySelectorAll('.category-items .edit-checklist-item').forEach(item => {
            const description = item.querySelector('.checklist-description')?.value.trim();
            if (description) {
                const pointsInput = item.querySelector('.checklist-points');
                const points = pointsInput ? parseInt(pointsInput.value, 10) || 1 : 1;
                
                checklist.push({
                    description: description,
                    points: points,
                    category: categoryName,
                    completed: false
                });
            }
        });
    });
    
    // Collect remaining data
    const editedData = {
        case_number: caseNumberInput?.value || '',
        specialty: specialtyInput?.value || '',
        patient_info: patientInfo,
        symptoms: symptoms,
        evaluation_checklist: checklist,
        diagnosis: document.getElementById('edit-diagnosis')?.value || '',
        directives: document.getElementById('edit-directives')?.value || '',
        consultation_time: parseInt(document.getElementById('edit-consultation-time')?.value, 10) || 10,
        custom_sections: [],
        images: []
    };
    
    // Collect differential diagnoses if present
    const differentialContainer = document.getElementById('edit-differential-container');
    if (differentialContainer) {
        const differentials = [];
        differentialContainer.querySelectorAll('.differential-input').forEach(input => {
            if (input.value.trim()) {
                differentials.push(input.value.trim());
            }
        });
        
        if (differentials.length > 0) {
            editedData.differential_diagnosis = differentials;
        }
    }
    
    // Collect custom sections
    document.querySelectorAll('.edit-custom-section').forEach(section => {
        const title = section.querySelector('.custom-section-title')?.value.trim();
        const content = section.querySelector('.custom-section-content')?.value.trim();
        
        if (title && content) {
            editedData.custom_sections.push({
                title: title,
                content: content
            });
        }
    });
    
    // Collect and update image descriptions
    const images = document.querySelectorAll('.image-description');
    images.forEach(input => {
        const index = parseInt(input.dataset.index, 10);
        const description = input.value.trim();
        
        if (input.closest('.image-preview-item') && input.closest('.image-preview-item').querySelector('img')) {
            const img = input.closest('.image-preview-item').querySelector('img');
            editedData.images.push({
                path: img.src,
                description: description || 'Image médicale',
                index: index
            });
        }
    });
    
    return editedData;
}
// Function to validate edited form data in real-time
function validateEditedForm() {
    const editedData = collectEditedFormData();
    const issues = validateExtraction(editedData);
    
    // Update UI with validation issues
    updateExtractionIssuesUI(issues, document.querySelector('.editable-preview'));
    
    // Enable/disable save button based on validation
    const saveButton = document.getElementById('save-extraction');
    if (saveButton) {
        saveButton.disabled = issues.length > 0;
        saveButton.title = issues.length > 0 ? 
            "Veuillez corriger les problèmes avant d'enregistrer" : "";
    }
    
    return issues.length === 0;
}

// Improved validation warning function
function updateValidationWarnings() {
    const warningBox = document.querySelector('.extraction-issues');
    if (!warningBox) return;

    // Check all required fields directly
    const age = document.getElementById('edit-patient-age')?.value;
    const gender = document.getElementById('edit-patient-gender')?.value;
    
    // Check if there's at least one non-empty symptom
    const symptomInputs = Array.from(document.querySelectorAll('.symptom-input, .category-symptoms .symptom-input'));
    const hasSymptoms = symptomInputs.some(input => input.value.trim() !== "");
    
    // Check if there are at least 3 non-empty checklist items
    const checklistItems = Array.from(document.querySelectorAll(
        '.checklist-description, .category-items .checklist-description'
    )).filter(input => input.value.trim() !== "");
    const hasValidChecklist = checklistItems.length >= 3;

    // Collect all validation issues
    const issues = [];
    if (!age) issues.push("L'âge du patient est manquant");
    if (!gender) issues.push("Le sexe du patient est manquant");
    if (!hasSymptoms) issues.push("Aucun symptôme n'a été détecté");
    if (!hasValidChecklist) issues.push("Grille d'évaluation incomplète (minimum 3 éléments requis)");

    // Update the warning box content or hide it
    if (issues.length > 0) {
        // Make sure the warning box is visible
        warningBox.style.display = '';
        
        // Update the content with current issues
        let issuesHTML = '<h5>Problèmes détectés:</h5><ul>';
        issues.forEach(issue => {
            issuesHTML += `<li>${issue}</li>`;
        });
        issuesHTML += '</ul>';
        
        // Find or create the issues list container
        let issuesList = warningBox.querySelector('ul');
        if (!issuesList) {
            warningBox.innerHTML = issuesHTML;
        } else {
            warningBox.innerHTML = issuesHTML;
        }
    } else {
        // Hide the warning box if no issues
        warningBox.style.display = 'none';
    }
}

// Update the preview display of all images
function updateImagesPreview() {
    imagesPreview.innerHTML = '';
    
    if (uploadedImages.length > 0) {
        // Display counter for multiple files
        const fileCountIndicator = document.createElement('div');
        fileCountIndicator.className = 'file-count-indicator';
        fileCountIndicator.textContent = `${uploadedImages.length} image${uploadedImages.length > 1 ? 's' : ''} sélectionnée${uploadedImages.length > 1 ? 's' : ''}`;
        imagesPreview.appendChild(fileCountIndicator);
        
        // Add descriptions textarea hint
        if (uploadedImages.length > 1) {
            const descriptionsHint = document.createElement('div');
            descriptionsHint.className = 'descriptions-hint';
            descriptionsHint.innerHTML = `<strong>N'oubliez pas:</strong> Ajoutez ${uploadedImages.length} descriptions dans le champ ci-dessous (une par ligne)`;
            descriptionsHint.style.color = '#2196F3';
            descriptionsHint.style.marginBottom = '10px';
            imagesPreview.appendChild(descriptionsHint);
        }
        
        // Create a container for the image preview grid
        const previewGrid = document.createElement('div');
        previewGrid.className = 'images-preview-grid';
        imagesPreview.appendChild(previewGrid);
        
        // Process each file for preview
        uploadedImages.forEach((image, index) => {
            const reader = new FileReader();
            
            reader.onload = (e) => {
                const previewItem = document.createElement('div');
                previewItem.classList.add('image-preview-item');
                previewItem.dataset.imageId = image.id;
                
                previewItem.innerHTML = `
                    <div class="image-number">#${index + 1}</div>
                    <button type="button" class="delete-image-btn" data-id="${image.id}">×</button>
                    <img src="${e.target.result}" alt="Preview ${index + 1}" onclick="previewImageLarge(this.src)">
                    <div class="image-desc-input">
                        <input type="text" placeholder="Description image ${index + 1}" 
                               value="${image.description}"
                               onchange="updateSingleImageDescription('${image.id}', this.value)">
                    </div>
                `;
                
                previewGrid.appendChild(previewItem);
            };
            
            reader.readAsDataURL(image.file);
        });
    }
    
    // Update descriptions textarea
    updateImageDescriptionsTextarea();
}

// Function to delete an image from the uploads
function deleteUploadedImage(imageId) {
    uploadedImages = uploadedImages.filter(img => img.id !== imageId);
    updateImagesPreview();
    updateImageDescriptionsTextarea();
}

// Update a single image description
function updateSingleImageDescription(imageId, description) {
    const imageIndex = uploadedImages.findIndex(img => img.id === imageId);
    if (imageIndex !== -1) {
        uploadedImages[imageIndex].description = description;
        updateImageDescriptionsTextarea();
    }
}

// Update the textarea with all image descriptions
function updateImageDescriptionsTextarea() {
    const descriptionsTextarea = document.getElementById('image-descriptions');
    if (descriptionsTextarea) {
        const descriptions = uploadedImages.map(img => img.description || `Description de l'image`);
        descriptionsTextarea.value = descriptions.join('\n');
    }
}

// Function to show a larger preview of an image
function previewImageLarge(src) {
    // Create modal for larger image view
    const modal = document.createElement('div');
    modal.style.position = 'fixed';
    modal.style.top = '0';
    modal.style.left = '0';
    modal.style.width = '100%';
    modal.style.height = '100%';
    modal.style.backgroundColor = 'rgba(0,0,0,0.8)';
    modal.style.display = 'flex';
    modal.style.alignItems = 'center';
    modal.style.justifyContent = 'center';
    modal.style.zIndex = '1000';
    modal.onclick = () => document.body.removeChild(modal);
    
    // Image container
    const imgContainer = document.createElement('div');
    imgContainer.style.maxWidth = '90%';
    imgContainer.style.maxHeight = '90%';
    imgContainer.style.position = 'relative';
    
    // Close button
    const closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.style.position = 'absolute';
    closeBtn.style.top = '-15px';
    closeBtn.style.right = '-15px';
    closeBtn.style.backgroundColor = 'white';
    closeBtn.style.color = 'black';
    closeBtn.style.border = 'none';
    closeBtn.style.borderRadius = '50%';
    closeBtn.style.width = '30px';
    closeBtn.style.height = '30px';
    closeBtn.style.fontWeight = 'bold';
    closeBtn.style.fontSize = '20px';
    closeBtn.style.cursor = 'pointer';
    closeBtn.onclick = (e) => {
        e.stopPropagation();
        document.body.removeChild(modal);
    };
    
    // Image element
    const img = document.createElement('img');
    img.src = src;
    img.style.maxWidth = '100%';
    img.style.maxHeight = '80vh';
    img.style.objectFit = 'contain';
    img.style.backgroundColor = 'white';
    img.style.padding = '10px';
    img.style.borderRadius = '4px';
    
    imgContainer.appendChild(img);
    imgContainer.appendChild(closeBtn);
    modal.appendChild(imgContainer);
    document.body.appendChild(modal);
}

// Modal helper functions
function openModal() {
    caseDetailsModal.classList.add('visible');
    caseDetailsModal.classList.remove('hidden');
}

function closeModalFunction() {
    caseDetailsModal.classList.remove('visible');
    caseDetailsModal.classList.add('hidden');
}

// Build editable preview UI
function buildEditablePreview(extractedData) {
    // This function creates editable fields for all extracted data
    let html = '<div class="editable-preview">';
    
    // Patient info section with enhanced editing
    html += '<div class="preview-section">';
    html += '<h5>Informations du patient</h5>';
    
    const patientInfo = extractedData.patient_info || {};
    html += `
        <div class="edit-field">
            <label>Nom:</label>
            <input type="text" id="edit-patient-name" value="${patientInfo.name || ''}">
        </div>
        <div class="edit-field">
            <label>Âge:</label>
            <input type="number" id="edit-patient-age" value="${patientInfo.age || ''}">
        </div>
        <div class="edit-field">
            <label>Sexe:</label>
            <select id="edit-patient-gender">
                <option value="" ${!patientInfo.gender ? 'selected' : ''}>Sélectionner</option>
                <option value="Masculin" ${patientInfo.gender === 'Masculin' ? 'selected' : ''}>Masculin</option>
                <option value="Féminin" ${patientInfo.gender === 'Féminin' ? 'selected' : ''}>Féminin</option>
            </select>
        </div>
    `;

    // Add occupation if present
    if (patientInfo.occupation) {
        html += `
            <div class="edit-field">
                <label>Profession:</label>
                <input type="text" id="edit-patient-occupation" value="${patientInfo.occupation || ''}">
            </div>
        `;
    }

    // Display any other patient info fields that might exist
    for (const [key, value] of Object.entries(patientInfo)) {
        if (!['name', 'age', 'gender', 'occupation'].includes(key) && value) {
            html += `
                <div class="edit-field custom-field">
                    <label>Nom du champ:</label>
                    <input type="text" class="custom-field-name" value="${key}">
                    <label>Valeur:</label>
                    <input type="text" class="custom-field-value" value="${value}">
                    <button type="button" class="remove-custom-field">×</button>
                </div>
            `;
        }
    }

    // Add custom field button
    html += `
        <div class="edit-field">
            <button type="button" id="add-patient-field" class="secondary-button">+ Ajouter un champ personnalisé</button>
        </div>
    `;
    html += '</div>';
    
    // Medical history section (if present)
    if (patientInfo.medical_history && patientInfo.medical_history.length > 0) {
        html += '<div class="preview-section">';
        html += '<h5>Antécédents médicaux</h5>';
        html += '<div id="edit-medical-history-container">';
        
        patientInfo.medical_history.forEach((history, index) => {
            html += `
                <div class="edit-medical-history">
                    <input type="text" class="medical-history-input" value="${history}">
                    <button type="button" class="remove-medical-history" data-index="${index}">×</button>
                </div>
            `;
        });
        
        html += '</div>';
        html += '<button type="button" id="add-medical-history-btn" class="secondary-button">+ Ajouter un antécédent</button>';
        html += '</div>';
    }
    
    // Symptoms section with category support
    html += '<div class="preview-section">';
    html += '<h5>Symptômes</h5>';
    html += '<div id="edit-symptoms-container">';
    
    const symptoms = extractedData.symptoms || [];
    
    // Group symptoms by category if they have categories
    const symptomsByCategory = {};
    let hasCategories = false;
    
    symptoms.forEach(symptom => {
        // Check if symptom has category format "Category: Symptom"
        const categoryMatch = symptom.match(/^([^:]+):\s*(.+)$/);
        if (categoryMatch) {
            hasCategories = true;
            const category = categoryMatch[1].trim();
            const symptomText = categoryMatch[2].trim();
            
            if (!symptomsByCategory[category]) {
                symptomsByCategory[category] = [];
            }
            symptomsByCategory[category].push(symptomText);
        } else {
            // Uncategorized symptoms go into 'uncategorized'
            if (!symptomsByCategory['uncategorized']) {
                symptomsByCategory['uncategorized'] = [];
            }
            symptomsByCategory['uncategorized'].push(symptom);
        }
    });
    
    if (hasCategories) {
        // Display symptoms by category
        for (const [category, categorySymptoms] of Object.entries(symptomsByCategory)) {
            if (category === 'uncategorized') continue; // Skip here, we'll add them at the end
            
            html += `
                <div class="symptom-category">
                    <div class="category-header">
                        <input type="text" class="category-name" value="${category}">
                        <button type="button" class="remove-category">×</button>
                    </div>
                    <div class="category-symptoms">
            `;
            
            categorySymptoms.forEach((symptom, index) => {
                html += `
                    <div class="edit-symptom">
                        <input type="text" class="symptom-input" value="${symptom}">
                        <button type="button" class="remove-symptom" data-index="${index}">×</button>
                    </div>
                `;
            });
            
            html += `
                    </div>
                    <button type="button" class="add-category-symptom secondary-button">+ Ajouter un symptôme à cette catégorie</button>
                </div>
            `;
        }
        
        // Now add uncategorized symptoms if any
        if (symptomsByCategory['uncategorized'] && symptomsByCategory['uncategorized'].length > 0) {
            symptomsByCategory['uncategorized'].forEach((symptom, index) => {
                html += `
                    <div class="edit-symptom">
                        <input type="text" class="symptom-input" value="${symptom}">
                        <button type="button" class="remove-symptom" data-index="${index}">×</button>
                    </div>
                `;
            });
        }
    } else {
        // No categories, just list symptoms
        if (symptoms.length > 0) {
            symptoms.forEach((symptom, index) => {
                html += `
                    <div class="edit-symptom">
                        <input type="text" class="symptom-input" value="${symptom}">
                        <button type="button" class="remove-symptom" data-index="${index}">×</button>
                    </div>
                `;
            });
        } else {
            html += `
                <div class="edit-symptom">
                    <input type="text" class="symptom-input" value="">
                    <button type="button" class="remove-symptom" data-index="0">×</button>
                </div>
            `;
        }
    }
    
    html += '</div>';
    html += '<button type="button" id="add-symptom-btn" class="secondary-button">+ Ajouter un symptôme</button>';
    html += '<button type="button" id="add-symptom-category" class="secondary-button">+ Ajouter une catégorie de symptômes</button>';
    html += '</div>';
    
    // Evaluation checklist section with category support
    html += '<div class="preview-section">';
    html += '<h5>Grille d\'évaluation</h5>';
    html += '<div id="edit-checklist-container">';
    
    const checklist = extractedData.evaluation_checklist || [];
    
    // Group checklist items by category
    const itemsByCategory = {};
    let hasChecklistCategories = false;
    
    checklist.forEach(item => {
        if (item.category) {
            hasChecklistCategories = true;
            if (!itemsByCategory[item.category]) {
                itemsByCategory[item.category] = [];
            }
            itemsByCategory[item.category].push(item);
        } else {
            if (!itemsByCategory['Général']) {
                itemsByCategory['Général'] = [];
            }
            itemsByCategory['Général'].push(item);
        }
    });
    
    if (hasChecklistCategories) {
        // Display items by category
        for (const [category, items] of Object.entries(itemsByCategory)) {
            html += `
                <div class="checklist-category">
                    <div class="category-header">
                        <input type="text" class="category-name" value="${category}">
                        <button type="button" class="remove-category">×</button>
                    </div>
                    <div class="category-items">
            `;
            
            items.forEach((item, index) => {
                html += `
                    <div class="edit-checklist-item">
                        <div class="edit-field-group">
                            <label>Description:</label>
                            <input type="text" class="checklist-description" value="${item.description || ''}">
                        </div>
                        <div class="edit-field-group small">
                            <label>Points:</label>
                            <input type="number" class="checklist-points" value="${item.points || 1}" min="1">
                        </div>
                        <button type="button" class="remove-checklist-item" data-index="${index}">×</button>
                    </div>
                `;
            });
            
            html += `
                    </div>
                    <button type="button" class="add-category-item secondary-button">+ Ajouter un élément à cette catégorie</button>
                </div>
            `;
        }
    } else {
        // No categories, just list items
        if (checklist.length > 0) {
            checklist.forEach((item, index) => {
                html += `
                    <div class="edit-checklist-item">
                        <div class="edit-field-group">
                            <label>Description:</label>
                            <input type="text" class="checklist-description" value="${item.description || ''}">
                        </div>
                        <div class="edit-field-group small">
                            <label>Points:</label>
                            <input type="number" class="checklist-points" value="${item.points || 1}" min="1">
                        </div>
                        <div class="edit-field-group">
                            <label>Catégorie:</label>
                            <input type="text" class="checklist-category" value="${item.category || ''}">
                        </div>
                        <button type="button" class="remove-checklist-item" data-index="${index}">×</button>
                    </div>
                `;
            });
        } else {
            html += `
                <div class="edit-checklist-item">
                    <div class="edit-field-group">
                        <label>Description:</label>
                        <input type="text" class="checklist-description" value="">
                    </div>
                    <div class="edit-field-group small">
                        <label>Points:</label>
                        <input type="number" class="checklist-points" value="1" min="1">
                    </div>
                    <div class="edit-field-group">
                        <label>Catégorie:</label>
                        <input type="text" class="checklist-category" value="">
                    </div>
                    <button type="button" class="remove-checklist-item" data-index="0">×</button>
                </div>
            `;
        }
    }
    
    html += '</div>';
    html += '<button type="button" id="add-checklist-btn" class="secondary-button">+ Ajouter un élément</button>';
    html += '<button type="button" id="add-checklist-category" class="secondary-button">+ Ajouter une catégorie</button>';
    html += '</div>';
    
    // Diagnosis section
    html += '<div class="preview-section">';
    html += '<h5>Diagnostic</h5>';
    html += `
        <div class="edit-field">
            <label>Diagnostic principal:</label>
            <input type="text" id="edit-diagnosis" value="${extractedData.diagnosis || ''}">
        </div>
    `;
    
    // Add differential diagnosis if present
    if (extractedData.differential_diagnosis) {
        html += '<div id="edit-differential-container">';
        html += '<label>Diagnostics différentiels:</label>';
        
        const differentials = Array.isArray(extractedData.differential_diagnosis) ? 
            extractedData.differential_diagnosis : [extractedData.differential_diagnosis];
        
        differentials.forEach((differential, index) => {
            html += `
                <div class="edit-differential">
                    <input type="text" class="differential-input" value="${differential}">
                    <button type="button" class="remove-differential" data-index="${index}">×</button>
                </div>
            `;
        });
        
        html += '</div>';
        html += '<button type="button" id="add-differential-btn" class="secondary-button">+ Ajouter un diagnostic différentiel</button>';
    }
    
    html += '</div>';
    
    // Lab results section if present
    if (patientInfo.lab_results) {
        html += '<div class="preview-section">';
        html += '<h5>Résultats de laboratoire</h5>';
        html += `
            <div class="edit-field">
                <textarea id="edit-lab-results" rows="5">${patientInfo.lab_results}</textarea>
            </div>
        `;
        html += '</div>';
    }
    

   // Directives Section
    html += '<div class="preview-section">';
    html += '<h5>Directives pour l\'étudiant</h5>';
    html += `
        <div class="edit-field">
            <label>Instructions et timing:</label>
            <textarea id="edit-directives" rows="5">${extractedData.directives || ''}</textarea>
            <p class="field-help">Ces instructions seront affichées aux étudiants pendant la consultation</p>
        </div>
    `;
    html += '</div>';
    
    // Consultation time
    html += '<div class="preview-section">';
    html += '<h5>Durée de consultation</h5>';
    html += `
        <div class="edit-field">
            <label>Durée (minutes):</label>
            <input type="number" id="edit-consultation-time" value="${extractedData.consultation_time || 10}" min="1" max="60">
        </div>
    `;
    html += '</div>';
    
    // Custom sections
    html += '<div class="preview-section">';
    html += '<h5>Sections personnalisées</h5>';
    html += '<div id="edit-custom-sections-container">';
    
    const customSections = extractedData.custom_sections || [];
    if (customSections.length > 0) {
        customSections.forEach((section, index) => {
            html += `
                <div class="edit-custom-section">
                    <div class="edit-field">
                        <label>Titre:</label>
                        <input type="text" class="custom-section-title" value="${section.title || ''}">
                    </div>
                    <div class="edit-field">
                        <label>Contenu:</label>
                        <textarea class="custom-section-content" rows="4">${section.content || ''}</textarea>
                    </div>
                    <button type="button" class="remove-custom-section" data-index="${index}">×</button>
                </div>
            `;
        });
    }
    
    html += '</div>';
    html += '<button type="button" id="add-preview-custom-section" class="secondary-button">+ Ajouter une section personnalisée</button>';
    html += '</div>';
    
    // Images section if images exist
    if (extractedData.images && extractedData.images.length > 0) {
        html += '<div class="preview-section">';
        html += '<h5>Images</h5>';
        html += '<div class="images-preview">';
        
        extractedData.images.forEach((image, index) => {
            html += `
                <div class="image-preview-item">
                    <img src="${image.path}" alt="${image.description || 'Image médicale'}">
                    <div class="edit-field">
                        <input type="text" class="image-description" data-index="${index}" 
                               value="${image.description || ''}" placeholder="Description de l'image">
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        html += '</div>';
    }
    
    html += '</div>'; // Close editable-preview div
    
    return html;
}

document.addEventListener('click', function(event) {
    // View case details - UPDATED URL
    if (event.target.classList.contains('view-button')) {
        const caseNumber = event.target.getAttribute('data-case');
        
        // Validate case number
        if (!caseNumber || caseNumber === 'None' || caseNumber === 'null') {
            alert("Erreur: Numéro de cas invalide");
            return;
        }
        
        // Add loading state to button
        const originalText = event.target.textContent;
        event.target.textContent = 'Chargement...';
        event.target.disabled = true;
        
        try {
            // Add cache busting parameter to ensure fresh data - UPDATED URL
            const timestamp = new Date().getTime();
            authenticatedFetch(`/get_case/${caseNumber}?t=${timestamp}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('Fresh case data loaded:', data);
                    
                    // Format and display case details in modal
                    let detailsHTML = '';
                    
                    // Basic information
                    detailsHTML += `<div class="case-details-section">
                        <h4>Informations générales</h4>
                        <p><strong>Numéro de cas:</strong> ${data.case_number}</p>
                        <p><strong>Spécialité:</strong> ${data.specialty || 'Non spécifiée'}</p>
                        <p><strong>Durée de consultation:</strong> ${data.consultation_time || 10} minutes</p>
                    </div>`;
                    
                    // Patient information
                    if (data.patient_info) {
                        detailsHTML += `<div class="case-details-section">
                            <h4>Informations du patient</h4>
                            <p><strong>Nom:</strong> ${data.patient_info.name || 'Non spécifié'}</p>
                            <p><strong>Âge:</strong> ${data.patient_info.age || 'Non spécifié'}</p>
                            <p><strong>Sexe:</strong> ${data.patient_info.gender || 'Non spécifié'}</p>
                            <p><strong>Profession:</strong> ${data.patient_info.occupation || 'Non spécifiée'}</p>`;
                        
                        // Medical history if available
                        if (data.patient_info.medical_history && data.patient_info.medical_history.length > 0) {
                            detailsHTML += `<h5>Antécédents médicaux</h5><ul class="case-details-list">`;
                            data.patient_info.medical_history.forEach(item => {
                                detailsHTML += `<li>${item}</li>`;
                            });
                            detailsHTML += `</ul>`;
                        }
                        
                        detailsHTML += `</div>`;
                    }
                    
                    // Symptoms
                    if (data.symptoms && data.symptoms.length > 0) {
                        detailsHTML += `<div class="case-details-section">
                            <h4>Symptômes (${data.symptoms.length})</h4>
                            <ul class="case-details-list">`;
                        
                        data.symptoms.forEach(symptom => {
                            detailsHTML += `<li>${symptom}</li>`;
                        });
                        
                        detailsHTML += `</ul></div>`;
                    }
                    
                    // Evaluation checklist
                    if (data.evaluation_checklist && data.evaluation_checklist.length > 0) {
                        detailsHTML += `<div class="case-details-section">
                            <h4>Grille d'évaluation (${data.evaluation_checklist.length} éléments)</h4>
                            <div class="case-details-grid">`;
                        
                        data.evaluation_checklist.forEach(item => {
                            const category = item.category ? `<small>${item.category}</small>` : '';
                            detailsHTML += `<div class="checklist-item-detail">
                                <p>${item.description} (${item.points} points)</p>
                                ${category}
                            </div>`;
                        });
                        
                        detailsHTML += `</div></div>`;
                    }
                    
                    // Diagnosis if available
                    if (data.diagnosis) {
                        detailsHTML += `<div class="case-details-section">
                            <h4>Diagnostic</h4>
                            <p>${data.diagnosis}</p>
                        </div>`;
                    }
                    
                    // Directives section
                    if (data.directives) {
                        detailsHTML += `<div class="case-details-section">
                            <h4>Directives</h4>
                            <div class="custom-section-detail">
                                <p>${data.directives.replace(/\n/g, '<br>')}</p>
                            </div>
                        </div>`;
                    }

                    // Images
                    if (data.images && data.images.length > 0) {
                        detailsHTML += `<div class="case-details-section">
                            <h4>Images (${data.images.length})</h4>
                            <div class="case-images-grid">`;
                        
                        data.images.forEach(image => {
                            detailsHTML += `<div class="case-image-item">
                                <p>${image.description || 'Image'}</p>
                                <img src="${image.path}?t=${timestamp}" alt="${image.description || 'Image médicale'}" class="case-image" onclick="previewImageLarge('${image.path}')">
                            </div>`;
                        });
                        
                        detailsHTML += `</div></div>`;
                    }
                    
                    // Custom sections
                    if (data.custom_sections && data.custom_sections.length > 0) {
                        data.custom_sections.forEach(section => {
                            detailsHTML += `<div class="case-details-section">
                                <h4>${section.title}</h4>
                                <div class="custom-section-detail">
                                    <p>${section.content}</p>
                                </div>
                            </div>`;
                        });
                    }
                    
                    // Additional notes
                    if (data.additional_notes) {
                        detailsHTML += `<div class="case-details-section">
                            <h4>Notes supplémentaires</h4>
                            <p>${data.additional_notes}</p>
                        </div>`;
                    }
                    
                    // Set content and open modal
                    caseDetailsContent.innerHTML = detailsHTML;
                    openModal();
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert(`Erreur lors de la récupération des détails du cas: ${error.message}`);
                })
                .finally(() => {
                    // Restore button state
                    event.target.textContent = originalText;
                    event.target.disabled = false;
                });
        } catch (error) {
            console.error('Error:', error);
            alert(`Erreur lors de la récupération des détails du cas: ${error.message}`);
            // Restore button state
            event.target.textContent = originalText;
            event.target.disabled = false;
        }
    }
    
    // Edit button click handler - UPDATED function call
    if (event.target.classList.contains('edit-button')) {
        const caseNumber = event.target.getAttribute('data-case');
        openEditModal(caseNumber);
    }
    // Delete cas
    if (event.target.classList.contains('delete-button')) {
        const caseNumber = event.target.getAttribute('data-case');
        
        // Validate case number
        if (!caseNumber || caseNumber === 'None' || caseNumber === 'null') {
            alert("Erreur: Impossible de supprimer un cas sans numéro valide");
            return;
        }
        
        if (confirm(`Êtes-vous sûr de vouloir supprimer le cas ${caseNumber} ? Cette action est irréversible.`)) {
            try {
                authenticatedFetch(`/teacher/delete_case/${caseNumber}`, {  // ✅ CORRECT URL
                    method: 'DELETE'
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        alert('Cas supprimé avec succès!');
                        // Refresh the page to update the case list
                        window.location.reload();
                    } else {
                        alert(`Erreur: ${data.error}`);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert(`Erreur lors de la suppression du cas: ${error.message}`);
                });
            } catch (error) {
                console.error('Error:', error);
                alert(`Erreur lors de la suppression du cas: ${error.message}`);
            }
        }
    }
});

// Also update the handleEditFormSubmit function to show better success feedback
async function handleEditFormSubmit(event) {
    event.preventDefault();
    
    if (!currentEditingCaseNumber) {
        alert('Erreur: Aucun cas en cours de modification');
        return;
    }
    
    console.log('Submitting edit form for case:', currentEditingCaseNumber);
    
    // Disable form during submission
    const submitButton = document.querySelector('#edit-case-form button[type="submit"]');
    const originalText = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.textContent = 'Sauvegarde en cours...';
    
    try {
        // Collect form data
        const editedData = collectEditFormData();
        
        console.log('Sending edit request with data:', editedData);
        
        // Send update request
        const response = await authenticatedFetch(`/teacher/edit_case/${currentEditingCaseNumber}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                edited_data: editedData
            })
        });
        
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Response error:', errorText);
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.error) {
            alert(`Erreur: ${data.error}`);
        } else {
            alert(`Cas ${currentEditingCaseNumber} modifié avec succès!\n\nLes modifications ont été sauvegardées.`);
            closeEditModal();
            
            // Update the case list table row if it exists
            updateCaseListRow(currentEditingCaseNumber, editedData);
            
            // Small delay to ensure save completed, then reload
            setTimeout(() => {
                window.location.reload();
            }, 1000);
        }
        
    } catch (error) {
        console.error('Error submitting edit form:', error);
        alert(`Erreur lors de la modification du cas: ${error.message}`);
    } finally {
        // Re-enable form
        submitButton.disabled = false;
        submitButton.textContent = originalText;
    }
}

function updateCaseListRow(caseNumber, editedData) {
    const rows = document.querySelectorAll('table tbody tr');
    rows.forEach(row => {
        const caseCell = row.cells[0]; // First cell contains case number
        if (caseCell && caseCell.textContent.trim() === caseNumber) {
            const specialtyCell = row.cells[1]; // Second cell contains specialty
            if (specialtyCell && editedData.specialty) {
                specialtyCell.textContent = editedData.specialty;
            }
        }
    });
}

// Tab navigation for teacher interface
function showTeacherTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.teacher-tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all nav tabs
    document.querySelectorAll('.teacher-nav-tabs .nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    
    // Add active class to clicked nav tab
    event.target.classList.add('active');
    
    // Load content for specific tabs
    if (tabName === 'stations-management-tab') {
        loadTeacherStations();
    } else if (tabName === 'student-performance-tab') {
        loadStudentPerformance();
    }
}

// Load teacher stations management
async function loadTeacherStations(searchQuery = '') {
    try {
        let url = '/teacher/stations';
        if (searchQuery) {
            url += `?search=${encodeURIComponent(searchQuery)}`;
        }
        
        const response = await authenticatedFetch(url);
        if (!response.ok) {
            throw new Error('Failed to load stations');
        }
        
        const data = await response.json();
        
        // Update stats
        document.getElementById('total-stations').textContent = data.total;
        
        // Calculate averages
        const totalCompletions = data.stations.reduce((sum, station) => sum + station.completion_count, 0);
        const avgCompletions = data.stations.length > 0 ? Math.round(totalCompletions / data.stations.length) : 0;
        const avgScore = data.stations.length > 0 ? 
            Math.round(data.stations.reduce((sum, station) => sum + station.average_score, 0) / data.stations.length) : 0;
        
        document.getElementById('avg-completion-rate').textContent = avgCompletions;
        document.getElementById('avg-station-score').textContent = avgScore + '%';
        
        // Update table
        const tableBody = document.getElementById('teacher-stations-table-body');
        tableBody.innerHTML = '';
        
        if (data.stations.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="8" style="text-align: center;">Aucune station trouvée</td></tr>';
        } else {
            data.stations.forEach(station => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${station.case_number}</td>
                    <td>${station.specialty}</td>
                    <td>${station.consultation_time}</td>
                    <td>${station.created_at}</td>
                    <td>${station.updated_at}</td>
                    <td><span class="completion-badge">${station.completion_count}</span></td>
                    <td><span class="score-badge score-${getScoreClass(station.average_score)}">${station.average_score}%</span></td>
                    <td>
                        <button class="view-button" data-case="${station.case_number}">Voir</button>
                        <button class="edit-button" data-case="${station.case_number}">Modifier</button>
                        <button class="delete-button" data-case="${station.case_number}">Supprimer</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
        }
        
    } catch (error) {
        console.error('Error loading teacher stations:', error);
        document.getElementById('teacher-stations-table-body').innerHTML = 
            '<tr><td colspan="8" style="text-align: center;">Erreur lors du chargement</td></tr>';
    }
}

// Load student performance data
async function loadStudentPerformance(searchQuery = '') {
    try {
        let url = '/teacher/students/performance';
        if (searchQuery) {
            url += `?search=${encodeURIComponent(searchQuery)}`;
        }
        
        const response = await authenticatedFetch(url);
        if (!response.ok) {
            throw new Error('Failed to load student performance');
        }
        
        const data = await response.json();
        
        // Update overview stats
        document.getElementById('total-students').textContent = data.total;
        
        // Calculate active students (those with at least one workout)
        const activeStudents = data.students.filter(student => student.total_workouts > 0).length;
        document.getElementById('active-students').textContent = activeStudents;
        
        // Calculate overall average score
        const studentsWithScores = data.students.filter(student => student.average_score > 0);
        const overallAvgScore = studentsWithScores.length > 0 ? 
            Math.round(studentsWithScores.reduce((sum, student) => sum + student.average_score, 0) / studentsWithScores.length) : 0;
        document.getElementById('overall-avg-score').textContent = overallAvgScore + '%';
        
        // Update table
        const tableBody = document.getElementById('students-performance-table-body');
        tableBody.innerHTML = '';
        
        if (data.students.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Aucun étudiant trouvé</td></tr>';
        } else {
            data.students.forEach(student => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>
                        <div class="student-identifier">
                            <span class="student-name">${student.name}</span>
                            <span class="student-code-display">N° ${student.student_code}</span>
                        </div>
                    </td>
                    <td><span class="workout-badge">${student.total_workouts}</span></td>
                    <td><span class="station-badge">${student.unique_stations}</span></td>
                    <td><span class="score-badge score-${getScoreClass(student.average_score)}">${student.average_score}%</span></td>
                    <td>${student.last_login}</td>
                    <td>
                        <button class="detail-button" data-student-id="${student.student_id}" data-student-name="${student.name}" data-student-code="${student.student_code}">
                            Voir Détails
                        </button>
                    </td>
                `;
                tableBody.appendChild(row);
            });
            
            // Add event listeners to detail buttons
            document.querySelectorAll('.detail-button').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const studentId = e.target.getAttribute('data-student-id');
                    const studentName = e.target.getAttribute('data-student-name');
                    const studentCode = e.target.getAttribute('data-student-code');
                    openStudentDetailModal(studentId, studentName, studentCode);
                });
            });
        }
        
    } catch (error) {
        console.error('Error loading student performance:', error);
        document.getElementById('students-performance-table-body').innerHTML = 
            '<tr><td colspan="7" style="text-align: center;">Erreur lors du chargement</td></tr>';
    }
}

// Open student detail modal
async function openStudentDetailModal(studentId, studentName) {
    try {
        const response = await authenticatedFetch(`/teacher/students/${studentId}/detailed_performance`);
        if (!response.ok) {
            throw new Error('Failed to load student details');
        }
        
        const data = await response.json();
        
        // Update modal header
        const headerElement = document.getElementById('student-detail-name');
        if (headerElement) {
            // Create enhanced header with student name and Numéro d'Apogée
            const headerContainer = headerElement.parentElement;
            headerContainer.innerHTML = `
                <div class="student-detail-header">
                    <div class="student-detail-info">
                        <div class="student-detail-name">${studentName}</div>
                        <div class="student-detail-apogee">N° Apogée: ${studentCode}</div>
                    </div>
                </div>
            `;
        }        
        // Update student stats
        document.getElementById('detail-total-workouts').textContent = data.student.total_workouts;
        document.getElementById('detail-unique-stations').textContent = data.student.unique_stations;
        document.getElementById('detail-average-score').textContent = data.student.average_score + '%';
        
        // Update detailed performance table
        const tableBody = document.getElementById('detailed-performance-table-body');
        tableBody.innerHTML = '';
        
        if (data.performances.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="9" style="text-align: center;">Aucune performance enregistrée</td></tr>';
        } else {
            data.performances.forEach(perf => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${perf.completed_at}</td>
                    <td>${perf.case_number}</td>
                    <td>${perf.specialty}</td>
                    <td>${perf.score}%</td>
                    <td>${perf.points_earned}/${perf.points_total}</td>
                    <td><span class="grade-badge grade-${perf.grade}">${perf.grade}</span></td>
                    <td><span class="status-badge status-${perf.status.toLowerCase().replace(' ', '-')}">${perf.status}</span></td>
                    <td>${perf.consultation_duration}</td>
                    <td>
                        <button class="view-evaluation-btn" data-performance-id="${perf.id}">
                            Télécharger PDF
                        </button>
                    </td>
                `; // Changed button text for clarity
                tableBody.appendChild(row);
            });

            // Add event listeners for the newly created "Télécharger PDF" buttons
            tableBody.querySelectorAll('.view-evaluation-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const performanceId = e.target.getAttribute('data-performance-id');
                    if (performanceId) {
                        // Trigger download by navigating to the new endpoint
                        window.location.href = `/teacher/download_student_report/${performanceId}`;
                    } else {
                        alert("ID de performance non trouvé.");
                    }
                });
            });
        }
        
        // Show modal
        document.getElementById('student-detail-modal').classList.remove('hidden');
        document.getElementById('student-detail-modal').classList.add('visible');
        
    } catch (error) {
        console.error('Error loading student details:', error);
        alert('Erreur lors du chargement des détails de l\'étudiant');
    }
}

// Search functions
function searchTeacherStations() {
    const searchQuery = document.getElementById('teacher-stations-search').value.trim();
    loadTeacherStations(searchQuery);
}

function searchStudents() {
    const searchQuery = document.getElementById('student-search').value.trim();
    
    // Enhanced search that works with longer student codes
    loadStudentPerformance(searchQuery);
}

// Helper function to get score class
function getScoreClass(score) {
    if (score >= 90) return 'excellent';
    if (score >= 80) return 'good';
    if (score >= 70) return 'average';
    if (score >= 60) return 'below-average';
    return 'poor';
}



let caseNumberValidationInProgress = false;
let lastValidatedCaseNumber = null;
let isCurrentCaseNumberValid = false;

// Function to check case number availability
async function checkCaseNumberAvailability(caseNumber, inputElement, isEdit = false, originalCaseNumber = null) {
    if (!caseNumber || caseNumber.trim() === '') {
        clearCaseNumberValidation(inputElement);
        return false;
    }
    
    // If editing and the case number is the same as original, it's valid
    if (isEdit && originalCaseNumber && caseNumber === originalCaseNumber) {
        // For editing the same case number, show it's the current case
        showEditingCurrentCase(inputElement);
        return true;
    }
    
    // Avoid duplicate API calls
    if (caseNumber === lastValidatedCaseNumber) {
        return isCurrentCaseNumberValid;
    }
    
    caseNumberValidationInProgress = true;
    showCaseNumberChecking(inputElement);
    
    try {
        const response = await authenticatedFetch(`/check_case_number/${encodeURIComponent(caseNumber)}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        lastValidatedCaseNumber = caseNumber;
        
        if (data.exists) {
            showCaseNumberError(inputElement, data.message);
            isCurrentCaseNumberValid = false;
            return false;
        } else {
            // Case number is available - just show green border, no message
            showCaseNumberValid(inputElement, data.message);
            isCurrentCaseNumberValid = true;
            return true;
        }
        
    } catch (error) {
        console.error('Error checking case number:', error);
        showCaseNumberError(inputElement, 'Erreur lors de la vérification du numéro de cas');
        isCurrentCaseNumberValid = false;
        return false;
    } finally {
        caseNumberValidationInProgress = false;
    }
}

function showEditingCurrentCase(inputElement) {
    clearCaseNumberValidation(inputElement);
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'case-number-validation current';
    messageDiv.innerHTML = `<span class="validation-icon">ℹ️</span> Numéro de cas actuel`;
    
    inputElement.parentNode.appendChild(messageDiv);
    inputElement.classList.add('current');
    inputElement.classList.remove('error', 'valid', 'checking');
}

// Show checking state
function showCaseNumberChecking(inputElement) {
    clearCaseNumberValidation(inputElement);
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'case-number-validation checking';
    messageDiv.innerHTML = '<span class="validation-icon">⏳</span> Vérification en cours...';
    
    inputElement.parentNode.appendChild(messageDiv);
    inputElement.classList.add('checking');
}

// Show error state
function showCaseNumberError(inputElement, message) {
    clearCaseNumberValidation(inputElement);
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'case-number-validation error';
    messageDiv.innerHTML = `<span class="validation-icon">❌</span> ${message}`;
    
    inputElement.parentNode.appendChild(messageDiv);
    inputElement.classList.add('error');
    inputElement.classList.remove('valid', 'checking');
}

// Show valid state
function showCaseNumberValid(inputElement, message) {
    clearCaseNumberValidation(inputElement);
    
    // Only add the green border, no message for available case numbers
    inputElement.classList.add('valid');
    inputElement.classList.remove('error', 'checking');
    
    // Don't create any validation message div for available case numbers
}


// Clear validation state
function clearCaseNumberValidation(inputElement) {
    const existingValidation = inputElement.parentNode.querySelector('.case-number-validation');
    if (existingValidation) {
        existingValidation.remove();
    }
    inputElement.classList.remove('error', 'valid', 'checking', 'current');
}

// Debounce function to avoid too many API calls
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Set up case number validation for an input
function setupCaseNumberValidation(inputElement, isEdit = false, originalCaseNumber = null) {
    // Create debounced validation function
    const debouncedValidation = debounce(async (caseNumber) => {
        await checkCaseNumberAvailability(caseNumber, inputElement, isEdit, originalCaseNumber);
    }, 500); // Wait 500ms after user stops typing
    
    // Add event listeners
    inputElement.addEventListener('input', function() {
        const caseNumber = this.value.trim();
        
        // Reset validation state for new input
        lastValidatedCaseNumber = null;
        isCurrentCaseNumberValid = false;
        
        if (caseNumber === '') {
            clearCaseNumberValidation(this);
            return;
        }
        
        // Validate that it's a positive number
        if (!/^\d+$/.test(caseNumber)) {
            showCaseNumberError(this, 'Le numéro de cas doit contenir uniquement des chiffres');
            return;
        }
        
        // Check if it's zero
        if (parseInt(caseNumber) === 0) {
            showCaseNumberError(this, 'Le numéro de cas doit être supérieur à 0');
            return;
        }
        
        // If it's a valid number, check availability
        debouncedValidation(caseNumber);
    });
    
    inputElement.addEventListener('blur', function() {
        const caseNumber = this.value.trim();
        if (caseNumber && !caseNumberValidationInProgress) {
            // Final validation on blur
            checkCaseNumberAvailability(caseNumber, this, isEdit, originalCaseNumber);
        }
    });
}

// Function to check if case number is valid before form submission
async function validateCaseNumberBeforeSubmit(caseNumber, inputElement, isEdit = false, originalCaseNumber = null) {
    if (!caseNumber || caseNumber.trim() === '') {
        showCaseNumberError(inputElement, 'Le numéro de cas est obligatoire');
        return false;
    }
    
    // If validation is in progress, wait for it
    if (caseNumberValidationInProgress) {
        // Wait a bit and try again
        await new Promise(resolve => setTimeout(resolve, 100));
        return validateCaseNumberBeforeSubmit(caseNumber, inputElement, isEdit, originalCaseNumber);
    }
    
    // If we haven't validated this case number yet, do it now
    if (caseNumber !== lastValidatedCaseNumber) {
        return await checkCaseNumberAvailability(caseNumber, inputElement, isEdit, originalCaseNumber);
    }
    
    return isCurrentCaseNumberValid;
}

const teacherApogeeStyles = `
/* Teacher interface specific styles for Numéro d'Apogée */
.apogee-number {
    font-family: 'Courier New', Monaco, monospace;
    font-weight: bold;
    color: #007bff;
    font-size: 14px;
}

.code-type-label {
    font-size: 10px;
    color: #6c757d;
    text-transform: uppercase;
    font-weight: normal;
    margin-top: 2px;
}

.apogee-badge {
    background: #e3f2fd;
    color: #1976d2;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: normal;
    margin-left: 10px;
}

.apogee-number-small {
    display: block;
    font-size: 11px;
    color: #6c757d;
    font-family: 'Courier New', monospace;
    margin-top: 2px;
}

.student-name {
    display: block;
    font-weight: 500;
}

/* Student performance table specific styles */
.students-performance-table td:first-child {
    font-family: 'Courier New', monospace;
    min-width: 100px;
}

.student-identifier {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
}

.student-code-display {
    font-family: 'Courier New', Monaco, monospace;
    font-size: 12px;
    background: #e3f2fd;
    color: #1565c0;
    padding: 2px 6px;
    border-radius: 4px;
    font-weight: 600;
    margin-top: 3px;
}

/* Modal styles for student details */
.student-detail-header {
    display: flex;
    align-items: center;
    gap: 15px;
    margin-bottom: 20px;
    padding-bottom: 15px;
    border-bottom: 2px solid #eee;
}

.student-detail-info {
    display: flex;
    flex-direction: column;
}

.student-detail-name {
    font-size: 24px;
    font-weight: bold;
    color: #333;
}

.student-detail-apogee {
    font-family: 'Courier New', Monaco, monospace;
    font-size: 14px;
    background: #e3f2fd;
    color: #1565c0;
    padding: 4px 10px;
    border-radius: 8px;
    font-weight: 600;
    margin-top: 5px;
    align-self: flex-start;
}

/* Performance table improvements */
.detailed-performance-table .student-code-col {
    font-family: 'Courier New', Monaco, monospace;
    font-weight: 600;
}

/* Responsive adjustments for teacher interface */
@media (max-width: 768px) {
    .apogee-number {
        font-size: 12px;
    }
    
    .code-type-label {
        font-size: 9px;
    }
    
    .apogee-badge {
        font-size: 10px;
        padding: 1px 6px;
    }
    
    .student-detail-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
    }
    
    .student-detail-name {
        font-size: 20px;
    }
    
    .student-detail-apogee {
        font-size: 12px;
    }
    
    .students-performance-table td:first-child {
        min-width: 80px;
    }
}

/* High contrast mode support */
@media (prefers-contrast: high) {
    .apogee-number, .student-code-display, .student-detail-apogee {
        border: 2px solid currentColor;
        font-weight: bold;
    }
}

/* Reduce motion for users who prefer it */
@media (prefers-reduced-motion: reduce) {
    .apogee-number, .student-code-display {
        transition: none;
    }
}
`;

const teacherApogeeStyleSheet = document.createElement('style');
teacherApogeeStyleSheet.textContent = teacherApogeeStyles;
document.head.appendChild(teacherApogeeStyleSheet);

console.log('Teacher interface updated for Numéro d\'Apogée support');