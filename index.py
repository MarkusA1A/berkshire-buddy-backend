#!/usr/bin/env python3
"""
Berkshire Buddy Backend - WSGI App for Vercel
"""

from http.server import BaseHTTPRequestHandler
import json
import re
from pathlib import Path
from urllib.parse import unquote
import urllib.request
import urllib.error

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

# ============= Letter URL Generation =============

def get_letter_url(year):
    """Generate correct URL for Berkshire shareholder letter based on year"""
    if not year:
        return None
    
    try:
        year_int = int(year)
    except (ValueError, TypeError):
        return None
    
    # URL structure changes by year
    if year_int <= 2005:
        # 1977-2005: {year}.html
        return f'https://www.berkshirehathaway.com/letters/{year}.html'
    else:
        # 2006+: {year}ltr.pdf
        return f'https://www.berkshirehathaway.com/letters/{year}ltr.pdf'

# ============= Ollama Integration =============

OLLAMA_BASE = 'http://localhost:11434'
OLLAMA_MODEL = 'mistral:latest'

def translate_to_german(text):
    """Translate text to German using Ollama"""
    try:
        request_data = json.dumps({
            'model': OLLAMA_MODEL,
            'prompt': f'Übersetze diesen englischen Text kurz ins Deutsche. Nur Übersetzung:\n\n{text}',
            'stream': False,
            'temperature': 0.5
        }).encode('utf-8')
        
        req = urllib.request.Request(
            f'{OLLAMA_BASE}/api/generate',
            data=request_data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode())
            return data.get('response', '').strip()
    except:
        return None

def synthesize_with_ollama(question, citations):
    """Call Ollama locally to synthesize an intelligent answer"""
    if not citations:
        return None
    
    try:
        # Format citations for context
        citation_text = '\n\n'.join([
            f"[{i+1}] \"{c['text']}\" ({c['source']}, {c.get('year', 'N/A')})"
            for i, c in enumerate(citations)
        ])
        
        system_prompt = f"""Du bist Berkshire Buddy, ein Investment Coach basierend auf der Weisheit von Warren Buffett und Charlie Munger.

Deine Aufgabe: Synthesisiere eine intelligente, prägnante Antwort aus den bereitgestellten Zitaten.

Anweisungen:
1. Antworte klar und direkt (2-4 Sätze max)
2. Referenziere Zitate als [1], [2], etc.
3. Erkläre das Prinzip, nicht nur zitiere
4. Sei praktisch und handlungsorientiert
5. Wenn unsicher, sei ehrlich
6. **Antworte IMMER auf Deutsch**

Zitate:
{citation_text}

Frage: {question}

Antwort:"""
        
        request_data = json.dumps({
            'model': OLLAMA_MODEL,
            'prompt': system_prompt,
            'stream': False,
            'temperature': 0.7
        }).encode('utf-8')
        
        req = urllib.request.Request(
            f'{OLLAMA_BASE}/api/generate',
            data=request_data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            return data.get('response', '').strip()
    
    except urllib.error.URLError:
        print("⚠ Ollama not available (localhost:11434)")
        return None
    except Exception as e:
        print(f"⚠ Ollama error: {e}")
        return None

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
    
    # Prioritize meetings over letters (they're more direct Q&A from Buffett/Munger)
    for r in unique_results:
        if 'Meeting' in r['source']:
            r['relevance'] = 1.5  # Meetings get higher priority than letters (1.0)
        else:
            r['relevance'] = 0.8  # Reduce letter priority slightly
    
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
    
    elif path == '/synthesis':
        """POST endpoint for AI synthesis of citations"""
        if method != 'POST':
            start_response('405 Method Not Allowed', headers)
            return [json.dumps({"error": "POST required"}).encode('utf-8')]
        
        try:
            content_length = int(environ.get('CONTENT_LENGTH', 0))
            body = environ['wsgi.input'].read(content_length).decode('utf-8')
            request_data = json.loads(body)
        except:
            start_response('400 Bad Request', headers)
            return [json.dumps({"error": "Invalid JSON"}).encode('utf-8')]
        
        question = request_data.get('question', '')
        citations = request_data.get('citations', [])
        
        if not question or not citations:
            start_response('400 Bad Request', headers)
            return [json.dumps({"error": "Need question and citations"}).encode('utf-8')]
        
        synthesis = synthesize_with_ollama(question, citations)
        
        # Add links + translate citations to German
        citations_with_links = []
        for c in citations:
            # Add link to original letter
            if c.get('year') and 'Letter' in c.get('source', ''):
                year = c['year']
                c['letter_url'] = f'https://www.berkshirehathaway.com/letters/{year}.html'
            
            # Translate citation text to German
            if c.get('text'):
                german_text = translate_to_german(c['text'])
                if german_text:
                    c['text_de'] = german_text  # Add German translation
            
            citations_with_links.append(c)
        
        # Translate question to German for display
        question_de = translate_to_german(question) if question else None
        
        response = {
            "question": question,
            "question_de": question_de,
            "synthesis": synthesis,
            "citations": citations_with_links,
            "has_answer": synthesis is not None
        }
        
        start_response('200 OK', headers)
        return [json.dumps(response, ensure_ascii=False).encode('utf-8')]
    
    elif path == '/search':
        query = params.get('q', '').strip()
        limit = int(params.get('limit', 3))
        
        if not query or len(query) < 2:
            start_response('400 Bad Request', headers)
            return [json.dumps({"error": "Query too short"}).encode('utf-8')]
        
        results = search_archives(query, limit=limit)
        
        # Add links to original Berkshire letters
        results_with_links = []
        for r in results:
            if r.get('year') and 'Letter' in r.get('source', ''):
                year = r['year']
                r['letter_url'] = f'https://www.berkshirehathaway.com/letters/{year}.html'
            results_with_links.append(r)
        
        response = {
            "query": query,
            "citations": results_with_links,
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
