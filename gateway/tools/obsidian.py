from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from gateway.config import ObsidianConfig

_config: ObsidianConfig | None = None


def init(config: ObsidianConfig) -> None:
    global _config
    _config = config


def _vault() -> Path:
    assert _config and _config.vault_path, "GATEWAY_OBSIDIAN__VAULT_PATH not configured"
    return Path(_config.vault_path).expanduser()


def _rel(path: Path) -> str:
    return str(path.relative_to(_vault()))


def list_notes(folder: str = "") -> str:
    """List all notes (.md files) in the Obsidian vault, optionally filtered to a subfolder. Returns relative paths."""
    base = _vault()
    search_root = base / folder if folder else base
    notes = sorted(p for p in search_root.rglob("*.md") if not any(part.startswith(".") for part in p.parts))
    return json.dumps([_rel(p) for p in notes])


def read_note(path: str) -> str:
    """Read the full content of a note. path is relative to the vault root (e.g. 'Projects/MyNote.md')."""
    note = _vault() / path
    if not note.exists():
        return json.dumps({"error": f"Note not found: {path}"})
    return json.dumps({"path": path, "content": note.read_text(encoding="utf-8")})


def search_notes(query: str, folder: str = "") -> str:
    """Search notes by content or title. Returns matching note paths and the line containing the match."""
    vault = _vault()
    search_root = vault / folder if folder else vault

    try:
        result = subprocess.run(
            ["grep", "-r", "-i", "-l", "--include=*.md", query, str(search_root)],
            capture_output=True,
            text=True,
        )
        matching_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except FileNotFoundError:
        matching_files = []
        for p in search_root.rglob("*.md"):
            try:
                if query.lower() in p.read_text(encoding="utf-8", errors="replace").lower():
                    matching_files.append(str(p))
            except Exception:
                pass

    results = []
    q = query.lower()
    for fpath in matching_files[:50]:
        p = Path(fpath)
        rel = _rel(p)
        if q in p.stem.lower():
            results.append({"path": rel, "match_type": "title"})
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines):
                if q in line.lower():
                    results.append({"path": rel, "match_type": "content", "line": i + 1, "context": line.strip()[:120]})
                    break
        except Exception:
            results.append({"path": rel, "match_type": "content"})

    return json.dumps(results)


def create_note(path: str, content: str) -> str:
    """Create a new note. path is relative to the vault root. Parent directories are created automatically. Fails if note already exists."""
    note = _vault() / path
    if note.exists():
        return json.dumps({"status": "error", "message": f"Note already exists: {path}. Use update_note to overwrite."})
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(content, encoding="utf-8")
    return json.dumps({"status": "created", "path": path})


def update_note(path: str, content: str) -> str:
    """Overwrite the content of an existing note. path is relative to the vault root."""
    note = _vault() / path
    if not note.exists():
        return json.dumps({"status": "error", "message": f"Note not found: {path}. Use create_note to create it."})
    note.write_text(content, encoding="utf-8")
    return json.dumps({"status": "updated", "path": path})


def append_to_note(path: str, content: str) -> str:
    """Append text to an existing note. Creates the note if it doesn't exist. A newline is added before the appended content."""
    note = _vault() / path
    note.parent.mkdir(parents=True, exist_ok=True)
    existing = note.read_text(encoding="utf-8") if note.exists() else ""
    separator = "\n" if existing and not existing.endswith("\n") else ""
    note.write_text(existing + separator + content, encoding="utf-8")
    return json.dumps({"status": "appended", "path": path})


def move_note(source_path: str, dest_path: str) -> str:
    """Move or rename a note. Both paths are relative to the vault root."""
    src = _vault() / source_path
    dst = _vault() / dest_path
    if not src.exists():
        return json.dumps({"status": "error", "message": f"Source not found: {source_path}"})
    if dst.exists():
        return json.dumps({"status": "error", "message": f"Destination already exists: {dest_path}"})
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return json.dumps({"status": "moved", "from": source_path, "to": dest_path})


def delete_note(path: str) -> str:
    """Delete a note permanently. path is relative to the vault root."""
    note = _vault() / path
    if not note.exists():
        return json.dumps({"status": "error", "message": f"Note not found: {path}"})
    note.unlink()
    return json.dumps({"status": "deleted", "path": path})


def register(mcp) -> None:
    for fn in [
        list_notes,
        read_note,
        search_notes,
        create_note,
        update_note,
        append_to_note,
        move_note,
        delete_note,
    ]:
        mcp.tool()(fn)
