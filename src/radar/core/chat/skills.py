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
    triggers: tuple[str, ...]
    tool_names: tuple[str, ...]
    always_on: bool
    source_path: Path

    def render_prompt(self) -> str:
        parts = [f"Skill: {self.name}"]
        if self.description:
            parts.append(f"Description: {self.description}")
        if self.instructions:
            parts.append(f"Instructions:\n{self.instructions}")
        if self.tool_names:
            parts.append(f"Allowed tools: {', '.join(self.tool_names)}")
        return "\n".join(parts)


@dataclass(frozen=True)
class ChatSkillSelection:
    skills: tuple[ChatSkill, ...]

    @property
    def names(self) -> list[str]:
        return [skill.name for skill in self.skills]

    @property
    def allowed_tool_names(self) -> set[str] | None:
        names = {tool_name for skill in self.skills for tool_name in skill.tool_names}
        return names or None

    def render_prompt(self) -> str:
        if not self.skills:
            return ""
        rendered = "\n\n".join(skill.render_prompt() for skill in self.skills)
        return f"本轮启用的 skills：\n\n{rendered}"


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

    def select(self, text: str, *, max_active: int) -> ChatSkillSelection:
        if max_active <= 0:
            return ChatSkillSelection(())
        normalized_text = text.casefold()
        selected: list[ChatSkill] = []
        for skill in self._skills:
            if skill.always_on or _matches_triggers(normalized_text, skill.triggers):
                selected.append(skill)
            if len(selected) >= max_active:
                break
        return ChatSkillSelection(tuple(selected))


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
        triggers=tuple(_str_list(metadata.get("triggers") or metadata.get("keywords") or metadata.get("trigger"))),
        tool_names=tuple(_str_list(metadata.get("tools") or metadata.get("tool_names"))),
        always_on=bool(metadata.get("always_on", False)),
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


def _matches_triggers(text: str, triggers: tuple[str, ...]) -> bool:
    return any(trigger.casefold() in text for trigger in triggers if trigger)


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in (_optional_str(item) for item in value) if item]
    return []


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
