// Configuration
const API_BASE_URL = 'http://localhost:8000';

// State
const state = {
    documents: [],
    messages: [],
    isUploading: false,
    isProcessing: false,
    isQuerying: false,
};

// DOM Elements
const elements = {
    uploadArea: document.getElementById('uploadArea'),
    fileInput: document.getElementById('fileInput'),
    uploadProgress: document.getElementById('uploadProgress'),
    progressFill: document.getElementById('progressFill'),
    progressText: document.getElementById('progressText'),
    uploadStatus: document.getElementById('uploadStatus'),
    documentsList: document.getElementById('documentsList'),
    documentsContainer: document.getElementById('documentsContainer'),
    chatMessages: document.getElementById('chatMessages'),
    queryInput: document.getElementById('queryInput'),
    sendButton: document.getElementById('sendButton'),
};

// Initialize App
function init() {
    setupEventListeners();
    console.log('RAG Chatbot initialized');
}

// Event Listeners Setup
function setupEventListeners() {
    // File input
    elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    elements.uploadArea.addEventListener('dragover', handleDragOver);
    elements.uploadArea.addEventListener('dragleave', handleDragLeave);
    elements.uploadArea.addEventListener('drop', handleDrop);

    // Send button
    elements.sendButton.addEventListener('click', handleSendQuery);

    // Enter key to send (Shift+Enter for new line)
    elements.queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendQuery();
        }
    });

    // Auto-resize textarea
    elements.queryInput.addEventListener('input', () => {
        elements.queryInput.style.height = 'auto';
        elements.queryInput.style.height = elements.queryInput.scrollHeight + 'px';
    });
}

// Drag and Drop Handlers
function handleDragOver(e) {
    e.preventDefault();
    elements.uploadArea.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    elements.uploadArea.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    elements.uploadArea.classList.remove('drag-over');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

// File Upload
async function handleFile(file) {
    // Validate file
    const maxSize = 10 * 1024 * 1024; // 10MB
    const allowedTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];

    if (file.size > maxSize) {
        showUploadStatus('error', 'File size exceeds 10MB limit');
        return;
    }

    if (!allowedTypes.includes(file.type) && !file.name.match(/\.(pdf|docx|txt)$/i)) {
        showUploadStatus('error', 'Invalid file type. Please upload PDF, DOCX, or TXT files');
        return;
    }

    // Upload and process
    try {
        state.isUploading = true;
        showUploadProgress(true);

        // Step 1: Upload document
        const uploadResult = await uploadDocument(file);
        updateProgress(50, 'Processing document...');

        // Step 2: Process document
        const processResult = await processDocument(uploadResult.document_id, file);
        updateProgress(100, 'Complete!');

        // Update state
        state.documents.push({
            id: uploadResult.document_id,
            name: file.name,
            status: 'processed',
        });

        // Update UI
        showUploadProgress(false);
        showUploadStatus('success', `Successfully uploaded and processed "${file.name}"`);
        updateDocumentsList();
        enableChat();

    } catch (error) {
        console.error('Upload/process error:', error);
        showUploadProgress(false);
        showUploadStatus('error', error.message || 'Failed to upload document');
    } finally {
        state.isUploading = false;
        elements.fileInput.value = '';
    }
}

async function uploadDocument(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
    }

    return await response.json();
}

async function processDocument(documentId, file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/api/documents/${documentId}/process`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Processing failed');
    }

    return await response.json();
}

// Query Handling
async function handleSendQuery() {
    const query = elements.queryInput.value.trim();

    if (!query || state.isQuerying) {
        return;
    }

    // Add user message
    addMessage('user', query);
    elements.queryInput.value = '';
    elements.queryInput.style.height = 'auto';

    // Show loading
    const loadingId = showLoading();

    try {
        state.isQuerying = true;
        elements.sendButton.disabled = true;

        // Call API
        const response = await fetch(`${API_BASE_URL}/api/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                top_k: 5,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Query failed');
        }

        const result = await response.json();

        // Remove loading
        removeLoading(loadingId);

        // Add assistant message
        addMessage('assistant', result.answer, result.sources, result.metadata);

    } catch (error) {
        console.error('Query error:', error);
        removeLoading(loadingId);
        addMessage('assistant', `Sorry, I encountered an error: ${error.message}`);
    } finally {
        state.isQuerying = false;
        elements.sendButton.disabled = false;
    }
}

// UI Updates
function showUploadProgress(show) {
    elements.uploadProgress.classList.toggle('hidden', !show);
    if (show) {
        updateProgress(0, 'Uploading...');
    }
}

function updateProgress(percent, text) {
    elements.progressFill.style.width = `${percent}%`;
    elements.progressText.textContent = text;
}

