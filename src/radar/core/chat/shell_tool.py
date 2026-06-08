from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from radar.core.chat.tools import ChatTool
from radar.core.config import RadarConfig


def build_shell_tool(config: RadarConfig) -> ChatTool:
    return ChatTool(
        name="radar_run_shell",
        description=(
            "在本机执行 shell 命令。默认使用 zsh -lic，因此会加载用户 .zshrc 中的环境变量。"
            "适合给 skills 调用本地 CLI；优先执行只读查询命令。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令。"},
                "cwd": {"type": "string", "description": "可选工作目录；默认使用 chat.shell.default_cwd 或当前进程目录。"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": config.chat.shell.timeout_seconds},
                "max_output_chars": {"type": "integer", "minimum": 1000, "maximum": config.chat.shell.max_output_chars},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
        handler=lambda args: run_shell_command(config, args),
    )


def run_shell_command(config: RadarConfig, args: dict[str, Any]) -> dict[str, Any]:
    command = _required_str(args.get("command"), "command")
    cwd = _resolve_cwd(config, args.get("cwd"))
    timeout = _bounded_int(args.get("timeout_seconds"), default=config.chat.shell.timeout_seconds, maximum=config.chat.shell.timeout_seconds)
    max_output_chars = _bounded_int(args.get("max_output_chars"), default=config.chat.shell.max_output_chars, maximum=config.chat.shell.max_output_chars)

    started = time.monotonic()
    try:
        completed = subprocess.run(
            [config.chat.shell.shell_path, "-lic", command],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "timed_out": False,
            "stdout": _clip(completed.stdout, max_output_chars),
            "stderr": _clip(completed.stderr, max_output_chars),
        }
    except subprocess.TimeoutExpired as error:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": None,
            "duration_ms": duration_ms,
            "timed_out": True,
            "stdout": _clip(_decode_output(error.stdout), max_output_chars),
            "stderr": _clip(_decode_output(error.stderr), max_output_chars),
        }


def _resolve_cwd(config: RadarConfig, value: object) -> Path:
    if isinstance(value, str) and value.strip():
        path = Path(value).expanduser()
    else:
        path = config.chat.shell.default_cwd or Path.cwd()
    if not path.exists() or not path.is_dir():
        raise ValueError(f"工作目录不存在: {path}")
    return path


def _required_str(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不能为空")
    return value


def _bounded_int(value: object, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    if parsed < 1:
        return default
    return min(parsed, maximum)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n...[truncated {omitted} chars]"


def _decode_output(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
