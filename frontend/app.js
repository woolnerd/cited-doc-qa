// Configuration
// Use empty string for production (relative URLs) or localhost for development
const API_BASE_URL =
  window.location.hostname === "localhost" ? "http://localhost:8000" : "";

// Session Management
// Generate or retrieve session ID from localStorage
function getSessionId() {
  let sessionId = localStorage.getItem("rag_session_id");
  if (!sessionId) {
    sessionId =
      "session_" +
      Date.now() +
      "_" +
      Math.random().toString(36).substr(2, 9);
    localStorage.setItem("rag_session_id", sessionId);
  }
  return sessionId;
}

const SESSION_ID = getSessionId();

// State
const state = {
  documents: [],
  messages: [],
  conversationHistory: [], // Store conversation for context
  isUploading: false,
  isProcessing: false,
  isQuerying: false,
  isLoadingDocuments: false,
  sessionId: SESSION_ID,
};

// DOM Elements
const elements = {
  uploadArea: document.getElementById("uploadArea"),
  fileInput: document.getElementById("fileInput"),
  uploadProgress: document.getElementById("uploadProgress"),
  progressFill: document.getElementById("progressFill"),
  progressText: document.getElementById("progressText"),
  uploadStatus: document.getElementById("uploadStatus"),
  documentsList: document.getElementById("documentsList"),
  documentsContainer: document.getElementById("documentsContainer"),
  chatMessages: document.getElementById("chatMessages"),
  queryInput: document.getElementById("queryInput"),
  sendButton: document.getElementById("sendButton"),
  newConversationButton: document.getElementById("newConversationButton"),
};

// Initialize App
function init() {
  setupEventListeners();
  loadDocuments();
  console.log("Operational Knowledge Hub initialized");
}

// Event Listeners Setup
function setupEventListeners() {
  // File input
  elements.uploadArea.addEventListener("click", () =>
    elements.fileInput.click()
  );
  elements.fileInput.addEventListener("change", handleFileSelect);

  // Drag and drop
  elements.uploadArea.addEventListener("dragover", handleDragOver);
  elements.uploadArea.addEventListener("dragleave", handleDragLeave);
  elements.uploadArea.addEventListener("drop", handleDrop);

  // Send button
  elements.sendButton.addEventListener("click", handleSendQuery);

  // Enter key to send (Shift+Enter for new line)
  elements.queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendQuery();
    }
  });

  // Auto-resize textarea
  elements.queryInput.addEventListener("input", () => {
    elements.queryInput.style.height = "auto";
    elements.queryInput.style.height = elements.queryInput.scrollHeight + "px";
  });

  // New conversation button
  elements.newConversationButton.addEventListener("click", clearConversation);
}

// Drag and Drop Handlers
function handleDragOver(e) {
  e.preventDefault();
  elements.uploadArea.classList.add("drag-over");
}

function handleDragLeave(e) {
  e.preventDefault();
  elements.uploadArea.classList.remove("drag-over");
}

function handleDrop(e) {
  e.preventDefault();
  elements.uploadArea.classList.remove("drag-over");

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
  const allowedTypes = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
  ];

  if (file.size > maxSize) {
    showUploadStatus("error", "File size exceeds 10MB limit");
    return;
  }

  if (
    !allowedTypes.includes(file.type) &&
    !file.name.match(/\.(pdf|docx|txt)$/i)
  ) {
    showUploadStatus(
      "error",
      "Invalid file type. Please upload PDF, DOCX, or TXT files"
    );
    return;
  }

  // Upload and process
  try {
    state.isUploading = true;
    showUploadProgress(true);

    // Step 1: Upload document
    const uploadResult = await uploadDocument(file);
    updateProgress(50, "Processing document...");

    // Step 2: Process document
    await processDocument(uploadResult.document_id, file);
    updateProgress(100, "Complete!");

    // Add placeholder for new document while loading
    state.documents.unshift({
      id: uploadResult.document_id,
      filename: file.name,
      status: "loading",
      upload_date: new Date().toISOString(),
      chunk_count: 0,
    });
    updateDocumentsList();

    // Reload documents to get complete metadata
    await loadDocuments();

    // Update UI
    showUploadProgress(false);
    showUploadStatus(
      "success",
      `Successfully uploaded and processed "${file.name}"`
    );
    enableChat();
  } catch (error) {
    console.error("Upload/process error:", error);
    showUploadProgress(false);
    showUploadStatus("error", error.message || "Failed to upload document");
    // Reload documents to remove any failed uploads from the list
    await loadDocuments();
  } finally {
    state.isUploading = false;
    elements.fileInput.value = "";
  }
}

