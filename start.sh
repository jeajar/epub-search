#!/bin/bash
# Startup script for EPUB Documentation Search
#
# Usage:
#   ./start.sh                          # Uses EPUB_PATH env var or auto-detects
#   ./start.sh /path/to/book.epub       # Specify EPUB path directly
#   EPUB_PATH=/path/to/book.epub ./start.sh

# Use first argument as EPUB path if provided
if [ -n "$1" ]; then
    export EPUB_PATH="$1"
fi

# Check if EPUB_PATH is set
if [ -z "$EPUB_PATH" ]; then
    # Try to find an epub file in current directory
    EPUB_FILE=$(ls *.epub 2>/dev/null | head -1)
    if [ -n "$EPUB_FILE" ]; then
        export EPUB_PATH="$EPUB_FILE"
        echo "Auto-detected EPUB: $EPUB_PATH"
    else
        echo "Error: No EPUB file specified."
        echo "Usage: ./start.sh /path/to/book.epub"
        echo "   or: EPUB_PATH=/path/to/book.epub ./start.sh"
        exit 1
    fi
fi

# Check if the EPUB file exists
if [ ! -e "$EPUB_PATH" ]; then
    echo "Error: EPUB file not found: $EPUB_PATH"
    exit 1
fi

# Parse EPUB if content.json doesn't exist or EPUB is newer
if [ ! -f "content.json" ] || [ "$EPUB_PATH" -nt "content.json" ]; then
    echo "Parsing EPUB: $EPUB_PATH"
    uv run python epub_parser.py "$EPUB_PATH"
fi

# Start the server
echo "Starting server on http://localhost:8000"
echo "Serving: $EPUB_PATH"
uv run python app.py
