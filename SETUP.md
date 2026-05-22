# Berkshire Buddy Backend – Schnellstart

## Was ist das?

Ein **einfacher Python HTTP Server** (0 externe Dependencies), der die Berkshire Archives durchsucht und JSON-Responses liefert.

## Installation & Start

### 1️⃣ Voraussetzungen

- Python 3.8+ (Standard-Library nur)
- Berkshire Archives im lokalen Workspace
  - `~/openclaw/workspace/memory/berkshire-letters-archive.json` (48 Jahre)
  - `~/openclaw/workspace/memory/berkshire-shareholder-meetings.txt`

### 2️⃣ Backend starten

```bash
# Option A: Einfach
python3 app_simple.py

# Option B: Mit Start-Skript
./start.sh
```

**Fertig!** Server läuft dann auf **http://localhost:8000**

## API Endpoints

### POST /search
Suche in Archives

```bash
curl "http://localhost:8000/search?q=value+investing&limit=3"
```

**Response:**
```json
{
  "query": "value investing",
  "citations": [
    {
      "text": "...relevant quote with match...",
      "source": "Shareholder Letter 1992",
      "year": "1992",
      "relevance": 1.0
    }
  ],
  "message": "Found 3 citations"
}
```

### GET /stats
Archive-Statistiken

```bash
curl http://localhost:8000/stats
```

### GET /health
Health-Check

```bash
curl http://localhost:8000/health
```

## Berkshire Buddy Frontend

Die App auf **https://markusa1a.github.io/berkshire-buddy/** verbindet sich mit dem Backend:

- **Mit Backend laufen:** Live-Suche in allen 48 Jahren + Shareholder Meetings
- **Ohne Backend:** Demo-Mode mit 5 vordefininierten Antworten

**API-URL im Frontend anpassen:**

Wenn du den Backend irgendwo anders hostest, editiere in `index.html`:

```javascript
const API_BASE = 'https://dein-backend.com'; // Statt localhost:8000
```

## Performance

- Archive: ~3,5 MB (JSON-Parsing beim Start)
- Suche: <100ms pro Query
- RAM: ~50-100 MB

## Production Deployment

Wenn du das Backend hosted, z.B. auf **Vercel/Railway/Heroku**:

1. Backend auf deinen Server deployen
2. CORS erlauben (in `app_simple.py` bereits konfiguriert)
3. Archive mit deployen (oder via Git LFS)
4. Frontend API-URL anpassen

### Beispiel: Vercel Deployment

```bash
vercel --prod
```

(Benötigt `vercel.json` mit Python runtime)

## Troubleshooting

**"Server startet nicht"**
- Check: `python3 --version` (3.8+ nötig)
- Check: Sind die Archive-Dateien vorhanden?
- Check: Port 8000 nicht in Benutzung

**"Archives laden zu lange"**
- Erste Suche nach App-Start kann 5-10s dauern
- Danach sind Archive im RAM gecacht

**"Frontend verbindet sich nicht"**
- Check: Backend läuft auf `localhost:8000`
- Check: Browser-Console für CORS Fehler
- Check: Firefox/Chrome haben unterschiedliche CORS-Policies

## Next Steps

1. ✅ Backend lokal testen
2. ✅ Frontend-Integration prüfen
3. ⏳ (Optional) Semantic Search für bessere Relevanz
4. ⏳ (Optional) Frontend auf eigenem Backend hosten

## Fragen?

Schau die `app_simple.py` an – der Code ist einfach und gut kommentiert!
