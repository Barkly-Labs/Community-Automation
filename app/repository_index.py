"""Persistent, incremental, local-only repository content index."""

import os, re, json, hashlib, sqlite3, fnmatch
from pathlib import Path
from collections import Counter
from . import core

EXT = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".astro",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".rst",
    ".txt",
    ".sql",
    ".rs",
    ".go",
    ".java",
    ".rb",
    ".php",
    ".vue",
    ".svelte",
    ".sh",
    ".ps1",
    ".xml",
    ".ini",
    ".cfg",
    ".c",
    ".h",
    ".cpp",
    ".cs",
    ".mjs",
    ".cjs",
}
NAMES = {"Dockerfile", "Makefile", "Gemfile", "LICENSE", "NOTICE", ".gitignore"}
SENSITIVE = re.compile(
    r"(?i)(secret|credential|password|token|api[_-]?key|private[_-]?key|\.env|id_rsa|id_ed25519|\.npmrc|\.pypirc|\.netrc|\.aws)"
)
PATTERN = re.compile(
    r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api[_-]?key|secret|password|token)\s*[:=]\s*[\"\']?[^\s\"\']{8,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})"
)


def rules():
    return {
        "max_bytes": int(os.getenv("INDEX_MAX_BYTES", "300000")),
        "exclude": set(core.EXCLUDE)
        | {x.strip() for x in os.getenv("INDEX_EXCLUDE", "").split(",") if x.strip()},
        "include": {
            x.strip() for x in os.getenv("INDEX_INCLUDE", "").split(",") if x.strip()
        },
    }


def reason(path, rel, st, opts):
    parts = Path(rel).parts
    if any(p in opts["exclude"] or p.startswith(".venv") for p in parts[:-1]):
        return "excluded directory"
    if path.is_symlink():
        return "symbolic link"
    if SENSITIVE.search(rel) or any(p.startswith(".env") for p in parts):
        return "sensitive filename"
    if st.st_size > opts["max_bytes"]:
        return "size limit"
    if (
        path.suffix.lower() not in EXT
        and path.name not in NAMES
        and not any(fnmatch.fnmatch(rel, p) for p in opts["include"])
    ):
        return "unsupported format"
    return None


def setup():
    with core.conn() as c:
        c.executescript(
            """CREATE TABLE IF NOT EXISTS indexed_files(path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, digest TEXT, language TEXT, content TEXT, updated_at TEXT);
  CREATE VIRTUAL TABLE IF NOT EXISTS indexed_fts USING fts5(path UNINDEXED, content, tokenize='unicode61');
  CREATE TABLE IF NOT EXISTS index_events(id INTEGER PRIMARY KEY, path TEXT, kind TEXT, at TEXT);
  CREATE TABLE IF NOT EXISTS index_exclusions(reason TEXT PRIMARY KEY, count INTEGER);
  CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', commits TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
  """
        )


