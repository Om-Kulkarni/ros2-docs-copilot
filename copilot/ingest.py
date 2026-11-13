"""Ingest the ROS 2 docs (reStructuredText source) into a local Chroma index.

Pipeline: clone docs repo -> parse .rst into sections -> clean markup ->
chunk with overlap -> embed locally (fastembed) -> upsert into Chroma.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config
from .store import get_collection, embed

HEADING_CHARS = set("=-^~*\"'#+`")


@dataclass
class Chunk:
    id: str
    text: str
    title: str
    section: str
    url: str
    path: str


def ensure_docs() -> Path:
    if not (config.DOCS_DIR / "source").exists():
        config.DOCS_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "-b", config.DOCS_BRANCH,
                        config.DOCS_REPO, str(config.DOCS_DIR)], check=True)
    return config.DOCS_DIR / "source"


def slugify(s: str) -> str:
    """Approximate Sphinx/docutils section anchors."""
    s = re.sub(r"[^\w\s-]", "", s.lower()).strip()
    return re.sub(r"[\s_]+", "-", s)


def is_underline(line: str) -> bool:
    l = line.rstrip()
    return len(l) >= 3 and len(set(l)) == 1 and l[0] in HEADING_CHARS


ROLE_RE = re.compile(r":(?:doc|ref|term|class|func|meth|py:\w+|cpp:\w+|envvar|file|command|kbd|code|rst:\w+):`([^`]*)`")


def clean_inline(text: str) -> str:
    def role(m: re.Match) -> str:
        inner = m.group(1)
        lab = re.match(r"(.*?)\s*<.*>$", inner, re.S)
        return (lab.group(1) if lab else inner).lstrip("~")
    text = ROLE_RE.sub(role, text)
    text = re.sub(r"`([^`<]+?)\s*<[^>]+>`_+", r"\1", text)  # external links
    text = re.sub(r"\|(\w+)\|", r"\1", text)                 # substitutions
    return text


SKIP_DIRECTIVES = ("image", "figure", "contents", "toctree", "redirect-from", "raw", "only")


def substitutions() -> dict[str, str]:
    d = config.DOCS_BRANCH
    full = {"jazzy": "Jazzy Jalisco", "humble": "Humble Hawksbill", "kilted": "Kilted Kaiju", "rolling": "Rolling Ridley"}
    return {"{DISTRO}": d, "{DISTRO_TITLE}": d.title(), "{DISTRO_TITLE_FULL}": full.get(d, d.title()),
            "{REPOS_FILE_BRANCH}": d}


def apply_substitutions(raw: str) -> str:
    """Expand the Sphinx macros the docs use (e.g. `--rosdistro {DISTRO}`)."""
    for k, v in substitutions().items():
        raw = raw.replace(k, v)
    return raw


def parse_rst(raw: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (page_title, [(section_title, body_text), ...])."""
    lines = raw.splitlines()
    sections: list[tuple[str, list[str]]] = [("", [])]
    title = ""
    i, skipping_indent = 0, None
    while i < len(lines):
        line = lines[i]
        # skip bodies of noisy directives (indented block after them)
        if skipping_indent is not None:
            if line.strip() == "" or (len(line) - len(line.lstrip())) > skipping_indent:
                i += 1
                continue
            skipping_indent = None
        stripped = line.strip()
        m = re.match(r"\s*\.\.\s+([\w-]+)::", line)
        if m and m.group(1) in SKIP_DIRECTIVES:
            skipping_indent = len(line) - len(line.lstrip())
            i += 1
            continue
        if re.match(r"\s*\.\.\s+_[\w-]+:\s*$", line):  # label targets
            i += 1
            continue
        # heading: text line followed by underline (optionally with overline)
        if (stripped and i + 1 < len(lines) and is_underline(lines[i + 1])
                and not is_underline(line) and len(lines[i + 1].rstrip()) >= len(stripped) - 2):
            heading = clean_inline(stripped)
            if not title:
                title = heading
            sections.append((heading, []))
            i += 2
            continue
        if is_underline(line):
            i += 1
            continue
        # keep directive names like code-block/note as light markers
        line = re.sub(r"^(\s*)\.\.\s+code-block::\s*(\w*)", r"\1[code \2]", line)
        line = re.sub(r"^(\s*)\.\.\s+([\w-]+)::\s*", r"\1[\2] ", line)
        sections[-1][1].append(clean_inline(line))
        i += 1
    out = []
    for heading, body in sections:
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(body)).strip()
        if len(text) > 40:
            out.append((heading or title, text))
    return title, out


def split_text(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    paras = re.split(r"\n\s*\n", text)
    chunks, cur = [], ""
    for p in paras:
        while len(p) > size:  # very long paragraph / code block
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:size])
            p = p[size - overlap:]
        if len(cur) + len(p) + 2 > size and cur:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n\n" + p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def iter_files(src: Path):
    for s in config.DOC_SECTIONS:
        p = src / s
        if p.is_file():
            yield p
        else:
            yield from sorted(p.rglob("*.rst"))


def build_chunks(src: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for f in iter_files(src):
        rel = f.relative_to(src).with_suffix("")
        page_url = config.DOCS_BASE_URL + rel.as_posix() + ".html"
        title, sections = parse_rst(apply_substitutions(f.read_text(encoding="utf-8", errors="ignore")))
        for s_idx, (sec, body) in enumerate(sections):
            anchor = "" if sec == title else "#" + slugify(sec)
            for c_idx, piece in enumerate(split_text(body, config.CHUNK_CHARS, config.CHUNK_OVERLAP)):
                header = f"{title} > {sec}" if sec != title else title
                chunks.append(Chunk(
                    id=f"{rel.as_posix()}::{s_idx}::{c_idx}",
                    text=f"{header}\n\n{piece}",
                    title=title, section=sec, url=page_url + anchor, path=rel.as_posix(),
                ))
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reset", action="store_true", help="drop and rebuild the index")
    args = ap.parse_args()
    src = ensure_docs()
    chunks = build_chunks(src)
    print(f"Parsed {len({c.path for c in chunks})} pages into {len(chunks)} chunks")
    col = get_collection(reset=args.reset)
    B = 128
    for i in range(0, len(chunks), B):
        batch = chunks[i:i + B]
        col.upsert(
            ids=[c.id for c in batch],
            documents=[c.text for c in batch],
            embeddings=embed([c.text for c in batch]),
            metadatas=[{"title": c.title, "section": c.section, "url": c.url, "path": c.path} for c in batch],
        )
        print(f"  indexed {min(i + B, len(chunks))}/{len(chunks)}", end="\r")
    print(f"\nDone. Collection '{config.COLLECTION}' has {col.count()} chunks at {config.CHROMA_DIR}")


if __name__ == "__main__":
    main()
