from __future__ import annotations

import subprocess

from radar.core.chat import ChatAgent, ChatSessionStore
from radar.core.chat.shell_tool import run_shell_command
from radar.core.config import RadarConfig


def test_chat_agent_registers_builtin_shell_tool(tmp_path):
    config = RadarConfig(storage={"data_dir": tmp_path}, chat={"shell": {"default_cwd": str(tmp_path)}})
    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))

    tools = {tool.name: tool for tool in agent.tools.list(read_only=True)}

    assert "radar_run_shell" in tools
    assert "读取系统时间" in tools["radar_run_shell"].description


def test_chat_agent_can_disable_builtin_shell_tool(tmp_path):
    config = RadarConfig(storage={"data_dir": tmp_path}, chat={"shell": {"enabled": False}})
    agent = ChatAgent(config, store=ChatSessionStore(tmp_path / "chat"))

    tool_names = [tool.name for tool in agent.tools.list(read_only=True)]

    assert "radar_run_shell" not in tool_names


def test_shell_tool_runs_zsh_login_interactive_shell(tmp_path, monkeypatch):
    config = RadarConfig(
        storage={"data_dir": tmp_path},
        chat={"shell": {"default_cwd": str(tmp_path), "timeout_seconds": 3, "max_output_chars": 1000}},
    )
    captured = {}

    def fake_run(command, **kwargs):
        captured.update({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, stdout="hello\n", stderr="")

    monkeypatch.setattr("radar.core.chat.shell_tool.subprocess.run", fake_run)

    result = run_shell_command(config, {"command": "echo hello", "timeout_seconds": 99, "max_output_chars": 999})

    assert captured["command"] == ["/bin/zsh", "-lic", "echo hello"]
    assert captured["cwd"] == str(tmp_path)
    assert captured["timeout"] == 3
    assert captured["text"] is True
    assert captured["capture_output"] is True
    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\n"


def test_shell_tool_reports_timeout(tmp_path, monkeypatch):
    config = RadarConfig(storage={"data_dir": tmp_path}, chat={"shell": {"default_cwd": str(tmp_path), "timeout_seconds": 1}})

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=1, output=b"partial", stderr=b"slow")

    monkeypatch.setattr("radar.core.chat.shell_tool.subprocess.run", fake_run)

    result = run_shell_command(config, {"command": "sleep 10"})

    assert result["exit_code"] is None
    assert result["timed_out"] is True
    assert result["stdout"] == "partial"
    assert result["stderr"] == "slow"