async function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", state.sessionId);

  const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Upload failed");
  }

  return await response.json();
}

async function processDocument(documentId, file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${API_BASE_URL}/api/documents/${documentId}/process`,
    {
      method: "POST",
      body: formData,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Processing failed");
  }

  return await response.json();
}

// Document Management
async function loadDocuments() {
  try {
    state.isLoadingDocuments = true;
    updateDocumentsList(); // Show loading state

    // Add timeout to prevent hanging
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000); // 10 second timeout

    const response = await fetch(
      `${API_BASE_URL}/api/documents?session_id=${state.sessionId}`,
      {
        signal: controller.signal,
      }
    );

    clearTimeout(timeout);

    if (!response.ok) {
      console.error("Failed to load documents");
      state.isLoadingDocuments = false;
      updateDocumentsList();
      return;
    }

    const data = await response.json();
    state.documents = data.documents;
    state.isLoadingDocuments = false;
    updateDocumentsList();

    // Enable chat if there are processed documents
    if (state.documents.some((doc) => doc.status === "ready")) {
      enableChat();
    }
  } catch (error) {
    console.error("Error loading documents:", error);
    state.isLoadingDocuments = false;
    updateDocumentsList();
  }
}

async function deleteDocument(documentId) {
  // Confirm deletion
  const doc = state.documents.find((d) => d.id === documentId);
  if (!doc) return;

  if (
    !confirm(
      `Delete "${doc.filename}"? This will permanently remove the document and all its chunks.`
    )
  ) {
    return;
  }

  try {
    const response = await fetch(
      `${API_BASE_URL}/api/documents/${documentId}?session_id=${state.sessionId}`,
      {
        method: "DELETE",
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Delete failed");
    }

    const result = await response.json();

    // Remove from state
    state.documents = state.documents.filter((d) => d.id !== documentId);

    // Update UI
    updateDocumentsList();

    // Show success message
    showUploadStatus(
      "success",
      `Deleted "${doc.filename}" (${result.chunks_deleted} chunks removed)`
    );
  } catch (error) {
    console.error("Delete error:", error);
    showUploadStatus("error", error.message || "Failed to delete document");
  }
}

// Query Handling
async function handleSendQuery() {
  const query = elements.queryInput.value.trim();

  if (!query || state.isQuerying) {
    return;
  }

  // Add user message
  addMessage("user", query);
  elements.queryInput.value = "";
  elements.queryInput.style.height = "auto";

  // Show loading
  const loadingId = showLoading();

  try {
    state.isQuerying = true;
    elements.sendButton.disabled = true;

    // Build conversation history (exclude current query, include previous messages)
    const conversationHistory =
      state.conversationHistory.length > 0 ? state.conversationHistory : null;

    // Call API
    const response = await fetch(`${API_BASE_URL}/api/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: state.sessionId,
        query: query,
        top_k: 5,
        conversation_history: conversationHistory,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Query failed");
    }

    const result = await response.json();

    // Remove loading
    removeLoading(loadingId);

    // Add assistant message
    addMessage("assistant", result.answer, result.sources, result.metadata);

    // Update conversation history for context
    state.conversationHistory.push({ role: "user", content: query });
    state.conversationHistory.push({
      role: "assistant",
      content: result.answer,
    });
  } catch (error) {
    console.error("Query error:", error);
    removeLoading(loadingId);
    const errorMessage = `Sorry, I encountered an error: ${error.message}`;
    addMessage("assistant", errorMessage);

    // Add error to conversation history to maintain context
    state.conversationHistory.push({ role: "user", content: query });
    state.conversationHistory.push({
      role: "assistant",
      content: errorMessage,
    });
  } finally {
    state.isQuerying = false;
    elements.sendButton.disabled = false;
  }
}

