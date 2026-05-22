#!/usr/bin/env python3
"""
Berkshire Buddy Backend (Simple HTTP Server)
With OpenAI Integration for synthesis
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import re
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
import sys
import os

# ============= Data Loading =============

BASE_DIR = Path(__file__).parent

ARCHIVE_PATHS = {
    "letters": BASE_DIR / "data" / "berkshire-letters-archive.json",
    "meetings": BASE_DIR / "data" / "berkshire-shareholder-meetings.json",
}

FALLBACK_PATHS = {
    "letters": Path("/Users/macmini/.openclaw/workspace/memory/berkshire-letters-archive.json"),
    "meetings": Path("/Users/macmini/.openclaw/workspace/memory/berkshire-shareholder-meetings.json"),
}

archives = {}
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

def load_archives():
    """Load both archives into memory"""
    global archives
    
    letter_path = ARCHIVE_PATHS["letters"] if ARCHIVE_PATHS["letters"].exists() else FALLBACK_PATHS["letters"]
    meeting_path = ARCHIVE_PATHS["meetings"] if ARCHIVE_PATHS["meetings"].exists() else FALLBACK_PATHS["meetings"]
    
    # Load Shareholder Letters (JSON)
    if letter_path.exists():
        try:
            with open(letter_path, "r", encoding="utf-8") as f:
                archives["letters"] = json.load(f)
            print(f"✓ Loaded {len(archives['letters'])} shareholder letters")
        except Exception as e:
            print(f"✗ Error loading letters: {e}")
            archives["letters"] = {}
    else:
        print(f"✗ Letters not found")
        archives["letters"] = {}
    
    # Load Shareholder Meetings (JSON)
    if meeting_path.exists():
        try:
            with open(meeting_path, "r", encoding="utf-8") as f:
                meeting_data = json.load(f)
                archives["meetings"] = json.dumps(meeting_data, ensure_ascii=False)
                print(f"✓ Loaded {len(meeting_data)} shareholder meetings ({len(archives['meetings']) // 1024}KB)")
        except Exception as e:
            print(f"✗ Error loading meetings: {e}")
            archives["meetings"] = ""
    else:
        print(f"✗ Meetings not found")
        archives["meetings"] = ""

load_archives()

# ============= OpenAI Integration =============

def synthesize_with_openai(question, citations):
    """Use OpenAI to synthesize answer from citations"""
    if not OPENAI_API_KEY:
        print("WARNING: OPENAI_API_KEY not set")
        return None
    
    # Format citations for prompt
    citations_parts = []
    for c in citations[:3]:
        year_str = f" ({c.get('year')})" if c.get('year') else ""
        citations_parts.append(f"Source: {c['source']}{year_str}\nContent: {c['text'][:500]}")
    citations_text = "\n\n".join(citations_parts)
    
    prompt = f"""You are Warren Buffett's investment coach. Using the following citations from Berkshire Hathaway's letters and meetings, provide a concise, insightful answer to the investor's question.

Question: {question}

Relevant Sources:
{citations_text}