def scan(path, progress=None):
    setup()
    root = Path(path).resolve()
    opts = rules()
    seen = set()
    counts = Counter()
    languages = Counter()
    changes = Counter()
    errors = []
    processed = 0
    with core.conn() as c:
        existing = {
            r["path"]: (r["mtime_ns"], r["size"], r["digest"])
            for r in c.execute("SELECT path,mtime_ns,size,digest FROM indexed_files")
        }
    for base, dirs, files in os.walk(root, followlinks=False):
        kept = []
        for d in dirs:
            if (
                d in opts["exclude"]
                or d.startswith(".venv")
                or (Path(base) / d).is_symlink()
            ):
                counts["excluded directory"] += 1
            else:
                kept.append(d)
        dirs[:] = kept
        for name in files:
            f = Path(base) / name
            rel = f.relative_to(root).as_posix()
            processed += 1
            try:
                st = f.lstat()
                why = reason(f, rel, st, opts)
                if why:
                    counts[why] += 1
                    continue
                with f.open("rb") as h:
                    data = h.read(opts["max_bytes"] + 1)
                if b"\0" in data:
                    counts["binary content"] += 1
                    continue
                try:
                    content = data.decode("utf-8-sig")
                except UnicodeError:
                    counts["non-UTF8"] += 1
                    continue
                if PATTERN.search(content):
                    counts["potential secret in content"] += 1
                    continue
                seen.add(rel)
                digest = hashlib.sha256(data).hexdigest()
                lang = core.LANG.get(f.suffix.lower(), "Other")
                languages[lang] += 1
                old = existing.get(rel)
                if old and old[2] == digest:
                    continue
                with core.conn() as c:
                    c.execute(
                        "INSERT INTO indexed_files VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET size=excluded.size,mtime_ns=excluded.mtime_ns,digest=excluded.digest,language=excluded.language,content=excluded.content,updated_at=excluded.updated_at",
                        (
                            rel,
                            st.st_size,
                            st.st_mtime_ns,
                            digest,
                            lang,
                            content,
                            core.now(),
                        ),
                    )
                    c.execute("DELETE FROM indexed_fts WHERE path=?", (rel,))
                    c.execute(
                        "INSERT INTO indexed_fts(path,content) VALUES(?,?)",
                        (rel, content),
                    )
                    c.execute(
                        "INSERT INTO index_events(path,kind,at) VALUES(?,?,?)",
                        (rel, "modified" if old else "added", core.now()),
                    )
                changes["modified" if old else "added"] += 1
            except (OSError, ValueError) as exc:
                errors.append(f"{rel}: {exc}")
            if progress and processed % 50 == 0:
                progress(processed, rel)
    for rel in existing.keys() - seen:
        with core.conn() as c:
            c.execute("DELETE FROM indexed_files WHERE path=?", (rel,))
            c.execute("DELETE FROM indexed_fts WHERE path=?", (rel,))
            c.execute(
                "INSERT INTO index_events(path,kind,at) VALUES(?,?,?)",
                (rel, "deleted", core.now()),
            )
        changes["deleted"] += 1
    # Detect likely renames from matching hashes in the current scan's event window.
    with core.conn() as c:
        c.execute("DELETE FROM index_exclusions")
        c.executemany("INSERT INTO index_exclusions VALUES(?,?)", counts.items())
        total = c.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    return {
        "indexed": total,
        "processed": processed,
        "changes": dict(changes),
        "excluded": dict(counts),
        "errors": errors[:30],
        "languages": dict(languages),
    }


def search(q, limit=20):
    setup()
    q = q.strip()[:120]
    if not q:
        return []
    terms = re.findall(r"[\w]+", q)
    if not terms:
        return []
    query = " OR ".join('"' + x.replace('"', "") + '"' for x in terms[:8])
    with core.conn() as c:
        return [
            dict(r)
            for r in c.execute(
                "SELECT f.path,f.language,substr(f.content,1,900) preview FROM indexed_fts x JOIN indexed_files f ON f.path=x.path WHERE indexed_fts MATCH ? LIMIT ?",
                (query, min(limit, 50)),
            )
        ]


def preview(path):
    setup()
    with core.conn() as c:
        r = c.execute(
            "SELECT path,language,substr(content,1,12000) content FROM indexed_files WHERE path=?",
            (path,),
        ).fetchone()
    return dict(r) if r else None


def context(paths, subject="", budget=14000):
    setup()
    out = []
    remaining = budget

    def add(label, content):
        nonlocal remaining
        chunk = str(content)[: min(remaining, 3500)]
        remaining -= len(chunk)
        if chunk:
            out.append(f"[{label}]\n{chunk}")

    with core.conn() as c:
        for p in paths[:20]:
            r = c.execute(
                "SELECT content FROM indexed_files WHERE path=?", (p,)
            ).fetchone()
            if r:
                add("Changed file " + p, r["content"])
        for r in c.execute(
            "SELECT path FROM indexed_files WHERE path LIKE ? OR path LIKE ? LIMIT 8",
            ("%README%", "%pyproject%"),
        ):
            if r["path"] not in paths:
                item = c.execute(
                    "SELECT content FROM indexed_files WHERE path=?", (r["path"],)
                ).fetchone()
                add("Project documentation " + r["path"], item["content"])
    for r in search(subject + " " + " ".join(Path(p).stem for p in paths[:8]), 10):
        if r["path"] not in paths:
            add("Related " + r["path"], r["preview"])
    return "\n\n".join(out)
