"""Minimal FastAPI web UI + JSON API."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import config, rag

app = FastAPI(title="ROS 2 Docs Copilot")
INDEX_HTML = (Path(__file__).parent / "static" / "index.html").read_text()


class AskIn(BaseModel):
    question: str
    k: int = config.TOP_K


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/api/health")
def health() -> dict:
    from .store import get_collection
    return {"chunks": get_collection().count(), "model": config.LLM_MODEL, "distro": config.DOCS_BRANCH}


@app.get("/api/search")
def search(q: str, k: int = 5) -> list[dict]:
    return [h.as_dict() for h in rag.search(q, max(1, min(k, 20)))]


@app.post("/api/ask")
def ask(body: AskIn) -> dict:
    if not body.question.strip():
        raise HTTPException(400, "empty question")
    try:
        return rag.ask(body.question, max(1, min(body.k, 20)))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", 8000)))


if __name__ == "__main__":
    main()
