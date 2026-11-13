"""Retrieval + grounded answer generation with numbered citations."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from functools import lru_cache

from openai import OpenAI
from rank_bm25 import BM25Okapi

from . import config
from .store import embed_query, get_collection

SYSTEM_PROMPT = """You are ROS 2 Docs Copilot, an expert assistant for ROS 2 {distro}.
Answer ONLY from the numbered documentation excerpts provided.
- Cite every factual claim with the excerpt number in square brackets, e.g. [2] or [1][3].
- Include exact commands / code from the excerpts when relevant, in fenced code blocks.
- General commands shown in the excerpts apply to any argument (e.g. a command shown for one message type works for others); adapt them to the question.
- Only if the excerpts truly do not contain the answer, say "I couldn't find this in the ROS 2 {distro} docs." and stop.
- Be concise: short paragraphs or bullet points."""


@dataclass
class Hit:
    n: int
    title: str
    section: str
    url: str
    path: str
    score: float
    text: str

    def as_dict(self) -> dict:
        return asdict(self)


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
RRF_K = 60  # standard reciprocal-rank-fusion constant
CANDIDATES = 30  # per retriever, before fusion


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


@lru_cache(maxsize=1)
def _bm25():
    """Keyword index over the same chunks (built in memory from Chroma at first use)."""
    data = get_collection().get(include=["documents", "metadatas"])
    return BM25Okapi([_tokens(d) for d in data["documents"]]), data


def _dense(query: str, n: int) -> list[tuple[str, str, dict, float]]:
    res = get_collection().query(query_embeddings=[embed_query(query)], n_results=n,
                                 include=["documents", "metadatas", "distances"])
    return [(i, d, m, 1 - dist) for i, d, m, dist in
            zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])]


def _keyword(query: str, n: int) -> list[tuple[str, str, dict]]:
    bm25, data = _bm25()
    scores = bm25.get_scores(_tokens(query))
    top = sorted(range(len(scores)), key=lambda i: -scores[i])[:n]
    return [(data["ids"][i], data["documents"][i], data["metadatas"][i]) for i in top if scores[i] > 0]


def search(query: str, k: int = config.TOP_K, mode: str = config.RETRIEVAL_MODE) -> list[Hit]:
    """Hybrid retrieval: dense (bge-small) + BM25, merged with reciprocal rank fusion.
    `mode="dense"` gives the dense-only baseline."""
    dense = _dense(query, CANDIDATES if mode == "hybrid" else k)
    if mode == "dense":
        ranked = [(d, m, s) for _, d, m, s in dense]
    else:
        fused: dict[str, float] = {}
        docs: dict[str, tuple[str, dict]] = {}
        for rank, (cid, d, m, _) in enumerate(dense):
            fused[cid] = fused.get(cid, 0) + 1 / (RRF_K + rank + 1)
            docs[cid] = (d, m)
        for rank, (cid, d, m) in enumerate(_keyword(query, CANDIDATES)):
            fused[cid] = fused.get(cid, 0) + 1 / (RRF_K + rank + 1)
            docs[cid] = (d, m)
        best = sorted(fused, key=lambda c: -fused[c])[:k]
        ranked = [(docs[c][0], docs[c][1], round(fused[c] * RRF_K / 2, 4)) for c in best]  # 1.0 = top in both
    return [Hit(n=i, title=m["title"], section=m["section"], url=m["url"], path=m["path"],
                score=round(s, 4), text=d) for i, (d, m, s) in enumerate(ranked[:k], 1)]


@lru_cache(maxsize=1)
def llm() -> OpenAI:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key.")
    return OpenAI(base_url=config.OPENROUTER_BASE_URL, api_key=config.OPENROUTER_API_KEY)


def format_context(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{h.n}] {h.title} — {h.section}\nURL: {h.url}\n{h.text}" for h in hits)


def ask(question: str, k: int = config.TOP_K, model: str | None = None, mode: str = config.RETRIEVAL_MODE) -> dict:
    hits = search(question, k, mode)
    resp = llm().chat.completions.create(
        model=model or config.LLM_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(distro=config.DOCS_BRANCH.title())},
            {"role": "user", "content": f"Documentation excerpts:\n\n{format_context(hits)}\n\nQuestion: {question}"},
        ],
    )
    answer = resp.choices[0].message.content.strip()
    return {
        "question": question,
        "answer": answer,
        "sources": [{"n": h.n, "title": h.title, "section": h.section, "url": h.url, "score": h.score} for h in hits],
        "model": model or config.LLM_MODEL,
    }
