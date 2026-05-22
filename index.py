#!/usr/bin/env python3
"""
Berkshire Buddy Backend - WSGI App for Vercel
"""

from http.server import BaseHTTPRequestHandler
import json
import re
from pathlib import Path
from urllib.parse import unquote

# ============= Data Loading =============

BASE_DIR = Path(__file__).parent
ARCHIVE_PATHS = {
    "letters": BASE_DIR / "data" / "berkshire-letters-archive.json",
    "meetings": BASE_DIR / "data" / "berkshire-shareholder-meetings.txt",
}

archives = {}

def load_archives():
    """Load both archives into memory"""
    global archives
    
    print(f"DEBUG: BASE_DIR = {BASE_DIR}")
    print(f"DEBUG: Looking for letters at: {ARCHIVE_PATHS['letters']}")
    print(f"DEBUG: File exists: {ARCHIVE_PATHS['letters'].exists()}")
    
    # Load Shareholder Letters (JSON)
    if ARCHIVE_PATHS["letters"].exists():
        try:
            with open(ARCHIVE_PATHS["letters"], "r", encoding="utf-8") as f:
                archives["letters"] = json.load(f)
            print(f"✓ Loaded {len(archives['letters'])} shareholder letters")
        except Exception as e:
            print(f"✗ Error loading letters: {e}")
            archives["letters"] = {}
    else:
        print(f"✗ Letters not found at {ARCHIVE_PATHS['letters']}")
        archives["letters"] = {}
    
    # Load Shareholder Meetings (TXT)
    if ARCHIVE_PATHS["meetings"].exists():
        try:
            with open(ARCHIVE_PATHS["meetings"], "r", encoding="utf-8") as f:
                archives["meetings"] = f.read()
            print(f"✓ Loaded shareholder meetings ({len(archives['meetings']) // 1000}KB)")
        except Exception as e:
            print(f"✗ Error loading meetings: {e}")
            archives["meetings"] = ""
    else:
        print(f"✗ Meetings not found at {ARCHIVE_PATHS['meetings']}")
        archives["meetings"] = ""

# Load on startup
load_archives()

# ============= Search Logic =============

def search_archives(query, limit=3):
    """Search in both archives"""
    results = []
    query_lower = query.lower().strip('?!.,;:')
    
    # Split query into keywords and search for any of them
    keywords = [w for w in query_lower.split() if len(w) > 2]
    if not keywords:
        keywords = [query_lower]
    
    # Search letters
    for year, content in archives.get("letters", {}).items():
        content_lower = content.lower()
        
        # Find first 5 matches per year for each keyword
        matches = []
        for keyword in keywords:
            for i, match in enumerate(re.finditer(re.escape(keyword), content_lower)):
                if i >= 3:
                    break
                pos = match.start()
                # Extract context
                start = max(0, pos - 200)
                end = min(len(content), pos + 200)
                context = content[start:end].strip()
                
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
            if i >= 3:
                break
            pos = match.start()
            # Extract context
            start = max(0, pos - 200)
            end = min(len(content), pos + 200)
            context = content[start:end].strip()
            
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
    
    # Deduplicate by text
    seen = set()
    unique_results = []
    for r in results:
        if r['text'] not in seen:
            seen.add(r['text'])
            unique_results.append(r)
    
    # Sort by relevance, then by match position
    unique_results = sorted(
        unique_results,
        key=lambda x: (x["relevance"], -x["match_pos"]),
        reverse=True
    )[:limit]
    
    # Clean up internal fields
    for r in unique_results:
        del r["match_pos"]
    
    return unique_results

# ============= WSGI Application =============

def application(environ, start_response):
    """WSGI application for Vercel"""
    
    path = environ.get('PATH_INFO', '/')
    query_string = environ.get('QUERY_STRING', '')
    method = environ.get('REQUEST_METHOD', 'GET')
    
    # Parse query params
    params = {}
    if query_string:
        for pair in query_string.split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                params[k] = unquote(v.replace('+', ' '))
    
    # CORS headers
    headers = [
        ('Access-Control-Allow-Origin', '*'),
        ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
        ('Access-Control-Allow-Headers', 'Content-Type'),
        ('Content-Type', 'application/json'),
    ]
    
    # Routes
    if method == 'OPTIONS':
        start_response('200 OK', headers)
        return [b'']
    
    elif path == '/':
        response = {
            "name": "Berkshire Buddy API",
            "version": "1.0.0",
            "endpoints": {
                "GET /search?q=...&limit=3": "Search archives",
                "GET /health": "Health check",
                "GET /stats": "Archive statistics"
            }
        }
        start_response('200 OK', headers)
        return [json.dumps(response).encode('utf-8')]
    
    elif path == '/health':
        response = {
            "status": "ok",
            "archives_loaded": {
                "letters": len(archives.get("letters", {})),
                "meetings_chars": len(archives.get("meetings", ""))
            }
        }
        start_response('200 OK', headers)
        return [json.dumps(response).encode('utf-8')]
    
    elif path == '/stats':
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
        start_response('200 OK', headers)
        return [json.dumps(response).encode('utf-8')]
    
    elif path == '/search':
        query = params.get('q', '').strip()
        limit = int(params.get('limit', 3))
        
        print(f"DEBUG: Query = '{query}'")
        print(f"DEBUG: Query length = {len(query)}")
        
        if not query or len(query) < 2:
            start_response('400 Bad Request', headers)
            return [json.dumps({"error": "Query too short"}).encode('utf-8')]
        
        results = search_archives(query, limit=limit)
        
        response = {
            "query": query,
            "citations": results,
            "message": f"Found {len(results)} citations" if results else "No results found"
        }
        start_response('200 OK', headers)
        return [json.dumps(response, ensure_ascii=False).encode('utf-8')]
    
    else:
        start_response('404 Not Found', headers)
        return [json.dumps({"error": "Not found"}).encode('utf-8')]

# For local testing
if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    
    print("\n" + "="*50)
    print("Berkshire Buddy API (WSGI)")
    print("="*50 + "\n")
    
    server = make_server('127.0.0.1', 8000, application)
    print("✅ Server running at http://localhost:8000")
    print("="*50 + "\n")
    server.serve_forever()
