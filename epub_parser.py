#!/usr/bin/env python3
"""
EPUB Parser - Extracts text content from EPUB XHTML files

Supports both extracted EPUB directories and .epub files.
"""
import os
import re
import json
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict, Optional


class EPUBParser:
    def __init__(self, epub_path: str):
        self.original_path = Path(epub_path)
        self.temp_dir = None
        
        # Handle both .epub files and extracted directories
        if self.original_path.suffix.lower() == '.epub' and self.original_path.is_file():
            self.temp_dir = tempfile.mkdtemp()
            self.epub_path = Path(self.temp_dir) / "epub_content"
            self._extract_epub()
        else:
            self.epub_path = self.original_path
        
        # Find the XHTML directory (handle different EPUB structures)
        self.xhtml_dir = self._find_xhtml_dir()
        self.content = []
        self.metadata = {}
    
    def _extract_epub(self):
        """Extract .epub file to temporary directory"""
        print(f"Extracting EPUB: {self.original_path}")
        with zipfile.ZipFile(self.original_path, 'r') as zip_ref:
            zip_ref.extractall(self.epub_path)
    
    def _find_xhtml_dir(self) -> Path:
        """Find the directory containing XHTML content files"""
        # Common EPUB structures
        possible_paths = [
            self.epub_path / "OEBPS" / "xhtml",
            self.epub_path / "OEBPS",
            self.epub_path / "OPS" / "xhtml",
            self.epub_path / "OPS",
            self.epub_path / "EPUB" / "xhtml",
            self.epub_path / "EPUB",
            self.epub_path,
        ]
        
        for path in possible_paths:
            if path.exists() and list(path.glob("*.xhtml")):
                return path
            if path.exists() and list(path.glob("*.html")):
                return path
        
        # Fallback: search for any directory with xhtml/html files
        for xhtml_file in self.epub_path.rglob("*.xhtml"):
            return xhtml_file.parent
        for html_file in self.epub_path.rglob("*.html"):
            return html_file.parent
        
        return self.epub_path / "OEBPS" / "xhtml"  # Default fallback
    
    def cleanup(self):
        """Clean up temporary files"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
        
    def parse_metadata(self):
        """Parse metadata from OPF file"""
        # Find OPF file dynamically
        opf_file = None
        for pattern in ["*.opf", "**/*.opf"]:
            opf_files = list(self.epub_path.glob(pattern))
            if opf_files:
                opf_file = opf_files[0]
                break
        
        if not opf_file or not opf_file.exists():
            return {}
            
        tree = ET.parse(opf_file)
        root = tree.getroot()
        
        # Extract metadata
        ns = {'dc': 'http://purl.org/dc/elements/1.1/', 'opf': 'http://www.idpf.org/2007/opf'}
        metadata = {}
        
        title = root.find('.//dc:title', ns)
        if title is not None:
            metadata['title'] = title.text
            
        creator = root.find('.//dc:creator', ns)
        if creator is not None:
            metadata['creator'] = creator.text
            
        date = root.find('.//dc:date', ns)
        if date is not None:
            metadata['date'] = date.text
            
        # Get spine order
        spine = root.find('.//opf:spine', {'opf': 'http://www.idpf.org/2007/opf'})
        if spine is not None:
            metadata['spine'] = [item.get('idref') for item in spine.findall('.//opf:itemref', {'opf': 'http://www.idpf.org/2007/opf'})]
            
        return metadata
    
    def clean_text(self, text: str) -> str:
        """Clean extracted text"""
        if not text:
            return ""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        return text
    
    def extract_text_from_xhtml(self, filepath: Path) -> Dict:
        """Extract text content from an XHTML file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Get title
            title_elem = soup.find('title')
            title = title_elem.text if title_elem else filepath.stem
            
            # Remove script and style elements
            for script in soup(["script", "style", "meta"]):
                script.decompose()
            
            # Extract body content
            body = soup.find('body')
            if not body:
                return None
                
            # Extract headings for structure
            headings = []
            for h in body.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                heading_text = self.clean_text(h.get_text())
                heading_id = h.get('id', '')
                if heading_text:
                    headings.append({'text': heading_text, 'id': heading_id})
            
            # Extract paragraphs and other text content
            paragraphs = []
            for p in body.find_all(['p', 'div']):
                text = self.clean_text(p.get_text())
                if text and len(text) > 10:  # Filter out very short text
                    para_id = p.get('id', '')
                    paragraphs.append({'text': text, 'id': para_id})
            
            # Get full text
            full_text = self.clean_text(body.get_text())
            
            return {
                'file': filepath.name,
                'title': title,
                'headings': headings,
                'paragraphs': paragraphs,
                'full_text': full_text,
                'url': f"/content/{filepath.name}"
            }
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None
    
    def parse_all(self) -> List[Dict]:
        """Parse all XHTML files in the EPUB"""
        if not self.xhtml_dir.exists():
            raise ValueError(f"XHTML directory not found: {self.xhtml_dir}")
        
        # Get metadata
        self.metadata = self.parse_metadata()
        
        # Store the graphics/images directory for later use
        self.metadata['graphics_dir'] = str(self._find_graphics_dir())
        
        # Parse all XHTML and HTML files
        xhtml_files = sorted(self.xhtml_dir.glob("*.xhtml"))
        if not xhtml_files:
            xhtml_files = sorted(self.xhtml_dir.glob("*.html"))
        
        # Filter out image-only files
        content_files = [f for f in xhtml_files if not f.name.endswith('_images.xhtml')]
        
        parsed_content = []
        for xhtml_file in content_files:
            content = self.extract_text_from_xhtml(xhtml_file)
            if content and content.get('full_text'):
                parsed_content.append(content)
        
        self.content = parsed_content
        return parsed_content
    
    def _find_graphics_dir(self) -> Optional[Path]:
        """Find the graphics/images directory in the EPUB"""
        possible_names = ['graphics', 'images', 'img', 'image', 'media']
        
        for name in possible_names:
            for graphics_dir in self.epub_path.rglob(name):
                if graphics_dir.is_dir():
                    return graphics_dir
        
        return None
    
    def save_to_json(self, output_path: str):
        """Save parsed content to JSON file"""
        data = {
            'metadata': self.metadata,
            'content': self.content
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.content)} documents to {output_path}")


def get_epub_path() -> str:
    """Get EPUB path from environment variable or command line argument"""
    import sys
    
    # Check command line argument first
    if len(sys.argv) > 1:
        return sys.argv[1]
    
    # Check environment variable
    epub_path = os.environ.get('EPUB_PATH')
    if epub_path:
        return epub_path
    
    # Default fallback (for backward compatibility)
    default_path = "book.epub"
    if os.path.exists(default_path):
        return default_path
    
    # Check for any .epub file in current directory
    epub_files = list(Path('.').glob('*.epub'))
    if epub_files:
        return str(epub_files[0])
    
    raise ValueError(
        "No EPUB file specified. Set EPUB_PATH environment variable or pass path as argument.\n"
        "Usage: python epub_parser.py <path_to_epub>\n"
        "   or: EPUB_PATH=/path/to/book.epub python epub_parser.py"
    )


if __name__ == "__main__":
    epub_path = get_epub_path()
    print(f"Parsing EPUB: {epub_path}")
    
    parser = EPUBParser(epub_path)
    try:
        parsed = parser.parse_all()
        parser.save_to_json("content.json")
        print(f"Parsed {len(parsed)} documents")
    finally:
        parser.cleanup()