Provide a thoughtful, practical answer in German. Keep it under 200 words. Reference the sources directly."""
    
    try:
        request_data = json.dumps({
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are Warren Buffett's investment coach."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 250,
            "temperature": 0.7
        }).encode('utf-8')
        
        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=request_data,
            headers={
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'Content-Type': 'application/json',
                'User-Agent': 'Berkshire-Buddy/1.0'
            },
            method='POST'
        )
        
        response = urllib.request.urlopen(req, timeout=15)
        data = json.loads(response.read().decode('utf-8'))
        
        if 'choices' in data and len(data['choices']) > 0:
            return data['choices'][0]['message']['content']
        else:
            print(f"OpenAI response missing choices: {data}")
            return None
            
    except urllib.error.HTTPError as e:
        try:
            error_body = e.read().decode('utf-8')
            error_data = json.loads(error_body)
            error_msg = error_data.get('error', {}).get('message', 'Unknown error')
        except:
            error_msg = str(e)
        print(f"OpenAI HTTP Error {e.code}: {error_msg}")
        return None
    except Exception as e:
        print(f"OpenAI synthesis error: {type(e).__name__}: {e}")
        return None

# ============= Letter URL Generation =============

try:
    with open('letter_urls.json', 'r') as f:
        letter_url_config = json.load(f)
        LETTER_URL_MAPPING = letter_url_config.get('mapping', {})
except:
    LETTER_URL_MAPPING = {}

def get_letter_url(year):
    """Get correct URL for Berkshire shareholder letter"""
    if not year:
        return None
    
    year_str = str(year)
    return LETTER_URL_MAPPING.get(year_str)

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
    return keywords if keywords else [query.lower()]

def search_archives(query, limit=3):
    """Search in both archives by keywords"""
    results = []
    query_lower = query.lower()
    keywords = extract_keywords(query)
    
    # Search letters
    for year, content in archives.get("letters", {}).items():
        content_lower = content.lower()
        
        matches = []
        for keyword in keywords:
            for i, match in enumerate(re.finditer(re.escape(keyword), content_lower)):
                if i >= 3:
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
            if i >= 3:
                break
            pos = match.start()
            context = extract_context(content, pos)
            
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
    
    results = sorted(
        results,
        key=lambda x: (x["relevance"], -x["match_pos"]),
        reverse=True
    )[:limit]
    
    for r in results:
        if "Letter" in r.get("source", "") and r.get("year"):
            letter_url = get_letter_url(r["year"])
            if letter_url:
                r["letter_url"] = letter_url
    
    for r in results:
        del r["match_pos"]
    
    return results

# ============= HTTP Handler =============

class BerkshireHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        """Handle GET requests"""
        
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        cors_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        }
        
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
                    "POST /synthesis": "Get AI synthesis",
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
                    "meetings": "loaded" if archives.get("meetings") else "not loaded"
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
            letter_stats = {
                "count": len(letters),
                "year_range": f"{min(letters.keys())}\u2013{max(letters.keys())}" if letters else "N/A",
                "total_chars": sum(len(c) for c in letters.values())
            }
            
            response = {
                "letters": letter_stats,
                "meetings": {
                    "total_chars": len(archives.get("meetings", ""))
                }
            }
            self.wfile.write(json.dumps(response).encode())
        
        elif path == "/search":
            query = query_params.get('q', [''])[0]
            limit = int(query_params.get('limit', ['3'])[0])
            
            if not query:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                for k, v in cors_headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing query parameter"}).encode())
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
    
    def do_POST(self):
        """Handle POST requests"""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        cors_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        }
        
        if path == "/synthesis":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                data = json.loads(body)
                question = data.get('question', '')
                citations = data.get('citations', [])
                
                if not question or not citations:
                    raise ValueError("Missing question or citations")
                
                synthesis = synthesize_with_openai(question, citations)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                for k, v in cors_headers.items():
                    self.send_header(k, v)
                self.end_headers()
                
                response = {
                    "synthesis": synthesis if synthesis else "Unable to synthesize at this time",
                    "status": "ok" if synthesis else "no_synthesis"
                }
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                for k, v in cors_headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
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
    PORT = int(os.getenv("PORT", 8000))
    HOST = "0.0.0.0"
    
    print("\n" + "="*50)
    print("Berkshire Buddy API Starting...")
    print("="*50)
    print(f"OpenAI API Key: {'SET' if OPENAI_API_KEY else 'NOT SET'}")
    
    server = HTTPServer((HOST, PORT), BerkshireHandler)
    print(f"\n✅ Server running at http://{HOST}:{PORT}")
    print(f"📊 Stats: http://{HOST}:{PORT}/stats")
    print(f"🔍 Test: http://{HOST}:{PORT}/search?q=value+investing")
    print("="*50 + "\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nServer stopped")
        sys.exit(0)
