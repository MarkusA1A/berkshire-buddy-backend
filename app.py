#!/usr/bin/env python3
"""
Berkshire Buddy Backend
Powered by Buffett & Munger Archives
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import re
from pathlib import Path

app = FastAPI(title="Berkshire Buddy API", version="1.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= Models =============

class SearchRequest(BaseModel):
    query: str
    limit: int = 3

class Citation(BaseModel):
    text: str
    source: str
    year: Optional[str] = None
    relevance: float

class SearchResponse(BaseModel):
    query: str
    citations: List[Citation]
    message: str

# ============= Data Loading =============

ARCHIVE_PATHS = {
    "letters": Path("/Users/macmini/.openclaw/workspace/memory/berkshire-letters-archive.json"),
    "meetings": Path("/Users/macmini/.openclaw/workspace/memory/berkshire-shareholder-meetings.txt"),
}

# Load archives on startup
archives = {}

def load_archives():
    """Load both archives into memory"""
    global archives
    
    # Load Shareholder Letters (JSON)
    if ARCHIVE_PATHS["letters"].exists():
        try:
            with open(ARCHIVE_PATHS["letters"], "r", encoding="utf-8") as f:
                archives["letters"] = json.load(f)
            print(f"✓ Loaded {len(archives['letters'])} shareholder letters")
        except Exception as e:
            print(f"✗ Error loading letters: {e}")
            archives["letters"] = {}
    
    # Load Shareholder Meetings (TXT)
    if ARCHIVE_PATHS["meetings"].exists():
        try:
            with open(ARCHIVE_PATHS["meetings"], "r", encoding="utf-8") as f:
                archives["meetings"] = f.read()
            print(f"✓ Loaded shareholder meetings ({len(archives['meetings'])} chars)")
        except Exception as e:
            print(f"✗ Error loading meetings: {e}")
            archives["meetings"] = ""
    
    if not archives:
        print("⚠ No archives loaded!")

# Load on startup
load_archives()

# ============= Search Logic =============

def extract_context(text: str, match_pos: int, context_words: int = 50) -> str:
    """Extract context around a match"""
    words = text.split()
    match_word_pos = len(text[:match_pos].split())
    
    start = max(0, match_word_pos - context_words)
    end = min(len(words), match_word_pos + context_words)
    
    context = " ".join(words[start:end])
    return context.strip()

def search_letters(query: str, limit: int = 3) -> List[Citation]:
    """Search in shareholder letters"""
    citations = []
    query_lower = query.lower()
    
    for year, content in archives.get("letters", {}).items():
        content_lower = content.lower()
        
        # Find all matches
        for match in re.finditer(re.escape(query_lower), content_lower):
            pos = match.start()
            context = extract_context(content, pos, context_words=40)
            
            # Highlight match in context
            highlighted = context.replace(
                query_lower,
                f"**{query}**"
            )
            
            relevance = 1.0  # Letters are primary source
            
            citations.append(Citation(
                text=highlighted,
                source=f"Shareholder Letter {year}",
                year=year,
                relevance=relevance
            ))
    
    return sorted(citations, key=lambda x: x.relevance, reverse=True)[:limit]

def search_meetings(query: str, limit: int = 3) -> List[Citation]:
    """Search in shareholder meetings"""
    citations = []
    query_lower = query.lower()
    content = archives.get("meetings", "")
    content_lower = content.lower()
    
    # Find all matches
    for match in re.finditer(re.escape(query_lower), content_lower):
        pos = match.start()
        context = extract_context(content, pos, context_words=40)
        
        # Highlight match in context
        highlighted = context.replace(
            query_lower,
            f"**{query}**"
        )
        
        # Try to extract year from context
        year_match = re.search(r'\b(19|20)\d{2}\b', context)
        year = year_match.group(0) if year_match else None
        
        relevance = 0.95  # Meetings slightly lower than letters
        
        citations.append(Citation(
            text=highlighted,
            source="Shareholder Meeting",
            year=year,
            relevance=relevance
        ))
    
    return sorted(citations, key=lambda x: x.relevance, reverse=True)[:limit]

# ============= API Endpoints =============

@app.get("/")
def root():
    return {
        "name": "Berkshire Buddy API",
        "version": "1.0.0",
        "endpoints": {
            "search": "/search (POST)",
            "health": "/health (GET)",
            "stats": "/stats (GET)"
        }
    }

@app.get("/health")
def health():
    """Health check"""
    return {
        "status": "ok",
        "archives_loaded": {
            "letters": len(archives.get("letters", {})),
            "meetings": len(archives.get("meetings", ""))
        }
    }

@app.get("/stats")
def stats():
    """Archive statistics"""
    letters_count = len(archives.get("letters", {}))
    meetings_size = len(archives.get("meetings", ""))
    
    years = sorted(archives.get("letters", {}).keys()) if archives.get("letters") else []
    year_range = f"{years[0]}–{years[-1]}" if years else "N/A"
    
    return {
        "letters": {
            "count": letters_count,
            "year_range": year_range,
            "total_chars": sum(len(v) for v in archives.get("letters", {}).values())
        },
        "meetings": {
            "total_chars": meetings_size
        }
    }

@app.post("/search")
def search(request: SearchRequest):
    """
    Search across all archives for relevant quotes
    
    Example:
    POST /search
    {
        "query": "How do you find good stocks?",
        "limit": 3
    }
    """
    
    if not request.query or len(request.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    if request.limit > 10:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 10")
    
    # Search both sources
    all_citations = []
    all_citations.extend(search_letters(request.query.lower(), limit=request.limit * 2))
    all_citations.extend(search_meetings(request.query.lower(), limit=request.limit * 2))
    
    # Sort by relevance and limit
    all_citations = sorted(
        all_citations,
        key=lambda x: x.relevance,
        reverse=True
    )[:request.limit]
    
    # Build message
    if not all_citations:
        message = f"Keine direkten Treffer für '{request.query}' gefunden. Versuche eine andere Frage!"
    else:
        message = f"Gefunden {len(all_citations)} relevante Zitate aus den Berkshire Archives."
    
    return SearchResponse(
        query=request.query,
        citations=all_citations,
        message=message
    )

@app.get("/search-simple")
def search_simple(q: str, limit: int = 3):
    """Simple search via query param (for testing)"""
    return search(SearchRequest(query=q, limit=limit))

# ============= Startup =============

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print("Berkshire Buddy API Starting...")
    print("="*50)
    load_archives()
    print("\n🚀 Ready! Visit http://localhost:8000")
    print("📚 Docs: http://localhost:8000/docs")
    print("="*50 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
