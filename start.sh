#!/bin/bash
# Start Berkshire Buddy Backend

cd "$(dirname "$0")"

echo "================================"
echo "Berkshire Buddy API"
echo "================================"
echo ""

# Check if app_simple.py exists
if [ ! -f "app_simple.py" ]; then
    echo "❌ app_simple.py not found!"
    exit 1
fi

# Start server
echo "🚀 Starting server..."
echo ""
python3 app_simple.py
