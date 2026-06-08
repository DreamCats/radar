from __future__ import annotations

from pathlib import Path
from typing import Any

from radar.core.chat.skills import ChatSkill, ChatSkillLibrary
from radar.core.chat.tools import ChatTool

DEFAULT_MAX_CHARS = 20000
MAX_REFERENCE_FILES = 200


def build_skill_tools(skills: ChatSkillLibrary) -> list[ChatTool]:
    return [
        ChatTool(
            name="radar_list_skills",
            description="列出当前 radar chat 已加载的 skills 轻量目录，只返回 name 和 description。",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda args: _list_skills(skills),
        ),
        ChatTool(
            name="radar_load_skill",
            description="按 skill name 读取完整 SKILL.md 内容，并返回该 skill 目录下可按需读取的 reference 文件清单。",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=lambda args: _load_skill(skills, args),
        ),
        ChatTool(
            name="radar_read_skill_reference",
            description="读取某个 skill 目录内的 reference 文件。path 必须是相对路径，不能越过 skill 目录。",
            input_schema={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1000, "maximum": 100000},
                },
                "required": ["skill_name", "path"],
                "additionalProperties": False,
            },
            handler=lambda args: _read_reference(skills, args),
        ),
    ]


def _list_skills(skills: ChatSkillLibrary) -> dict[str, Any]:
    return {
        "items": [
            {
                "name": skill.name,
                "description": skill.description,
            }
            for skill in skills.list()
        ]
    }


def _load_skill(skills: ChatSkillLibrary, args: dict[str, Any]) -> dict[str, Any]:
    skill = _require_skill(skills, _required_str(args, "name"))
    return {
        "name": skill.name,
        "description": skill.description,
        "content": _clip(skill.instructions, DEFAULT_MAX_CHARS),
        "references": _reference_files(skill),
    }


def _read_reference(skills: ChatSkillLibrary, args: dict[str, Any]) -> dict[str, Any]:
    skill = _require_skill(skills, _required_str(args, "skill_name"))
    relative_path = _required_str(args, "path")
    max_chars = _optional_int(args.get("max_chars"), DEFAULT_MAX_CHARS)
    path = _resolve_reference_path(skill, relative_path)
    if not path.is_file():
        raise ValueError(f"reference 不存在: {relative_path}")
    content = path.read_text(encoding="utf-8")
    return {
        "skill_name": skill.name,
        "path": path.relative_to(skill.root_dir).as_posix(),
        "content": _clip(content, max_chars),
    }


def _reference_files(skill: ChatSkill) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(skill.root_dir.rglob("*")):
        if len(files) >= MAX_REFERENCE_FILES:
            break
        if not path.is_file() or path == skill.source_path or _is_hidden(path, skill.root_dir):
            continue
        files.append(
            {
                "path": path.relative_to(skill.root_dir).as_posix(),
                "size_bytes": path.stat().st_size,
            }
        )
    return files


def _resolve_reference_path(skill: ChatSkill, path: str) -> Path:
    relative_path = Path(path)
    if relative_path.is_absolute():
        raise ValueError("reference path 必须是相对路径")
    resolved = (skill.root_dir / relative_path).resolve()
    root = skill.root_dir.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("reference path 不能越过 skill 目录")
    return resolved


def _require_skill(skills: ChatSkillLibrary, name: str) -> ChatSkill:
    skill = skills.get(name)
    if skill is None:
        raise ValueError(f"未知 skill: {name}")
    return skill


def _required_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 不能为空")
    return value.strip()


def _optional_int(value: Any, default: int) -> int:
    if isinstance(value, int):
        return max(1000, min(value, 100000))
    return default


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n...[truncated {len(text) - max_chars} chars]"


def _is_hidden(path: Path, root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)
