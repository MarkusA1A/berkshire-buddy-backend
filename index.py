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

def extract_context_smart(text, match_pos, context_before=400, context_after=600):
    """Extract context, ensuring complete sentences"""
    # Get raw context window
    start = max(0, match_pos - context_before)
    end = min(len(text), match_pos + context_after)
    
    # Find sentence boundaries (. ! ?)
    # Move start to next sentence start
    sentence_markers = ['.', '!', '?']
    while start > 0 and text[start-1] not in sentence_markers:
        start -= 1
    # Skip the marker itself
    while start < len(text) and text[start] in sentence_markers + [' ', '\n']:
        start += 1
    
    # Move end to sentence end
    while end < len(text) and text[end] not in sentence_markers:
        end += 1
    # Include the marker
    if end < len(text) and text[end] in sentence_markers:
        end += 1
    
    context = text[start:end].strip()
    return context if context else text[max(0, match_pos-200):min(len(text), match_pos+200)].strip()

def search_archives(query, limit=3):
    """Search in both archives"""
    results = []
    query_lower = query.lower().strip('?!.,;:')
    
    # Try phrase search first, then keyword fallback
    phrase = query_lower
    keywords = [w for w in query_lower.split() if len(w) > 2]
    if not keywords:
        keywords = [query_lower]
    
    # Search letters
    for year, content in archives.get("letters", {}).items():
        content_lower = content.lower()
        
        # Try phrase first
        matches = []
        phrase_found = False
        for i, match in enumerate(re.finditer(re.escape(phrase), content_lower)):
            if i >= 2:  # Limit phrase matches
                break
            pos = match.start()
            context = extract_context_smart(content, pos)
            matches.append({
                "text": context,
                "source": f"Shareholder Letter {year}",
                "year": year,
                "relevance": 1.5,  # Boost phrase matches
                "match_pos": pos
            })
            phrase_found = True
        
        # If phrase didn't find much, try keywords
        if not phrase_found:
            for keyword in keywords:
                for i, match in enumerate(re.finditer(re.escape(keyword), content_lower)):
                    if i >= 2:
                        break
                    pos = match.start()
                    context = extract_context_smart(content, pos)
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
    # Try phrase first
    for i, match in enumerate(re.finditer(re.escape(phrase), content_lower)):
        if i >= 2:
            break
        pos = match.start()
        context = extract_context_smart(content, pos)
        year_match = re.search(r'\b(19|20)\d{2}\b', context)
        year = year_match.group(0) if year_match else None
        matches.append({
            "text": context,
            "source": "Shareholder Meeting",
            "year": year,
            "relevance": 1.45,
            "match_pos": pos
        })
    
    # Keyword fallback
    if not matches:
        for keyword in keywords:
            for i, match in enumerate(re.finditer(re.escape(keyword), content_lower)):
                if i >= 2:
                    break
                pos = match.start()
                context = extract_context_smart(content, pos)
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
