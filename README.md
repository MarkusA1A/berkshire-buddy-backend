# Berkshire Buddy Backend API

FastAPI server für Suche in Berkshire Hathaway Archives.

## Setup

```bash
# Venv erstellen
python3 -m venv venv
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# Server starten
python app.py
```

Server läuft dann auf **http://localhost:8000**

## API Endpoints

### POST /search
Suche in allen Archives

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "How do you find good stocks?", "limit": 3}'
```

**Response:**
```json
{
  "query": "How do you find good stocks?",
  "citations": [
    {
      "text": "...relevanter Text mit **match**...",
      "source": "Shareholder Letter 1992",
      "year": "1992",
      "relevance": 1.0
    }
  ],
  "message": "Found 3 relevant quotes"
}
```

### GET /health
Health check

```bash
curl http://localhost:8000/health
```

### GET /stats
Archive Statistiken

```bash
curl http://localhost:8000/stats
```

### GET /docs
Interactive API documentation (Swagger UI)

```
http://localhost:8000/docs
```

## Archive Quellen

- `memory/berkshire-letters-archive.json` – 48 Jahrgänge (1977–2024)
- `memory/berkshire-shareholder-meetings.txt` – Q&A Sessions

## Testing

```bash
# Beispielsuche
curl "http://localhost:8000/search-simple?q=value+investing&limit=3"
```

## Entwicklung

Die API lädt die Archive beim Start in den RAM. 
Größe: ~3,5 MB, Suche dauert <100ms.

## Deployment

Für Production:
- Quelle auf **environment variables** setzen
- CORS auf deine Domain beschränken
- Behind Reverse Proxy (nginx, Vercel, Railway)

Beispiel Vercel deployment:
```bash
vercel --prod
```

## Lizenz

MIT – Private Project