function showUploadStatus(type, message) {
    elements.uploadStatus.textContent = message;
    elements.uploadStatus.className = `upload-status ${type}`;
    elements.uploadStatus.classList.remove('hidden');

    // Auto-hide success messages
    if (type === 'success') {
        setTimeout(() => {
            elements.uploadStatus.classList.add('hidden');
        }, 5000);
    }
}

function updateDocumentsList() {
    if (state.documents.length === 0) {
        elements.documentsList.classList.add('hidden');
        return;
    }

    elements.documentsList.classList.remove('hidden');
    elements.documentsContainer.innerHTML = state.documents.map(doc => `
        <div class="document-item">
            <svg class="document-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span class="document-name">${escapeHtml(doc.name)}</span>
            <span class="document-status">✓ Processed</span>
        </div>
    `).join('');
}

function enableChat() {
    elements.queryInput.disabled = false;
    elements.sendButton.disabled = false;

    // Clear welcome message if it exists
    const welcomeMessage = elements.chatMessages.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }
}

function addMessage(role, content, sources = [], metadata = {}) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.textContent = content;
    contentDiv.appendChild(textDiv);

    // Add sources for assistant messages
    if (role === 'assistant' && sources && sources.length > 0) {
        const sourcesDiv = createSourcesSection(sources);
        contentDiv.appendChild(sourcesDiv);
    }

    messageDiv.appendChild(contentDiv);
    elements.chatMessages.appendChild(messageDiv);

    // Scroll to bottom
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

    // Store in state
    state.messages.push({ role, content, sources, metadata });
}

function createSourcesSection(sources) {
    const sourcesDiv = document.createElement('div');
    sourcesDiv.className = 'sources';

    const header = document.createElement('div');
    header.className = 'sources-header';
    header.textContent = `Sources (${sources.length})`;
    sourcesDiv.appendChild(header);

    sources.forEach((source, index) => {
        const sourceItem = createSourceItem(source);
        sourcesDiv.appendChild(sourceItem);
    });

    return sourcesDiv;
}

function createSourceItem(source) {
    const item = document.createElement('div');
    item.className = 'source-item';

    // Header
    const header = document.createElement('div');
    header.className = 'source-header';

    const title = document.createElement('div');
    title.className = 'source-title';
    title.innerHTML = `
        <span class="citation-badge">${source.citation_num}</span>
        <span>${escapeHtml(source.document_name)} (chunk ${source.chunk_index})</span>
    `;

    const chevron = document.createElement('svg');
    chevron.className = 'source-chevron';
    chevron.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />';
    chevron.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    chevron.setAttribute('fill', 'none');
    chevron.setAttribute('viewBox', '0 0 24 24');
    chevron.setAttribute('stroke', 'currentColor');

    header.appendChild(title);
    header.appendChild(chevron);

    // Content (collapsed by default)
    const content = document.createElement('div');
    content.className = 'source-content';

    const text = document.createElement('div');
    text.className = 'source-text';
    text.textContent = source.content;
    content.appendChild(text);

    // Scores
    const scores = document.createElement('div');
    scores.className = 'source-scores';

    if (source.rerank_score !== null && source.rerank_score !== undefined) {
        scores.innerHTML += `
            <div class="score-item">
                <span class="score-label">Rerank</span>
                <span class="score-value">${source.rerank_score.toFixed(3)}</span>
            </div>
        `;
    }

    if (source.rrf_score !== null && source.rrf_score !== undefined) {
        scores.innerHTML += `
            <div class="score-item">
                <span class="score-label">RRF</span>
                <span class="score-value">${source.rrf_score.toFixed(4)}</span>
            </div>
        `;
    }

    content.appendChild(scores);

    // Toggle functionality
    header.addEventListener('click', () => {
        const isExpanded = header.classList.contains('expanded');
        header.classList.toggle('expanded');
        content.classList.toggle('expanded');
    });

    item.appendChild(header);
    item.appendChild(content);

    return item;
}

function showLoading() {
    const loadingDiv = document.createElement('div');
    const loadingId = `loading-${Date.now()}`;
    loadingDiv.id = loadingId;
    loadingDiv.className = 'message message-assistant';
    loadingDiv.innerHTML = `
        <div class="message-content">
            <div class="loading">
                <div class="loading-spinner"></div>
                <span>Thinking...</span>
            </div>
        </div>
    `;

    elements.chatMessages.appendChild(loadingDiv);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

    return loadingId;
}

function removeLoading(loadingId) {
    const loadingDiv = document.getElementById(loadingId);
    if (loadingDiv) {
        loadingDiv.remove();
    }
}

// Utility Functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
