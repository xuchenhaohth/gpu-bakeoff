"""Persist ComfyUI outputs and LLM transcripts under artifacts/ for pullback."""

from __future__ import annotations

import shutil
from pathlib import Path

from paths import ARTIFACTS_DIR, REMOTE_ROOT

COMFY_OUTPUT = Path("/workspace/ComfyUI/output")
MEDIA_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov")


def _artifact_dest(model_key: str, prompt_id: str, ext: str) -> Path:
    dest_dir = ARTIFACTS_DIR / model_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / f"{prompt_id}{ext}"


def repo_relative(path: Path) -> str:
    """Path relative to bakeoff root (e.g. artifacts/ideogram_4/img01.png)."""
    try:
        return path.relative_to(REMOTE_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def copy_comfy_output(comfy_rel: str, model_key: str, prompt_id: str) -> str:
    """Copy a ComfyUI output file into artifacts/{model}/{prompt_id}{ext}."""
    if not comfy_rel:
        return ""
    src = COMFY_OUTPUT / comfy_rel
    if not src.is_file():
        # Comfy may return filename only
        src = COMFY_OUTPUT / Path(comfy_rel).name
    if not src.is_file():
        return ""
    ext = src.suffix.lower() if src.suffix else ".png"
    if ext not in MEDIA_EXTS:
        ext = ".png"
    dest = _artifact_dest(model_key, prompt_id, ext)
    shutil.copy2(src, dest)
    return repo_relative(dest)


def write_transcript(model_key: str, prompt_id: str, content: str | None, note: str | None = None) -> str:
    """Write LLM response or stub note to artifacts/{model}/{prompt_id}.txt."""
    dest = _artifact_dest(model_key, prompt_id, ".txt")
    text = (content or "").strip()
    if not text and note:
        text = f"[stub] {note}"
    if not text:
        text = "[no output]"
    dest.write_text(text + "\n", encoding="utf-8")
    return repo_relative(dest)

