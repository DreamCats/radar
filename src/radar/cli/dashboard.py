from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).resolve().parents[3]
UI_DIR = PROJECT_ROOT / "web" / "ui"


@dataclass
class ChildProcess:
    name: str
    process: subprocess.Popen


@click.command("dashboard")
@click.option("--host", default="127.0.0.1", show_default=True, help="后端监听地址。")
@click.option("--port", default=8000, show_default=True, type=int, help="后端监听端口。")
@click.option("--ui-host", default="127.0.0.1", show_default=True, help="前端监听地址。")
@click.option("--ui-port", default=5173, show_default=True, type=int, help="前端监听端口。")
@click.option("--reload", is_flag=True, help="开发时自动重载后端代码。")
@click.pass_context
def dashboard(
    ctx: click.Context,
    host: str,
    port: int,
    ui_host: str,
    ui_port: int,
    reload: bool,
) -> None:
    """一站式启动本地 Web dashboard。"""

    config_dir = ctx.obj.get("config_dir") if ctx.obj else None
    env = os.environ.copy()
    if isinstance(config_dir, Path):
        env["RADAR_CONFIG_DIR"] = str(config_dir)

    backend_args = [
        sys.executable,
        "-m",
        "uvicorn",
        "radar.web.server.app:create_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        backend_args.append("--reload")

    frontend_args = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        ui_host,
        "--port",
        str(ui_port),
    ]

    children: list[ChildProcess] = []
    try:
        children.append(_start_child("api", backend_args, PROJECT_ROOT, env))
        children.append(_start_child("ui", frontend_args, UI_DIR, env))
        click.echo(f"dashboard: http://{ui_host}:{ui_port}")
        click.echo(f"api: http://{host}:{port}")
        _wait_children(children)
    except KeyboardInterrupt:
        click.echo("\n正在停止 dashboard...")
    finally:
        _stop_children(children)


def _start_child(
    name: str,
    args: list[str],
    cwd: Path,
    env: dict[str, str],
) -> ChildProcess:
    if not cwd.exists():
        raise click.ClickException(f"{name} 工作目录不存在: {cwd}")
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            start_new_session=os.name != "nt",
        )
    except FileNotFoundError as exc:
        raise click.ClickException(f"{name} 启动失败，命令不存在: {args[0]}") from exc
    return ChildProcess(name=name, process=process)


def _wait_children(children: list[ChildProcess]) -> None:
    while True:
        for child in children:
            code = child.process.poll()
            if code is not None:
                if code != 0:
                    raise click.ClickException(f"{child.name} 进程退出，exit_code={code}")
                return
        time.sleep(0.2)


def _stop_children(children: list[ChildProcess]) -> None:
    for child in children:
        _terminate(child.process)
    for child in children:
        try:
            child.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill(child.process)


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
        return
    os.killpg(process.pid, signal.SIGTERM)


def _kill(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.kill()
        return
    os.killpg(process.pid, signal.SIGKILL)
