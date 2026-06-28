from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


class CloudUploadError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudUploadResult:
    local_path: Path
    remote_path: str
    url: str


def clean_remote_relative_path(value: str) -> str:
    cleaned = value.strip().replace("\\", "/").lstrip("/")
    parts = [part for part in cleaned.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise CloudUploadError(f"非法远程相对路径: {value}")
    return "/".join(parts)


def public_url(prefix: str, relative_path: str) -> str:
    return f"{prefix.rstrip('/')}/{quote(relative_path, safe='/')}"
