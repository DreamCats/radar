from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class IndustryChainNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class IndustryChainDetail:
    item: dict[str, Any]
    data: dict[str, Any]
    content_markdown: str


def list_industry_chains() -> dict[str, Any]:
    return _read_json(_industry_chains_dir() / "index.json")


def get_industry_chain_detail(chain_id: str) -> IndustryChainDetail:
    index = list_industry_chains()
    item = next((entry for entry in index.get("items", []) if entry.get("chain_id") == chain_id), None)
    if item is None:
        raise IndustryChainNotFoundError(chain_id)

    base_dir = _industry_chains_dir()
    content_path = _resolve_content_path(base_dir, str(item.get("content_path", "")))
    data_path = _resolve_content_path(base_dir, str(item.get("data_path", "")))
    data = _read_json(data_path)
    markdown = content_path.read_text(encoding="utf-8")
    return IndustryChainDetail(item=item, data=data, content_markdown=markdown)


def _industry_chains_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "industry-chains"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise IndustryChainNotFoundError(str(path)) from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _resolve_content_path(base_dir: Path, relative_path: str) -> Path:
    path = (base_dir / relative_path).resolve()
    if not path.is_relative_to(base_dir.resolve()):
        raise IndustryChainNotFoundError(relative_path)
    return path