// UI Updates
function showUploadProgress(show) {
  elements.uploadProgress.classList.toggle("hidden", !show);
  if (show) {
    updateProgress(0, "Uploading...");
  }
}

function updateProgress(percent, text) {
  elements.progressFill.style.width = `${percent}%`;
  elements.progressText.textContent = text;
}

function showUploadStatus(type, message) {
  elements.uploadStatus.innerHTML = `
        <span>${message}</span>
        <button class="status-close" onclick="dismissUploadStatus()" aria-label="Dismiss">×</button>
    `;
  elements.uploadStatus.className = `upload-status ${type}`;
  elements.uploadStatus.classList.remove("hidden");

  // Auto-hide all messages after 15 seconds
  setTimeout(() => {
    elements.uploadStatus.classList.add("hidden");
  }, 15000);
}

function dismissUploadStatus() {
  elements.uploadStatus.classList.add("hidden");
}

function updateDocumentsList() {
  // Show loading spinner only if we have no documents yet (initial load)
  if (state.isLoadingDocuments && state.documents.length === 0) {
    elements.documentsList.classList.remove("hidden");
    elements.documentsContainer.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: var(--text-2);">
                <div class="spinner" style="margin: 0 auto 1rem;"></div>
                <p>Loading documents...</p>
            </div>
        `;
    return;
  }

  if (state.documents.length === 0) {
    elements.documentsList.classList.add("hidden");
    return;
  }

  elements.documentsList.classList.remove("hidden");
  elements.documentsContainer.innerHTML = state.documents
    .map((doc) => {
      const uploadDate = new Date(doc.upload_date).toLocaleDateString();

      // Show loading state for documents being loaded
      if (doc.status === "loading") {
        return `
            <div class="document-item">
                <svg class="document-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <div class="document-info">
                    <span class="document-name">${escapeHtml(
                      doc.filename
                    )}</span>
                    <span class="document-meta">Loading details...</span>
                </div>
                <span class="document-status status-loading">
                    <div class="loading-spinner"></div>
                </span>
            </div>
            `;
      }

      const statusIcon = doc.status === "ready" ? "✓" : "⏳";
      const statusText = doc.status === "ready" ? "Ready" : "Processing";

      return `
        <div class="document-item">
            <svg class="document-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <div class="document-info">
                <span class="document-name">${escapeHtml(doc.filename)}</span>
                <span class="document-meta">${uploadDate} • ${
        doc.chunk_count
      } chunks</span>
            </div>
            <span class="document-status status-${
              doc.status
            }">${statusIcon} ${statusText}</span>
            <button class="delete-button" onclick="deleteDocument('${
              doc.id
            }')" title="Delete document">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
            </button>
        </div>
        `;
    })
    .join("");
}

function enableChat() {
  elements.queryInput.disabled = false;
  elements.sendButton.disabled = false;

  // Replace welcome message with example questions
  const welcomeMessage =
    elements.chatMessages.querySelector(".welcome-message");
  if (welcomeMessage) {
    welcomeMessage.innerHTML = `
            <h2>Ready to answer your questions!</h2>
            <p style="margin-bottom: 1rem;">Try asking about your operational documents:</p>
            <div style="text-align: left; max-width: 560px; margin: 0 auto;">
                <p style="margin: 0.5rem 0; color: var(--text-2); font-size: 0.95rem;">
                    💬 "Which vendor contracts renew this quarter?"
                </p>
                <p style="margin: 0.5rem 0; color: var(--text-2); font-size: 0.95rem;">
                    💬 "How is overtime calculated?"
                </p>
                <p style="margin: 0.5rem 0; color: var(--text-2); font-size: 0.95rem;">
                    💬 "What does the refund policy say?"
                </p>
                <p style="margin: 0.5rem 0; color: var(--text-2); font-size: 0.95rem;">
                    💬 "Where are OSHA procedures documented?"
                </p>
                <p style="margin: 0.5rem 0; color: var(--text-2); font-size: 0.95rem;">
                    💬 "What knowledge should be documented from long-time employees?"
                </p>
            </div>
        `;
  }
}

function clearConversation() {
  // Clear messages from state
  state.messages = [];

  // Clear conversation history
  state.conversationHistory = [];

  // Clear chat UI
  elements.chatMessages.innerHTML = "";

  // Hide new conversation button
  elements.newConversationButton.classList.add("hidden");

  // Show success feedback
  showUploadStatus(
    "success",
    "Conversation cleared. Start a new conversation!"
  );
}

function addMessage(role, content, sources = [], metadata = {}) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `message message-${role}`;

  const contentDiv = document.createElement("div");
  contentDiv.className = "message-content";

  const textDiv = document.createElement("div");
  textDiv.className = "message-text";
  textDiv.textContent = content;
  contentDiv.appendChild(textDiv);

  // Add sources for assistant messages
  if (role === "assistant" && sources && sources.length > 0) {
    const sourcesDiv = createSourcesSection(sources);
    contentDiv.appendChild(sourcesDiv);
  }

  messageDiv.appendChild(contentDiv);
  elements.chatMessages.appendChild(messageDiv);

  // Scroll to bottom
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

  // Store in state
  state.messages.push({ role, content, sources, metadata });

  // Show new conversation button if there are messages
  if (state.messages.length > 0) {
    elements.newConversationButton.classList.remove("hidden");
  }
}

function createSourcesSection(sources) {
  const sourcesDiv = document.createElement("div");
  sourcesDiv.className = "sources";

  const header = document.createElement("div");
  header.className = "sources-header";
  header.textContent = `Sources (${sources.length})`;
  sourcesDiv.appendChild(header);

  sources.forEach((source) => {
    const sourceItem = createSourceItem(source);
    sourcesDiv.appendChild(sourceItem);
  });

  return sourcesDiv;
}

function createSourceItem(source) {
  const item = document.createElement("div");
  item.className = "source-item";

  // Header
  const header = document.createElement("div");
  header.className = "source-header";

  const title = document.createElement("div");
  title.className = "source-title";
  title.innerHTML = `
        <span class="citation-badge">${source.citation_num}</span>
        <span>${escapeHtml(source.document_name)} (chunk ${
    source.chunk_index
  })</span>
    `;

  const chevron = document.createElement("svg");
  chevron.className = "source-chevron";
  chevron.innerHTML =
    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />';
  chevron.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  chevron.setAttribute("fill", "none");
  chevron.setAttribute("viewBox", "0 0 24 24");
  chevron.setAttribute("stroke", "currentColor");

  header.appendChild(title);
  header.appendChild(chevron);

  // Content (collapsed by default)
  const content = document.createElement("div");
  content.className = "source-content";

  const text = document.createElement("div");
  text.className = "source-text";
  text.textContent = source.content;
  content.appendChild(text);

  // Scores
  const scores = document.createElement("div");
  scores.className = "source-scores";

  if (source.rerank_score !== null && source.rerank_score !== undefined) {
    scores.innerHTML += `
            <div class="score-item">
                <span class="score-label">Rerank</span>
                <span class="score-value">${source.rerank_score.toFixed(
                  3
                )}</span>
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
  header.addEventListener("click", () => {
    header.classList.toggle("expanded");
    content.classList.toggle("expanded");
  });

  item.appendChild(header);
  item.appendChild(content);

  return item;
}

function showLoading() {
  const loadingDiv = document.createElement("div");
  const loadingId = `loading-${Date.now()}`;
  loadingDiv.id = loadingId;
  loadingDiv.className = "message message-assistant";
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
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// Initialize on load
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
