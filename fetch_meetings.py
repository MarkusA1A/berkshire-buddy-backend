#!/usr/bin/env python3
"""
Fetch Berkshire Shareholder Meeting transcripts from finanzapedia
and save as structured JSON
"""

import json
import urllib.request
import urllib.error
from pathlib import Path
import time

BASE_URL = "https://finanzapedia.com/en/warren-buffett/annual-meetings"

# Meeting years available (approximately)
YEARS = list(range(1994, 2027))

def fetch_meeting(year):
    """Fetch a single meeting transcript"""
    url = f"{BASE_URL}/{year}-berkshire-hathaway-annual-meeting"
    
    print(f"Fetching {year}...", end=" ")
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        html = response.read().decode('utf-8')
        print("✓")
        return html
    except urllib.error.HTTPError as e:
        print(f"✗ (HTTP {e.code})")
        return None
    except Exception as e:
        print(f"✗ ({e})")
        return None

def extract_text(html):
    """Extract readable text from HTML (basic extraction)"""
    from html.parser import HTMLParser
    
    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text = []
            self.skip = False
        
        def handle_starttag(self, tag, attrs):
            if tag in ['script', 'style', 'nav', 'footer']:
                self.skip = True
        
        def handle_endtag(self, tag):
            if tag in ['script', 'style', 'nav', 'footer']:
                self.skip = False
        
        def handle_data(self, data):
            if not self.skip:
                text = data.strip()
                if text:
                    self.text.append(text)
    
    extractor = TextExtractor()
    try:
        extractor.feed(html)
        return '\n'.join(extractor.text)
    except:
        return None

def main():
    print("="*50)
    print("Fetching Berkshire Meeting Transcripts")
    print("="*50)
    print(f"Target years: {YEARS[0]}-{YEARS[-1]}")
    print()
    
    meetings = {}
    
    for year in YEARS:
        html = fetch_meeting(year)
        if html:
            text = extract_text(html)
            if text and len(text) > 1000:  # Only save if substantial content
                meetings[str(year)] = text
                print(f"  Saved {len(text):,} chars for {year}")
        time.sleep(0.5)  # Rate limiting
    
    print()
    print(f"Downloaded {len(meetings)} meetings")
    
    # Save to JSON
    output_path = Path(__file__).parent / "data" / "berkshire-shareholder-meetings.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(meetings, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Saved to {output_path}")
    
    # Print summary
    total_chars = sum(len(text) for text in meetings.values())
    print(f"\nSummary:")
    print(f"  Meetings: {len(meetings)}")
    print(f"  Total size: {total_chars:,} characters (~{total_chars/1024/1024:.1f} MB)")

if __name__ == "__main__":
    main()
