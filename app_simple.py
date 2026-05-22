#!/usr/bin/env python3
"""
Berkshire Buddy Backend (Simple HTTP Server)
No external dependencies - pure Python
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import re
import urllib.parse
from pathlib import Path
import sys
import os

# ============= Data Loading =============

# Try relative path first (for GitHub deployment), then absolute fallback
BASE_DIR = Path(__file__).parent

ARCHIVE_PATHS = {
    "letters": BASE_DIR / "data" / "berkshire-letters-archive.json",
    "meetings": BASE_DIR / "data" / "berkshire-shareholder-meetings.json",
}

# Fallback to absolute path if relative doesn't exist (for development)
FALLBACK_PATHS = {
    "letters": Path("/Users/macmini/.openclaw/workspace/memory/berkshire-letters-archive.json"),
    "meetings": Path("/Users/macmini/.openclaw/workspace/memory/berkshire-shareholder-meetings.json"),
}

archives = {}

def load_archives():
    """Load both archives into memory"""
    global archives
    
    # Try relative path first, then fallback to absolute
    letter_path = ARCHIVE_PATHS["letters"] if ARCHIVE_PATHS["letters"].exists() else FALLBACK_PATHS["letters"]
    meeting_path = ARCHIVE_PATHS["meetings"] if ARCHIVE_PATHS["meetings"].exists() else FALLBACK_PATHS["meetings"]
    
    # Load Shareholder Letters (JSON)
    if letter_path.exists():
        try:
            with open(letter_path, "r", encoding="utf-8") as f:
                archives["letters"] = json.load(f)
            print(f"✓ Loaded {len(archives['letters'])} shareholder letters")
            print(f"  (from {letter_path})")
        except Exception as e:
            print(f"✗ Error loading letters: {e}")
            archives["letters"] = {}
    else:
        print(f"✗ Letters not found at {letter_path}")
        archives["letters"] = {}
    
    # Load Shareholder Meetings (JSON)
    if meeting_path.exists():
        try:
            with open(meeting_path, "r", encoding="utf-8") as f:
                meeting_data = json.load(f)
                # Convert JSON dict to combined text for searching
                archives["meetings"] = json.dumps(meeting_data, ensure_ascii=False)
                print(f"✓ Loaded {len(meeting_data)} shareholder meetings ({len(archives['meetings']) // 1024}KB)")
            print(f"  (from {meeting_path})")
        except Exception as e:
            print(f"✗ Error loading meetings: {e}")
            archives["meetings"] = ""
    else:
        print(f"✗ Meetings not found at {meeting_path}")
        archives["meetings"] = ""
    
    if not archives or (not archives.get("letters") and not archives.get("meetings")):
        print("\n⚠ WARNING: No archives loaded!")
        print("  Make sure data/ folder exists with:")
        print("  - berkshire-letters-archive.json")
        print("  - berkshire-shareholder-meetings.txt")

# Load on startup
load_archives()

# ============= Letter URL Mapping =============

letter_urls = {}

def load_letter_urls():
    """Load letter URL mapping from letter_urls.json"""
    global letter_urls
    
    url_config_path = BASE_DIR / "letter_urls.json"
    if url_config_path.exists():
        try:
            with open(url_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                letter_urls = config.get("mapping", {})
                print(f"✓ Loaded letter URL mapping ({len(letter_urls)} years)")
        except Exception as e:
            print(f"⚠ Error loading letter_urls.json: {e}")
    else:
        print(f"⚠ letter_urls.json not found at {url_config_path}")

load_letter_urls()

def get_letter_url(year):
    """Get correct URL for a Berkshire letter by year"""
    if not year:
        return None
    
    year_str = str(year)
    
    # Check mapping first (most accurate)
    if year_str in letter_urls:
        return letter_urls[year_str]
    
    # Fallback for early years (1977-1996, might not be in mapping)
    try:
        year_int = int(year_str)
        if year_int < 1997:
            return f'https://www.berkshirehathaway.com/letters/{year}.html'
    except (ValueError, TypeError):
        pass
    
    return None

# ============= Search Logic =============

def extract_context(text, match_pos, context_chars=200):
    """Extract context around a match"""
    start = max(0, match_pos - context_chars)
    end = min(len(text), match_pos + context_chars)
    return text[start:end].strip()

def extract_keywords(query):
    """Extract important keywords from query (skip common words)"""
    stopwords = {'what', 'shall', 'should', 'do', 'with', 'i', 'a', 'the', 'is', 'are', 'to', 'of', 'in', 'on', 'at', 'be', 'have', 'has', 'had'}
    words = query.lower().split()
    keywords = [w for w in words if len(w) > 2 and w not in stopwords]
    return keywords if keywords else [query.lower()]  # Fallback to full query if no keywords

def search_archives(query, limit=3):
    """Search in both archives by keywords"""
    results = []
    query_lower = query.lower()
    keywords = extract_keywords(query)
    
    # Search letters
    for year, content in archives.get("letters", {}).items():
        content_lower = content.lower()
        
        # Find matches for ANY keyword
        matches = []
        for keyword in keywords:
            for i, match in enumerate(re.finditer(re.escape(keyword), content_lower)):
                if i >= 3:  # Max 3 matches per keyword per year
                    break
                pos = match.start()
                context = extract_context(content, pos)
                matches.append({
                    "text": context,
                    "source": f"Shareholder Letter {year}",
                    "year": year,
                    "relevance": 1.0,
                    "match_pos": pos
                })
        
        results.extend(matches)
    
    # Search meetings
    content = archives.get("meetings", "")
    content_lower = content.lower()
    
    matches = []
    for keyword in keywords:
        for i, match in enumerate(re.finditer(re.escape(keyword), content_lower)):
            if i >= 3:  # Max 3 matches per keyword
                break
            pos = match.start()
            context = extract_context(content, pos)
            
            # Try to extract year
            year_match = re.search(r'\b(19|20)\d{2}\b', context)
            year = year_match.group(0) if year_match else None
            
            matches.append({
                "text": context,
                "source": "Shareholder Meeting",
                "year": year,
                "relevance": 0.95,
                "match_pos": pos
            })
    
    results.extend(matches)
    
    # Sort by relevance, then by match position
    results = sorted(
        results,
        key=lambda x: (x["relevance"], -x["match_pos"]),
        reverse=True
    )[:limit]
    
    # Add letter URLs for letter sources
    for r in results:
        if "Letter" in r.get("source", "") and r.get("year"):
            letter_url = get_letter_url(r["year"])
            if letter_url:
                r["letter_url"] = letter_url
    
    # Clean up internal fields
    for r in results:
        del r["match_pos"]
    
    return results

# ============= HTTP Handler =============

class BerkshireHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        """Handle GET requests"""
        
        # Parse URL
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # CORS headers
        cors_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        }
        
        # Routes
        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            for k, v in cors_headers.items():
                self.send_header(k, v)
            self.end_headers()
            
            response = {
                "name": "Berkshire Buddy API",
                "version": "1.0.0",
                "endpoints": {
                    "GET /search?q=...&limit=3": "Search archives",
                    "GET /health": "Health check",
                    "GET /stats": "Archive statistics"
                }
            }
            self.wfile.write(json.dumps(response).encode())
        
        elif path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            for k, v in cors_headers.items():
                self.send_header(k, v)
            self.end_headers()
            
            response = {
                "status": "ok",
                "archives_loaded": {
                    "letters": len(archives.get("letters", {})),
                    "meetings_chars": len(archives.get("meetings", ""))
                }
            }
            self.wfile.write(json.dumps(response).encode())
        
        elif path == "/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            for k, v in cors_headers.items():
                self.send_header(k, v)
            self.end_headers()
            
            letters = archives.get("letters", {})
            years = sorted(letters.keys()) if letters else []
            
            response = {
                "letters": {
                    "count": len(letters),
                    "year_range": f"{years[0]}–{years[-1]}" if years else "N/A",
                    "total_chars": sum(len(v) for v in letters.values())
                },
                "meetings": {
                    "total_chars": len(archives.get("meetings", ""))
                }
            }
            self.wfile.write(json.dumps(response).encode())
        
        elif path == "/search":
            query = query_params.get("q", [""])[0]
            limit = int(query_params.get("limit", ["3"])[0])
            
            if not query or len(query) < 2:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                for k, v in cors_headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Query too short"}).encode())
                return
            
            results = search_archives(query, limit=limit)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            for k, v in cors_headers.items():
                self.send_header(k, v)
            self.end_headers()
            
            response = {
                "query": query,
                "citations": results,
                "message": f"Found {len(results)} citations" if results else "No results found"
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            for k, v in cors_headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Not found"}).encode())
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

# ============= Main =============

if __name__ == "__main__":
    import os
    PORT = int(os.getenv("PORT", 8000))
    HOST = "0.0.0.0"
    
    print("\n" + "="*50)
    print("Berkshire Buddy API Starting...")
    print("="*50)
    
    server = HTTPServer((HOST, PORT), BerkshireHandler)
    print(f"\n✅ Server running at http://{HOST}:{PORT}")
    print(f"📊 Stats: http://{HOST}:{PORT}/stats")
    print(f"🔍 Test: http://{HOST}:{PORT}/search?q=value+investing")
    print("="*50 + "\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹ Server stopped")
        sys.exit(0)
