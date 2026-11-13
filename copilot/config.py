"""Central settings, read from environment / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DOCS_REPO = "https://github.com/ros2/ros2_documentation.git"
DOCS_BRANCH = os.getenv("ROS_DISTRO_DOCS", "jazzy")
DOCS_DIR = Path(os.getenv("DOCS_DIR", ROOT / "data" / "ros2_documentation"))
DOCS_BASE_URL = f"https://docs.ros.org/en/{DOCS_BRANCH}/"
# Subset of the docs we index (relative to source/)
DOC_SECTIONS = ["Tutorials", "Concepts", "How-To-Guides", "Installation", "Glossary.rst"]

CHROMA_DIR = Path(os.getenv("CHROMA_DIR", ROOT / "data" / "chroma"))
COLLECTION = f"ros2_{DOCS_BRANCH}"
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
MODEL_CACHE = os.getenv("FASTEMBED_CACHE", str(ROOT / "data" / "models"))

CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", 1500))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))
TOP_K = int(os.getenv("TOP_K", 6))
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")  # or "dense"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", LLM_MODEL)
