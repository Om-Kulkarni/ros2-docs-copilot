"""Eval suite for ROS 2 Docs Copilot.

Metrics
  * retrieval hit-rate@k (k=1,3,5): a question is a hit if any of its top-k chunks
    comes from one of its hand-labelled relevant pages. Also MRR@5. No LLM needed.
  * answer accuracy: LLM-as-judge grades the generated answer against the
    hand-written reference (CORRECT / PARTIAL / INCORRECT). Requires OPENROUTER_API_KEY.
  * citation rate: share of answers containing at least one [n] citation.

Usage:
  uv run python evals/run_evals.py                 # retrieval + answers
  uv run python evals/run_evals.py --retrieval-only
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

from copilot import config, rag

HERE = Path(__file__).parent
KS = (1, 3, 5)

JUDGE_PROMPT = """You are grading an AI assistant's answer to a ROS 2 question.
Compare the ANSWER with the REFERENCE answer written by a ROS 2 expert.
- CORRECT: contains the key facts/commands of the reference, no contradictions.
- PARTIAL: some key facts right but something important missing or wrong.
- INCORRECT: wrong, contradicts the reference, or says it could not find the answer.
Extra correct detail is fine. Reply with JSON only: {{"verdict": "CORRECT|PARTIAL|INCORRECT", "reason": "<one sentence>"}}

QUESTION: {q}
REFERENCE: {ref}
ANSWER: {ans}"""


def judge(q: str, ref: str, ans: str) -> dict:
    resp = rag.llm().chat.completions.create(
        model=config.JUDGE_MODEL, temperature=0,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(q=q, ref=ref, ans=ans)}])
    txt = resp.choices[0].message.content
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        out = {}
    v = str(out.get("verdict", "")).upper()
    return {"verdict": v if v in {"CORRECT", "PARTIAL", "INCORRECT"} else "INCORRECT",
            "reason": out.get("reason", txt[:200])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--mode", choices=["hybrid", "dense"], default=config.RETRIEVAL_MODE)
    ap.add_argument("--tag", default="", help="suffix for result files, e.g. 'dense'")
    args = ap.parse_args()

    items = [json.loads(l) for l in (HERE / "qa.jsonl").read_text().splitlines() if l.strip()]
    if args.limit:
        items = items[: args.limit]
    rows = []
    for it in items:
        hits = rag.search(it["question"], max(KS), mode=args.mode)
        paths = [h.path for h in hits]
        rel = set(it["relevant_pages"])
        first = next((i for i, p in enumerate(paths, 1) if p in rel), None)
        row = {"id": it["id"], "question": it["question"], "retrieved": paths,
               "first_relevant_rank": first, **{f"hit@{k}": bool(first and first <= k) for k in KS}}
        if not args.retrieval_only:
            t0 = time.time()
            r = rag.ask(it["question"], mode=args.mode)
            row.update(answer=r["answer"], latency_s=round(time.time() - t0, 2),
                       cited=bool(re.search(r"\[\d+\]", r["answer"])),
                       **judge(it["question"], it["reference"], r["answer"]))
        rows.append(row)
        print(f"#{it['id']:>2} rank={first} {row.get('verdict', '')}")

    n = len(rows)
    summary = {"date": str(date.today()), "n": n, "retrieval_mode": args.mode, "embed_model": config.EMBED_MODEL,
               "chunks": rag.get_collection().count(), "top_k_for_answers": config.TOP_K,
               **{f"hit@{k}": round(sum(r[f"hit@{k}"] for r in rows) / n, 3) for k in KS},
               "mrr@5": round(sum(1 / r["first_relevant_rank"] for r in rows if r["first_relevant_rank"]) / n, 3)}
    if not args.retrieval_only:
        c = sum(r["verdict"] == "CORRECT" for r in rows)
        p = sum(r["verdict"] == "PARTIAL" for r in rows)
        summary.update(llm_model=config.LLM_MODEL, judge_model=config.JUDGE_MODEL,
                       accuracy=round(c / n, 3), accuracy_incl_partial=round((c + p) / n, 3),
                       correct=c, partial=p, incorrect=n - c - p,
                       citation_rate=round(sum(r["cited"] for r in rows) / n, 3),
                       median_latency_s=sorted(r["latency_s"] for r in rows)[n // 2])

    sfx = f"_{args.tag}" if args.tag else ""
    (HERE / "results" / f"rows{sfx}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (HERE / "results" / f"summary{sfx}.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
