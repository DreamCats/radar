from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from radar.core.config import RadarConfig


@dataclass(frozen=True)
class ChatSkill:
    name: str
    description: str
    instructions: str
    source_path: Path

    @property
    def root_dir(self) -> Path:
        return self.source_path.parent


@dataclass(frozen=True)
class ChatSkillSelection:
    skills: tuple[ChatSkill, ...]

    @property
    def names(self) -> list[str]:
        return [skill.name for skill in self.skills]


class ChatSkillLibrary:
    def __init__(self, skills: list[ChatSkill] | None = None):
        self._skills = tuple(skills or [])

    @classmethod
    def from_config(cls, config: RadarConfig) -> "ChatSkillLibrary":
        if not config.chat.skills.enabled:
            return cls()
        return cls(load_chat_skills(config.chat_skill_paths))

    def list(self) -> list[ChatSkill]:
        return list(self._skills)

    def get(self, name: str) -> ChatSkill | None:
        normalized_name = name.casefold()
        for skill in self._skills:
            if skill.name.casefold() == normalized_name:
                return skill
        return None

    def select(self, text: str, *, max_active: int) -> ChatSkillSelection:
        return ChatSkillSelection(())

    def render_catalog_prompt(self) -> str:
        if not self._skills:
            return ""
        lines = [
            "可用 skills 目录：",
            "这些只是轻量目录。需要某个 skill 的完整说明时，先调用 radar_load_skill；如果该 skill 暴露 references，再按需调用 radar_read_skill_reference 读取具体相对路径。",
        ]
        for skill in self._skills:
            description = f": {skill.description}" if skill.description else ""
            lines.append(f"- {skill.name}{description}")
        return "\n".join(lines)


def load_chat_skills(paths: list[Path]) -> list[ChatSkill]:
    skills: list[ChatSkill] = []
    seen: set[str] = set()
    for root in paths:
        if not root.exists():
            continue
        for skill_file in _skill_files(root):
            skill = parse_chat_skill(skill_file)
            if skill.name in seen:
                raise ValueError(f"skill 名称重复: {skill.name}")
            seen.add(skill.name)
            skills.append(skill)
    return skills


def parse_chat_skill(path: Path) -> ChatSkill:
    metadata, body = _read_skill_markdown(path)
    name = _optional_str(metadata.get("name")) or path.parent.name
    if not name:
        raise ValueError(f"skill 缺少 name: {path}")
    return ChatSkill(
        name=name,
        description=_optional_str(metadata.get("description")) or "",
        instructions=_optional_str(metadata.get("system_prompt")) or body.strip(),
        source_path=path,
    )


def _skill_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.name == "SKILL.md" else []
    return sorted(path for path in root.glob("*/SKILL.md") if path.is_file())


def _read_skill_markdown(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"skill frontmatter 未闭合: {path}")
    raw_metadata = yaml.safe_load(text[4:end]) or {}
    if not isinstance(raw_metadata, dict):
        raise ValueError(f"skill frontmatter 必须是 mapping: {path}")
    return raw_metadata, text[end + 5 :]


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
