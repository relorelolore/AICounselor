# storage/paths.py
import os


DATA_DIR: str = os.environ.get("DATA_DIR", "./data")
DOCUMENTS_DIR: str = os.environ.get("DOCUMENTS_DIR", "./Documents")
WEB_DIR: str = os.environ.get("WEB_DIR", "./web")
CHROMA_DIR: str = os.path.join(DATA_DIR, "chroma")
INDEX_META: str = os.path.join(DATA_DIR, "index_meta.json")