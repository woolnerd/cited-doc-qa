# RAG Chatbot Frontend

A simple, modern chat interface for the RAG Chatbot system built with vanilla HTML, CSS, and JavaScript.

## Features

- **Drag-and-drop file upload** - Upload PDF, DOCX, or TXT files up to 10MB
- **Real-time progress indicators** - Visual feedback during upload and processing
- **Interactive chat interface** - Clean, responsive message history
- **Source citations** - Expandable source snippets with relevance scores
- **Mobile-friendly** - Responsive design that works on all devices
- **No build step required** - Pure vanilla JS, works directly in the browser

## Quick Start

### 1. Start the Backend

Make sure the FastAPI backend is running:

```bash
cd backend
source ../venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Serve the Frontend

**Option A: Using Python's built-in server (recommended)**

```bash
cd frontend
python3 serve.py
```

Then open http://localhost:3000 in your browser.

**Option B: Using Python's HTTP server directly**

```bash
cd frontend
python3 -m http.server 3000
```

**Option C: Using Node.js http-server**

```bash
cd frontend
npx http-server -p 3000 --cors
```

**Option D: Using VS Code Live Server**

Right-click on `index.html` and select "Open with Live Server"

## Usage

1. **Upload a Document**
   - Click the upload area or drag and drop a file
   - Supported formats: PDF, DOCX, TXT
   - Maximum size: 10MB
   - Wait for processing to complete

2. **Ask Questions**
   - Type your question in the input box
   - Press Enter or click Send
   - View the answer with cited sources

3. **View Sources**
   - Click on source items to expand and view the original text
   - See relevance scores (rerank score, RRF score)
   - Citations are numbered [1], [2], etc. in the answer

## API Configuration

The frontend connects to the backend at `http://localhost:8000` by default.

To change the API URL, edit `app.js`:

```javascript
const API_BASE_URL = 'http://localhost:8000';  // Change this
```

## Browser Compatibility

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## CORS Configuration

If you encounter CORS errors, ensure your backend has the frontend origin in the allowed origins list.

In `backend/app/core/config.py`:

```python
ALLOWED_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Add your frontend URLs here
]
```

## Development

No build tools or dependencies required! Just edit the files:

- `index.html` - Structure and layout
- `styles.css` - Styling and responsive design
- `app.js` - Application logic and API calls

The application uses modern JavaScript (ES6+) and CSS features. No frameworks or libraries needed.

## Architecture

### File Structure
```
frontend/
├── index.html     # Main HTML structure
├── styles.css     # All styling
├── app.js         # Application logic
├── serve.py       # Simple dev server
└── README.md      # This file
```

### Key Components

- **Upload Section** - File upload with drag-and-drop
- **Chat Section** - Message history with user/assistant messages
- **Sources Display** - Expandable citation cards with scores
- **Input Area** - Textarea with auto-resize and send button

### State Management

The app maintains simple state in memory:

```javascript
const state = {
    documents: [],    // Uploaded documents
    messages: [],     // Chat history
    isUploading: false,
    isProcessing: false,
    isQuerying: false,
};
```

### API Integration

The app communicates with three backend endpoints:

1. `POST /api/documents/upload` - Upload document metadata
2. `POST /api/documents/{id}/process` - Process and chunk document
3. `POST /api/query` - Query the RAG system

All requests use the Fetch API with proper error handling.

## Customization

### Colors

Edit CSS variables in `styles.css`:

```css
:root {
    --primary-color: #3b82f6;     /* Main theme color */
    --success-color: #10b981;     /* Success states */
    --error-color: #ef4444;       /* Error states */
    /* ... more variables */
}
```

### Features

To add custom features, extend the `app.js` functions:

- `addMessage()` - Customize message display
- `createSourceItem()` - Modify source cards
- `handleSendQuery()` - Add query preprocessing

## Troubleshooting

**Upload fails with 413 error**
- File is too large (> 10MB limit)
- Check backend MAX_FILE_SIZE setting

**CORS errors**
- Backend ALLOWED_ORIGINS doesn't include frontend URL
- Add your frontend URL to backend config

**Query times out**
- Check backend logs for errors
- Verify all API keys are configured (Gemini, Cohere, OpenRouter)

**Sources not displaying**
- Check browser console for JavaScript errors
- Verify API response format matches expected structure

## Performance

- **Upload**: Depends on file size and server processing
- **Query**: ~4-5 seconds for end-to-end RAG pipeline
  - Vector search: ~600ms
  - Full-text search: ~100ms
  - Reranking: ~500ms
  - LLM generation: ~3s

## Security Notes

- This is a development interface - add authentication for production
- API endpoints are not protected - implement auth middleware
- File uploads are not virus-scanned - add scanning in production
- CORS is open for development - restrict in production
