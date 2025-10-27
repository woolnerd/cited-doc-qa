#!/usr/bin/env python3
"""Simple HTTP server for the RAG Chatbot frontend."""

import http.server
import socketserver
from pathlib import Path

PORT = 3000
DIRECTORY = Path(__file__).parent


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler with CORS headers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def end_headers(self):
        """Add CORS headers to all responses."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        """Handle preflight OPTIONS requests."""
        self.send_response(200)
        self.end_headers()


def main():
    """Start the HTTP server."""
    try:
        with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
            print("🚀 RAG Chatbot Frontend Server")
            print(f"📁 Serving: {DIRECTORY}")
            print(f"🌐 URL: http://localhost:{PORT}")
            print("✋ Press Ctrl+C to stop\n")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"❌ Port {PORT} is already in use")
            print(f"   Try: lsof -ti:{PORT} | xargs kill")
        else:
            raise


if __name__ == "__main__":
    main()
