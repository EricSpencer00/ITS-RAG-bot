import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.ingest import ingest

if __name__ == "__main__":
    ingest()
