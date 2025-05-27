// Global variables
const uploadForm = document.getElementById('upload-form');
const uploadStatus = document.getElementById('upload-status');
const processingMessage = document.getElementById('processing-message');
const extractionResults = document.getElementById('extraction-results');
const existingCases = document.getElementById('existing-cases');
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

// Variables for tracking data
let extractedData = null;
let uploadedImages = [];

// Main initialization when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize UI components
    setupTabSwitching();
    setupFormHandlers();
    setupImageHandlers();
    setupModalHandlers();
    
    // Initialize validation for extraction preview forms
    setupValidation();
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
    // Close modal functionality
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
        });
    }
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
    
    // Show processing status
    uploadStatus.classList.remove('hidden');
    processingMessage.textContent = 'Téléchargement et traitement du fichier en cours...';
    extractionResults.innerHTML = '';
    
    // Get form data - validate case number
    const formData = new FormData(uploadForm);
    const caseNumber = formData.get('case_number');
    
    if (!caseNumber || caseNumber.trim() === '') {
        processingMessage.textContent = "Erreur: Le numéro du cas est obligatoire";
        return;
    }
    
    // Get image files from the input 
    const imageFiles = document.getElementById('image-files').files;
    
    // Add all image files to formData if there are any
    if (imageFiles && imageFiles.length > 0) {
        for (let i = 0; i < imageFiles.length; i++) {
            formData.append('image_files', imageFiles[i]);
        }
    }
    
    try {
        // Send file to backend for processing
        const response = await fetch('/process_case_file', {
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
    
    // Show processing status
    uploadStatus.classList.remove('hidden');
    processingMessage.textContent = 'Traitement des données en cours...';
    extractionResults.innerHTML = '';
    
    // Create FormData from manual form
    const formData = new FormData(manualEntryForm);
    
    // Validate case number
    const caseNumber = formData.get('case_number');
    if (!caseNumber || caseNumber.trim() === '') {
        processingMessage.textContent = "Erreur: Le numéro du cas est obligatoire";
        return;
    }
    
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
        // Send manual data to backend for processing
        const response = await fetch('/process_manual_case', {
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

// Function to save edited case data
function saveEditedCase(previewData) {
    // Collect all edited data from the form using the advanced function if available
    const editedData = collectEditedFormData ? collectEditedFormData() : {
        // Basic patient info
        patient_info: {
            name: document.getElementById('edit-patient-name')?.value || '',
            age: document.getElementById('edit-patient-age')?.value ? 
                 parseInt(document.getElementById('edit-patient-age').value) : null,
            gender: document.getElementById('edit-patient-gender')?.value || ''
        },
        symptoms: [],
        evaluation_checklist: [],
        diagnosis: document.getElementById('edit-diagnosis')?.value || '',
        consultation_time: parseInt(document.getElementById('edit-consultation-time')?.value) || 10,
        images: [],
        custom_sections: []
    };
    
    // Add case number and specialty if not already present
    if (!editedData.case_number) {
        editedData.case_number = previewData.case_number;
    }
    
    if (!editedData.specialty && previewData.specialty) {
        editedData.specialty = previewData.specialty;
    }
    
    // If using simple collection, collect and update image descriptions
    if (!collectEditedFormData) {
        const images = previewData.extracted_data.images || [];
        images.forEach((image, index) => {
            const descriptionInput = document.querySelector(`.image-description[data-index="${index}"]`);
            if (descriptionInput) {
                editedData.images.push({
                    ...image,
                    description: descriptionInput.value.trim() || image.description || 'Image médicale'
                });
            } else {
                editedData.images.push(image);
            }
        });
    }
    
    // Send the edited data to the backend
    fetch('/save_edited_case', {
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
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            processingMessage.textContent = `Erreur: ${data.error}`;
        } else {
            processingMessage.textContent = 'Cas enregistré avec succès!';
            extractionResults.innerHTML = '';
            uploadForm.reset();
            
            // Refresh the page after 2 seconds to show updated case list
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        processingMessage.textContent = `Une erreur est survenue lors de l'enregistrement: ${error.message}`;
    });
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

// Event delegation for all dynamic elements
document.addEventListener('click', function(event) {
    // View case details
    if (event.target.classList.contains('view-button')) {
        const caseNumber = event.target.getAttribute('data-case');
        
        // Validate case number
        if (!caseNumber || caseNumber === 'None' || caseNumber === 'null') {
            alert("Erreur: Numéro de cas invalide");
            return;
        }
        
        try {
            fetch(`/get_case/${caseNumber}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    // Format and display case details in modal
                    let detailsHTML = '';
                    
                    // Basic information
                    detailsHTML += `<div class="case-details-section">
                        <h4>Informations générales</h4>
                        <p><strong>Numéro de cas:</strong> ${data.case_number}</p>
                        <p><strong>Spécialité:</strong> ${data.specialty || 'Non spécifiée'}</p>
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
                    
                    //  DIRECTIVES SECTION 
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
                                <img src="${image.path}" alt="${image.description || 'Image médicale'}" class="case-image" onclick="previewImageLarge('${image.path}')">
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
                });
        } catch (error) {
            console.error('Error:', error);
            alert(`Erreur lors de la récupération des détails du cas: ${error.message}`);
        }
    }
        // Delete case
        if (event.target.classList.contains('delete-button')) {
            const caseNumber = event.target.getAttribute('data-case');
            
            // Validate case number
            if (!caseNumber || caseNumber === 'None' || caseNumber === 'null') {
                alert("Erreur: Impossible de supprimer un cas sans numéro valide");
                return;
            }
            
            if (confirm(`Êtes-vous sûr de vouloir supprimer le cas ${caseNumber} ? Cette action est irréversible.`)) {
                try {
                    fetch(`/delete_case/${caseNumber}`, {
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
        
        // Remove symptom and checklist item event delegation
        if (event.target.classList.contains('remove-btn')) {
            const parent = event.target.closest('.symptom-entry, .checklist-item, .custom-section');
            if (parent) {
                parent.remove();
            }
        }
        
        // ---- HANDLERS FOR ENHANCED EDITING ----
        
        // Add custom patient field
        if (event.target.id === 'add-patient-field') {
            const container = event.target.closest('.preview-section');
            
            // Create field name input
            const fieldNameDiv = document.createElement('div');
            fieldNameDiv.className = 'edit-field custom-field';
            fieldNameDiv.innerHTML = `
                <label>Nom du champ:</label>
                <input type="text" class="custom-field-name" placeholder="Ex: Antécédents familiaux">
                <label>Valeur:</label>
                <input type="text" class="custom-field-value">
                <button type="button" class="remove-custom-field">×</button>
            `;
            
            // Insert before the Add button
            container.insertBefore(fieldNameDiv, event.target.parentNode);
            
            // Trigger validation
            if (validateEditedForm) validateEditedForm();
        }
        
        // Remove custom field
        if (event.target.classList.contains('remove-custom-field')) {
            const fieldDiv = event.target.closest('.custom-field');
            if (fieldDiv) {
                fieldDiv.remove();
                if (validateEditedForm) validateEditedForm();
            }
        }
        
        // Add symptom
        if (event.target.id === 'add-symptom-btn') {
            const container = document.getElementById('edit-symptoms-container');
            
            const symptomDiv = document.createElement('div');
            symptomDiv.className = 'edit-symptom';
            symptomDiv.innerHTML = `
                <input type="text" class="symptom-input" value="">
                <button type="button" class="remove-symptom">×</button>
            `;
            
            container.appendChild(symptomDiv);
            
            // Add event listener for validation
            symptomDiv.querySelector('.symptom-input').addEventListener('input', function() {
                if (validateEditedForm) validateEditedForm();
            });
            
            // Trigger validation
            if (validateEditedForm) validateEditedForm();
        }
        
        // Remove symptom
        if (event.target.classList.contains('remove-symptom')) {
            const symptomDiv = event.target.closest('.edit-symptom');
            if (symptomDiv) {
                symptomDiv.remove();
                if (validateEditedForm) validateEditedForm();
            }
        }
        
        // Add symptom category
        if (event.target.id === 'add-symptom-category') {
            const container = document.getElementById('edit-symptoms-container');
            
            const categoryDiv = document.createElement('div');
            categoryDiv.className = 'symptom-category';
            categoryDiv.innerHTML = `
                <div class="category-header">
                    <input type="text" class="category-name" placeholder="Nom de la catégorie">
                    <button type="button" class="remove-category">×</button>
                </div>
                <div class="category-symptoms"></div>
                <button type="button" class="add-category-symptom secondary-button">+ Ajouter un symptôme à cette catégorie</button>
            `;
            
            container.appendChild(categoryDiv);
            
            // Add event listener for category name changes
            categoryDiv.querySelector('.category-name').addEventListener('input', function() {
                if (validateEditedForm) validateEditedForm();
            });
        }
        
        // Add symptom to category
        if (event.target.classList.contains('add-category-symptom')) {
            const categoryContainer = event.target.previousElementSibling; // The category-symptoms div
            
            const symptomDiv = document.createElement('div');
            symptomDiv.className = 'edit-symptom';
            symptomDiv.innerHTML = `
                <input type="text" class="symptom-input" value="">
                <button type="button" class="remove-symptom">×</button>
            `;
            
            categoryContainer.appendChild(symptomDiv);
            
            // Add event listener for validation
            symptomDiv.querySelector('.symptom-input').addEventListener('input', function() {
                if (validateEditedForm) validateEditedForm();
            });
            
            // Trigger validation
            if (validateEditedForm) validateEditedForm();
        }
        
        // Add checklist item
        if (event.target.id === 'add-checklist-btn') {
            const container = document.getElementById('edit-checklist-container');
            
            const itemDiv = document.createElement('div');
            itemDiv.className = 'edit-checklist-item';
            itemDiv.innerHTML = `
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
                <button type="button" class="remove-checklist-item">×</button>
            `;
            
            container.appendChild(itemDiv);
            
            // Add event listener for validation
            itemDiv.querySelector('.checklist-description').addEventListener('input', function() {
                if (validateEditedForm) validateEditedForm();
            });
            
            // Trigger validation
            if (validateEditedForm) validateEditedForm();
        }
        
        // Remove checklist item
        if (event.target.classList.contains('remove-checklist-item')) {
            const itemDiv = event.target.closest('.edit-checklist-item');
            if (itemDiv) {
                itemDiv.remove();
                if (validateEditedForm) validateEditedForm();
            }
        }
        
        // Add checklist category
        if (event.target.id === 'add-checklist-category') {
            const container = document.getElementById('edit-checklist-container');
            
            const categoryDiv = document.createElement('div');
            categoryDiv.className = 'checklist-category';
            categoryDiv.innerHTML = `
                <div class="category-header">
                    <input type="text" class="category-name" placeholder="Nom de la catégorie (ex: Anamnèse)">
                    <button type="button" class="remove-category">×</button>
                </div>
                <div class="category-items"></div>
                <button type="button" class="add-category-item secondary-button">+ Ajouter un élément à cette catégorie</button>
            `;
            
            container.appendChild(categoryDiv);
        }
        
        // Add item to checklist category
        if (event.target.classList.contains('add-category-item')) {
            const categoryContainer = event.target.previousElementSibling; // The category-items div
            
            const itemDiv = document.createElement('div');
            itemDiv.className = 'edit-checklist-item';
            itemDiv.innerHTML = `
                <div class="edit-field-group">
                    <label>Description:</label>
                    <input type="text" class="checklist-description" value="">
                </div>
                <div class="edit-field-group small">
                    <label>Points:</label>
                    <input type="number" class="checklist-points" value="1" min="1">
                </div>
                <button type="button" class="remove-checklist-item">×</button>
            `;
            
            categoryContainer.appendChild(itemDiv);
            
            // Add event listener for validation
            itemDiv.querySelector('.checklist-description').addEventListener('input', function() {
                if (validateEditedForm) validateEditedForm();
            });
            
            // Trigger validation
            if (validateEditedForm) validateEditedForm();
        }
        
        // Remove category
        if (event.target.classList.contains('remove-category')) {
            const categoryDiv = event.target.closest('.symptom-category, .checklist-category');
            if (categoryDiv) {
                categoryDiv.remove();
                if (validateEditedForm) validateEditedForm();
            }
        }
        
        // Add medical history item
        if (event.target.id === 'add-medical-history-btn') {
            const container = document.getElementById('edit-medical-history-container');
            
            const historyDiv = document.createElement('div');
            historyDiv.className = 'edit-medical-history';
            historyDiv.innerHTML = `
                <input type="text" class="medical-history-input" value="">
                <button type="button" class="remove-medical-history">×</button>
            `;
            
            container.appendChild(historyDiv);
        }
        
        // Remove medical history item
        if (event.target.classList.contains('remove-medical-history')) {
            const historyDiv = event.target.closest('.edit-medical-history');
            if (historyDiv) {
                historyDiv.remove();
            }
        }
        
        // Add differential diagnosis
        if (event.target.id === 'add-differential-btn') {
            const container = document.getElementById('edit-differential-container');
            
            const diffDiv = document.createElement('div');
            diffDiv.className = 'edit-differential';
            diffDiv.innerHTML = `
                <input type="text" class="differential-input" value="">
                <button type="button" class="remove-differential">×</button>
            `;
            
            container.appendChild(diffDiv);
        }
        
        // Remove differential diagnosis
        if (event.target.classList.contains('remove-differential')) {
            const diffDiv = event.target.closest('.edit-differential');
            if (diffDiv) {
                diffDiv.remove();
            }
        }
        
        // Add custom section in preview
        if (event.target.id === 'add-preview-custom-section') {
            const container = document.getElementById('edit-custom-sections-container');
            
            const sectionDiv = document.createElement('div');
            sectionDiv.className = 'edit-custom-section';
            sectionDiv.innerHTML = `
                <div class="edit-field">
                    <label>Titre:</label>
                    <input type="text" class="custom-section-title" value="">
                </div>
                <div class="edit-field">
                    <label>Contenu:</label>
                    <textarea class="custom-section-content" rows="4"></textarea>
                </div>
                <button type="button" class="remove-custom-section">×</button>
            `;
            
            container.appendChild(sectionDiv);
        }
        
        // Remove custom section in preview
        if (event.target.classList.contains('remove-custom-section')) {
            const sectionDiv = event.target.closest('.edit-custom-section');
            if (sectionDiv) {
                sectionDiv.remove();
            }
        }
        
        // Delete image button handler
        if (event.target.classList.contains('delete-image-btn')) {
            const imageId = event.target.dataset.id;
            if (imageId) {
                deleteUploadedImage(imageId);
            }
        }
    });