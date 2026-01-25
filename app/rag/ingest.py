from __future__ import annotations

import hashlib
import os
import pickle
import re
import time
from pathlib import Path
from typing import Iterable, List, Set
from urllib.parse import urljoin, urlparse

import faiss
import numpy as np
import requests
import trafilatura
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from app.config import CHROMA_PATH, EMBED_MODEL, RAW_DOCS_PATH

# ITS TeamDynamix portal base
TDX_BASE = "https://services.luc.edu"
TDX_SEARCH = "https://services.luc.edu/TDClient/33/Portal/Shared/Search/"
TDX_KB_PREFIX = "/TDClient/33/Portal/KB/"


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    if not text or len(text) == 0:
        return []
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(text_len, start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        # Move forward, ensuring we always make progress
        next_start = start + chunk_size - overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start
    return chunks


def _hash_id(source: str, chunk: str) -> str:
    return hashlib.sha256(f"{source}|{chunk}".encode("utf-8")).hexdigest()


def _load_text_files(folder: Path) -> Iterable[tuple[str, str, str]]:
    for path in folder.rglob("*"):
        if path.is_dir():
            continue
        if path.name == "seed_urls.txt":
            continue
        if path.suffix.lower() not in {".txt", ".md", ".html", ".htm"}:
            continue
        try:
            content = path.read_text(errors="ignore")
        except Exception:
            continue
        title = path.stem
        if path.suffix.lower() in {".html", ".htm"}:
            extracted = trafilatura.extract(content)
            if extracted:
                content = extracted
            else:
                soup = BeautifulSoup(content, "html.parser")
                content = soup.get_text(" ")
        cleaned = _clean_text(content)
        if cleaned:
            yield str(path), title, cleaned


def _fetch_page(url: str, timeout: int = 30) -> str | None:
    """Fetch raw HTML from URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  Failed to fetch {url}: {e}")
        return None


def _extract_text(html: str, url: str) -> str | None:
    """Extract main text content from HTML."""
    try:
        extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
        if extracted:
            return _clean_text(extracted)
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        return _clean_text(soup.get_text(" "))
    except Exception:
        return None


def _discover_kb_articles(search_url: str, max_pages: int = 40) -> List[str]:
    """
    Crawl TDX KB category pages to discover all article URLs.
    """
    discovered = set()
    categories_to_visit = set()
    visited_categories = set()
    
    # Start with the main KB page to find all categories
    kb_index_url = "https://services.luc.edu/TDClient/33/Portal/KB/"
    html = _fetch_page(kb_index_url)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "CategoryID=" in href:
                full_url = urljoin(TDX_BASE, href)
                categories_to_visit.add(full_url)
    
    print(f"  Found {len(categories_to_visit)} top-level categories")
    
    # Crawl each category and its subcategories
    while categories_to_visit:
        cat_url = categories_to_visit.pop()
        if cat_url in visited_categories:
            continue
        visited_categories.add(cat_url)
        
        html = _fetch_page(cat_url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Find articles on this page
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "ArticleDet?ID=" in href or "ArticleDet?id=" in href:
                full_url = urljoin(TDX_BASE, href)
                discovered.add(full_url)
            # Also check for subcategories
            elif "CategoryID=" in href:
                subcat_url = urljoin(TDX_BASE, href)
                if subcat_url not in visited_categories:
                    categories_to_visit.add(subcat_url)
        
        time.sleep(0.2)  # Be polite
        
        if len(visited_categories) % 10 == 0:
            print(f"  Visited {len(visited_categories)} categories, found {len(discovered)} articles...")
    
    print(f"\nDiscovered {len(discovered)} unique KB articles from {len(visited_categories)} categories")
    return list(discovered)


def _fetch_kb_article(url: str) -> tuple[str, str, str] | None:
    """Fetch and extract content from a KB article."""
    html = _fetch_page(url)
    if not html:
        return None
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Try to get article title
    title = ""
    title_el = soup.find("h1") or soup.find("h2") or soup.find("title")
    if title_el:
        title = title_el.get_text().strip()
    
    # Extract main content
    text = _extract_text(html, url)
    if not text or len(text) < 50:
        return None
    
    return url, title, text


def _load_seed_urls(seed_file: Path) -> List[str]:
    if not seed_file.exists():
        return []
    urls = []
    for line in seed_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def ingest() -> None:
    raw_path = Path(RAW_DOCS_PATH)
    raw_path.mkdir(parents=True, exist_ok=True)
    chroma_path = Path(CHROMA_PATH)
    chroma_path.mkdir(parents=True, exist_ok=True)

    print("Loading embedding model...")
    embedder = SentenceTransformer(EMBED_MODEL)
    index = faiss.IndexFlatIP(384)  # all-MiniLM-L6-v2 dimension
    metadata = []
    embeddings_list = []

    docs_added = 0

    # 1. Load local files
    local_files = list(_load_text_files(raw_path))
    print(f"Found {len(local_files)} local files")
    for source, title, text in tqdm(local_files, desc="Local docs"):
        if not text:
            continue
        chunks = _chunk_text(text)
        for chunk in chunks:
            embeddings_list.append(chunk)
            metadata.append({"content": chunk, "source": source, "title": title})
            docs_added += 1

    # 2. Discover and fetch KB articles from TDX
    print("\nDiscovering ITS KB articles...")
    kb_urls = _discover_kb_articles(TDX_SEARCH)
    
    print(f"\nFetching {len(kb_urls)} KB articles...")
    for url in tqdm(kb_urls, desc="KB Articles"):
        result = _fetch_kb_article(url)
        if not result:
            continue
        source, title, text = result
        chunks = _chunk_text(text)
        for chunk in chunks:
            embeddings_list.append(chunk)
            metadata.append({"content": chunk, "source": source, "title": title or url})
            docs_added += 1
        time.sleep(0.3)  # Be polite to server

    # 3. Also fetch any additional seed URLs
    seed_urls = _load_seed_urls(raw_path / "seed_urls.txt")
    additional_urls = [u for u in seed_urls if "/KB/" not in u]  # Skip KB URLs already handled
    
    for url in tqdm(additional_urls, desc="Additional URLs"):
        html = _fetch_page(url)
        if not html:
            continue
        text = _extract_text(html, url)
        if not text:
            continue
        chunks = _chunk_text(text)
        for chunk in chunks:
            embeddings_list.append(chunk)
            metadata.append({"content": chunk, "source": url, "title": url})
            docs_added += 1

    # 4. Encode and save
    if embeddings_list:
        print(f"\nEncoding {len(embeddings_list)} chunks...")
        embeddings = embedder.encode(embeddings_list, normalize_embeddings=True, show_progress_bar=True)
        index.add(np.array(embeddings))
        
        faiss.write_index(index, str(chroma_path / "faiss.index"))
        with open(chroma_path / "metadata.pkl", "wb") as f:
            pickle.dump(metadata, f)
        
        print(f"\n✓ Ingested {docs_added} chunks into FAISS at {CHROMA_PATH}")
    else:
        print("\n⚠ No documents found to ingest")


if __name__ == "__main__":
    ingest()
    ingest()
