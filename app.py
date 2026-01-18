#!/usr/bin/env python3
"""
FastAPI application for serving EPUB content with AI search
"""
import json
import os
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

# Try to import vector search dependencies
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    VECTOR_SEARCH_AVAILABLE = True
except ImportError:
    VECTOR_SEARCH_AVAILABLE = False
    print("Warning: sentence-transformers not available. Using keyword search only.")


app = FastAPI(title="EPUB Documentation Search")

# Load content
CONTENT_FILE = Path("content.json")
content_data = {}
documents = []

if CONTENT_FILE.exists():
    with open(CONTENT_FILE, 'r', encoding='utf-8') as f:
        content_data = json.load(f)
        documents = content_data.get('content', [])
        print(f"Loaded {len(documents)} documents")
else:
    print(f"Warning: {CONTENT_FILE} not found. Run epub_parser.py first.")

# Initialize vector search if available
vector_model = None
document_embeddings = None

if VECTOR_SEARCH_AVAILABLE and documents:
    try:
        print("Loading sentence transformer model...")
        vector_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Generating document embeddings...")
        # Create embeddings for each document's full text
        document_texts = [doc.get('full_text', '') for doc in documents]
        document_embeddings = vector_model.encode(document_texts, show_progress_bar=True)
        print(f"Generated embeddings for {len(document_embeddings)} documents")
    except Exception as e:
        print(f"Error initializing vector search: {e}")
        vector_model = None
        document_embeddings = None


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    use_vector_search: bool = True


class SearchResult(BaseModel):
    title: str
    file: str
    url: str
    snippet: str
    score: float
    headings: List[dict]


def keyword_search(query: str, limit: int = 10) -> List[SearchResult]:
    """Simple keyword-based search"""
    query_lower = query.lower()
    query_words = set(query_lower.split())
    
    results = []
    for doc in documents:
        text = doc.get('full_text', '').lower()
        title = doc.get('title', '')
        
        # Calculate simple relevance score
        score = 0
        for word in query_words:
            if word in text:
                score += text.count(word)
            if word in title.lower():
                score += 10  # Boost title matches
        
        if score > 0:
            # Find snippet
            paragraphs = doc.get('paragraphs', [])
            snippet = ""
            for para in paragraphs[:3]:
                if any(word in para['text'].lower() for word in query_words):
                    snippet = para['text'][:300]
                    break
            
            if not snippet and paragraphs:
                snippet = paragraphs[0]['text'][:300]
            
            results.append(SearchResult(
                title=title,
                file=doc.get('file', ''),
                url=doc.get('url', ''),
                snippet=snippet,
                score=score,
                headings=doc.get('headings', [])
            ))
    
    # Sort by score
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:limit]


def vector_search(query: str, limit: int = 10) -> List[SearchResult]:
    """Vector-based semantic search"""
    if not vector_model or document_embeddings is None:
        return keyword_search(query, limit)
    
    try:
        # Encode query
        query_embedding = vector_model.encode([query])
        
        # Calculate similarities
        similarities = cosine_similarity(query_embedding, document_embeddings)[0]
        
        # Get top results
        top_indices = np.argsort(similarities)[::-1][:limit]
        
        results = []
        for idx in top_indices:
            if similarities[idx] > 0.1:  # Minimum similarity threshold
                doc = documents[idx]
                paragraphs = doc.get('paragraphs', [])
                snippet = paragraphs[0]['text'][:300] if paragraphs else doc.get('full_text', '')[:300]
                
                results.append(SearchResult(
                    title=doc.get('title', ''),
                    file=doc.get('file', ''),
                    url=doc.get('url', ''),
                    snippet=snippet,
                    score=float(similarities[idx]),
                    headings=doc.get('headings', [])
                ))
        
        return results
    except Exception as e:
        print(f"Error in vector search: {e}")
        return keyword_search(query, limit)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page"""
    html_file = Path("static/index.html")
    if html_file.exists():
        return FileResponse(html_file)
    return HTMLResponse("""
    <html>
        <head><title>eBook Search</title></head>
        <body>
            <h1>eBook Documentation Search</h1>
            <p>Please ensure static/index.html exists</p>
        </body>
    </html>
    """)


@app.post("/api/search")
async def search(request: SearchRequest):
    """Search endpoint"""
    if not documents:
        raise HTTPException(status_code=503, detail="Content not loaded")
    
    if request.use_vector_search and VECTOR_SEARCH_AVAILABLE and vector_model:
        results = vector_search(request.query, request.limit)
    else:
        results = keyword_search(request.query, request.limit)
    
    return {"results": [r.dict() for r in results]}


@app.get("/api/content/{filename}")
async def get_content(filename: str):
    """Get content for a specific file"""
    for doc in documents:
        if doc.get('file') == filename:
            return doc
    raise HTTPException(status_code=404, detail="Content not found")


@app.get("/api/metadata")
async def get_metadata():
    """Get book metadata"""
    return content_data.get('metadata', {})


@app.get("/api/toc")
async def get_toc():
    """Get table of contents"""
    toc = []
    for doc in documents:
        toc.append({
            'title': doc.get('title', ''),
            'file': doc.get('file', ''),
            'url': doc.get('url', ''),
            'headings': doc.get('headings', [])
        })
    return {"toc": toc}


# Mount static files
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount EPUB content directory for images (dynamically from parsed content)
graphics_dir = content_data.get('metadata', {}).get('graphics_dir')
if graphics_dir:
    graphics_path = Path(graphics_dir)
    if graphics_path.exists():
        # Mount the parent directory to serve images
        app.mount("/graphics", StaticFiles(directory=str(graphics_path.parent)), name="graphics")
        print(f"Mounted graphics directory: {graphics_path.parent}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
