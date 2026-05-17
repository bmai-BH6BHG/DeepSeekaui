#!/usr/bin/env python3
"""
DeepSeek TUI 远程桥接服务器 v2.0

支持：
  1. 远程 shell 命令执行（流式输出）
  2. 模型对话中继（转发到 DeepSeek TUI CLI，返回 token 估算）
  3. 系统监控（CPU / 内存 / 磁盘）
  4. PC 状态查询

启动：
  python bridge_server.py --port 9876
  python bridge_server.py --deepseek ./deepseek-tui-windows-x64.exe --port 9876
"""

import argparse
import asyncio
import json
import os
import platform
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 可选依赖
# ---------------------------------------------------------------------------
try:
    import websockets
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets

from websockets.asyncio.server import serve

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ---------------------------------------------------------------------------
# 协议常量
# ---------------------------------------------------------------------------
VERSION = "2.0.0"
DEFAULT_PORT = 9876

MSG_EXEC     = "exec"
MSG_CHAT     = "chat"
MSG_MONITOR  = "monitor"
MSG_STATUS   = "status"
MSG_PING     = "ping"
MSG_LS       = "ls"
MSG_READ     = "read"
MSG_PWD      = "pwd"
MSG_WORK     = "work"

REPLY_OUTPUT   = "output"
REPLY_RESULT   = "result"
REPLY_ERROR    = "error"
REPLY_STATUS   = "status"
REPLY_PONG     = "pong"
REPLY_NOTIFY   = "notification"
REPLY_CHAT     = "chat_response"
REPLY_MONITOR  = "monitor_data"
REPLY_FILE_LIST = "file_list"
REPLY_FILE_READ = "file_read"
REPLY_WORK     = "work_status"

CHARS_PER_TOKEN = 2.5


def make_id() -> str:
    return uuid.uuid4().hex[:12]


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def host_info() -> dict:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "cwd": str(Path.cwd()),
        "bridge_version": VERSION,
    }


# ---------------------------------------------------------------------------
# DeepSeek API 配置（从 config.toml 读取）
# ---------------------------------------------------------------------------
DS_API_KEY = None
DS_API_BASE = "https://api.deepseek.com"
DS_MODEL = "deepseek-v4-flash"

def load_deepseek_config():
    global DS_API_KEY, DS_API_BASE, DS_MODEL
    config_path = Path.home() / ".deepseek" / "config.toml"
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("api_key") and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if DS_API_KEY is None:
                    DS_API_KEY = val
            if line.startswith("api_base") and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                DS_API_BASE = val.rstrip("/")
            if line.startswith("model") and "=" in line and '"' in line:
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                DS_MODEL = val
        # [model] section overrides
        in_model = False
        for line in text.splitlines():
            if line.strip().startswith("[model]"):
                in_model = True; continue
            if in_model and line.strip().startswith("["):
                in_model = False
            if in_model and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "api_key": DS_API_KEY = v
                if k == "api_base": DS_API_BASE = v.rstrip("/")
                if k == "model": DS_MODEL = v

load_deepseek_config()

# ---------------------------------------------------------------------------
# 全局对话记忆 + 客户端注册（PC 终端 + 手机共享同一条会话）
# ---------------------------------------------------------------------------
_global_messages = []
_clients = set()

def get_messages():
    return _global_messages

def add_message(role: str, content: str):
    _global_messages.append({"role": role, "content": content})

def clear_messages():
    _global_messages.clear()

async def broadcast(msg_dict):
    """向所有已连接的客户端广播消息"""
    if not _clients:
        return
    text = json.dumps(msg_dict)
    dead = set()
    for c in _clients:
        try:
            await c.send(text)
        except Exception:
            dead.add(c)
    _clients.difference_update(dead)

# ---------------------------------------------------------------------------
# Chat —— 直接调 DeepSeek API，流式返回
# ---------------------------------------------------------------------------
async def api_chat(message: str, ws, req_id: str):
    if not DS_API_KEY:
        await ws.send(json.dumps({
            "type": REPLY_ERROR, "id": req_id,
            "message": "DeepSeek API key 未配置（检查 ~/.deepseek/config.toml）",
        }))
        return

    start_time = time.time()
    add_message("user", message)
    await broadcast({"type": "sync_message", "role": "user", "content": message})
    messages = get_messages()

    body = json.dumps({
        "model": DS_MODEL,
        "messages": messages,
        "stream": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{DS_API_BASE}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DS_API_KEY}",
        },
    )

    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=120)
        )

        full_text = ""
        token_in = 0
        token_out = 0
        content_detected = False

        while True:
            line = await loop.run_in_executor(None, resp.readline)
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            if raw == "data: [DONE]":
                break
            if raw.startswith("data: "):
                try:
                    chunk = json.loads(raw[6:])
                except json.JSONDecodeError:
                    continue

                # 收集 token
                if "usage" in chunk:
                    u = chunk["usage"]
                    token_in = u.get("prompt_tokens", token_in)
                    token_out = u.get("completion_tokens", token_out)

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                # 流式推送内容
                content = delta.get("content", "")
                if content:
                    full_text += content
                    content_detected = True
                    await broadcast({
                        "type": REPLY_OUTPUT,
                        "id": req_id,
                        "stream": "chat",
                        "data": content,
                    })

                # 流式推送 tool call（若有）
                tool_calls = delta.get("tool_calls", [])
                for tc in tool_calls:
                    func = tc.get("function", {})
                    await ws.send(json.dumps({
                        "type": REPLY_OUTPUT,
                        "id": req_id,
                        "stream": "tool",
                        "data": json.dumps({
                            "name": func.get("name", ""),
                            "arguments": func.get("arguments", ""),
                        }),
                    }))

        elapsed = time.time() - start_time

        # 没有 token 数就估算
        if token_in == 0 and token_out == 0:
            token_in = max(1, int(len(message) / 3.5))
            token_out = max(1, int(len(full_text) / 3.5))

        if full_text.strip():
            add_message("assistant", full_text)

        await broadcast({
            "type": REPLY_CHAT,
            "id": req_id,
            "response": full_text,
            "token_usage": {
                "input_tokens": token_in,
                "output_tokens": token_out,
                "total_tokens": token_in + token_out,
                "estimated": token_in < 10,
                "elapsed_sec": round(elapsed, 2),
            },
        })

    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        await ws.send(json.dumps({
            "type": REPLY_ERROR, "id": req_id,
            "message": f"API 错误 {e.code}: {detail}",
        }))
    except Exception as exc:
        await ws.send(json.dumps({
            "type": REPLY_ERROR, "id": req_id,
            "message": f"Chat 错误: {exc}",
        }))


# ---------------------------------------------------------------------------
# 工作/任务状态
# ---------------------------------------------------------------------------
def get_work_status(workspace: str = ".") -> dict:
    """读取当前工作区的任务/工作状态"""
    wd = Path(workspace)
    result = {"tasks": [], "active_work": None, "checklist": []}

    # 1. 读取 checklist/deepseek 任务文件
    checklist_dirs = [
        wd / ".deepseek" / "checklist",
        wd / "checklist",
        wd / "tasks",
    ]
    for cd in checklist_dirs:
        if cd.exists() and cd.is_dir():
            for f in sorted(cd.iterdir()):
                if f.suffix in (".json", ".md", ".txt"):
                    try:
                        text = f.read_text("utf-8", errors="replace")[:500]
                        result["checklist"].append({
                            "file": str(f.relative_to(wd)),
                            "content": text,
                        })
                    except OSError:
                        pass

    # 2. 主动读取 AGENTS.md/instructions.md
    for fname in ("AGENTS.md", ".deepseek/instructions.md", "README.md"):
        f = wd / fname
        if f.exists():
            try:
                text = f.read_text("utf-8", errors="replace")[:500]
                result["active_work"] = text
            except OSError:
                pass

    return result


# ---------------------------------------------------------------------------
# 系统监控
# ---------------------------------------------------------------------------
def get_system_stats() -> dict:
    if not HAS_PSUTIL:
        return {"available": False, "error": "psutil not installed"}

    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        boot = psutil.boot_time()
        uptime = time.time() - boot

        return {
            "available": True,
            "timestamp": time.time(),
            "cpu": {
                "percent": cpu,
                "cores": psutil.cpu_count(logical=True),
                "physical_cores": psutil.cpu_count(logical=False),
            },
            "memory": {
                "total_bytes": mem.total,
                "used_bytes": mem.used,
                "available_bytes": mem.available,
                "percent": mem.percent,
            },
            "disk": {
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
                "percent": disk.percent,
            },
            "network": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
            },
            "uptime_sec": uptime,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 命令执行
# ---------------------------------------------------------------------------
async def run_command(cmd: str, ws, req_id: str, cwd: Optional[str] = None):
    timeout = 60
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        async def read_stream(stream, stream_name: str):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\n")
                await ws.send(json.dumps({
                    "type": REPLY_OUTPUT,
                    "id": req_id,
                    "stream": stream_name,
                    "data": text,
                }))

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(proc.stdout, "stdout"),
                    read_stream(proc.stderr, "stderr"),
                ),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            await ws.send(json.dumps({
                "type": REPLY_ERROR, "id": req_id,
                "message": f"命令超时（>{timeout}s）",
            }))
            return

        await proc.wait()
        await ws.send(json.dumps({
            "type": REPLY_RESULT,
            "id": req_id,
            "exit_code": proc.returncode,
        }))
    except Exception as exc:
        await ws.send(json.dumps({
            "type": REPLY_ERROR, "id": req_id,
            "message": str(exc),
        }))


# ---------------------------------------------------------------------------
# 文件操作
# ---------------------------------------------------------------------------
import stat as _stat

def list_dir(path: str) -> dict:
    """列出目录内容"""
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "路径不存在"}
    if not p.is_dir():
        return {"ok": False, "error": "不是目录"}
    try:
        entries = []
        for child in sorted(p.iterdir()):
            try:
                st = child.stat()
                entries.append({
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size": st.st_size if not child.is_dir() else 0,
                    "modified": int(st.st_mtime),
                })
            except OSError:
                entries.append({
                    "name": child.name,
                    "is_dir": True,
                    "size": 0,
                    "modified": 0,
                })
        return {"ok": True, "path": str(p.resolve()), "entries": entries}
    except PermissionError:
        return {"ok": False, "error": "权限不足"}


async def handle_ls(path: str, ws, req_id: str):
    result = list_dir(path)
    await ws.send(json.dumps({
        "type": REPLY_FILE_LIST,
        "id": req_id,
        **result,
    }))


async def handle_read(path: str, ws, req_id: str):
    p = Path(path)
    if not p.exists():
        await ws.send(json.dumps({
            "type": REPLY_ERROR, "id": req_id,
            "message": "文件不存在",
        }))
        return
    if p.is_dir():
        await ws.send(json.dumps({
            "type": REPLY_ERROR, "id": req_id,
            "message": "是目录，不是文件",
        }))
        return
    try:
        MAX_BYTES = 100 * 1024  # 100KB
        data = p.read_bytes()[:MAX_BYTES]
        truncated = len(data) == MAX_BYTES and p.stat().st_size > MAX_BYTES
        await ws.send(json.dumps({
            "type": REPLY_FILE_READ,
            "id": req_id,
            "path": str(p.resolve()),
            "content": data.decode("utf-8", errors="replace"),
            "size": len(data),
            "truncated": truncated,
        }))
    except Exception as exc:
        await ws.send(json.dumps({
            "type": REPLY_ERROR, "id": req_id,
            "message": f"读取失败: {exc}",
        }))


# ---------------------------------------------------------------------------
# WebSocket 连接处理
# ---------------------------------------------------------------------------
async def handler(ws, deepseek_path: str, auth_token: Optional[str] = None):
    peer = ws.remote_address
    authenticated = (auth_token is None)

    print(f"[bridge] 客户端连接: {peer}")
    _clients.add(ws)

    await ws.send(json.dumps({
        "type": REPLY_STATUS,
        "connected": True,
        **host_info(),
    }))

    # 发送同步：完整对话历史
    history = get_messages()
    if history:
        pairs = []
        for m in history:
            pairs.append({"role": m["role"], "content": m["content"]})
        await ws.send(json.dumps({
            "type": "sync_full",
            "history": pairs,
        }))

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send(json.dumps({
                    "type": REPLY_ERROR, "id": "",
                    "message": "无效 JSON",
                }))
                continue

            msg_type = msg.get("type", "")
            req_id = msg.get("id", make_id())

            if not authenticated:
                if msg_type == "auth":
                    if msg.get("token") == auth_token:
                        authenticated = True
                        await ws.send(json.dumps({
                            "type": REPLY_NOTIFY,
                            "message": "认证成功",
                        }))
                    else:
                        await ws.send(json.dumps({
                            "type": REPLY_ERROR, "id": req_id,
                            "message": "认证失败",
                        }))
                        continue
                else:
                    await ws.send(json.dumps({
                        "type": REPLY_ERROR, "id": req_id,
                        "message": "请先认证",
                    }))
                    continue

            if msg_type == MSG_EXEC:
                command = msg.get("command", "")
                if not command.strip():
                    await ws.send(json.dumps({
                        "type": REPLY_ERROR, "id": req_id,
                        "message": "指令为空",
                    }))
                    continue
                print(f"[bridge] exec [{req_id}]: {command[:120]}")
                await run_command(command, ws, req_id)

            elif msg_type == MSG_CHAT:
                message = msg.get("message", "")
                if not message.strip():
                    await ws.send(json.dumps({
                        "type": REPLY_ERROR, "id": req_id,
                        "message": "消息为空",
                    }))
                    continue
                print(f"[bridge] chat [{req_id}]: {message[:80]}")
                await api_chat(message, ws, req_id)

            elif msg_type == MSG_MONITOR:
                stats = get_system_stats()
                await ws.send(json.dumps({
                    "type": REPLY_MONITOR,
                    "id": req_id,
                    **stats,
                }))

            elif msg_type == MSG_STATUS:
                await ws.send(json.dumps({
                    "type": REPLY_STATUS,
                    "id": req_id,
                    "connected": True,
                    **host_info(),
                }))

            elif msg_type == MSG_LS:
                path = msg.get("path", ".")
                print(f"[bridge] ls [{req_id}]: {path}")
                await handle_ls(path, ws, req_id)

            elif msg_type == MSG_WORK:
                workspace = msg.get("workspace", str(Path.cwd()))
                work_info = get_work_status(workspace)
                work_info["conversation_len"] = len(get_messages())
                await ws.send(json.dumps({
                    "type": REPLY_WORK,
                    "id": req_id,
                    **work_info,
                }))

            elif msg_type == MSG_READ:
                path = msg.get("path", "")
                if not path:
                    await ws.send(json.dumps({
                        "type": REPLY_ERROR, "id": req_id,
                        "message": "路径为空",
                    }))
                    continue
                print(f"[bridge] read [{req_id}]: {path}")
                await handle_read(path, ws, req_id)

            elif msg_type == "clear":
                clear_messages()
                await ws.send(json.dumps({
                    "type": REPLY_NOTIFY, "id": req_id,
                    "message": "对话已清空",
                }))

            elif msg_type == MSG_PING:
                await ws.send(json.dumps({
                    "type": REPLY_PONG,
                    "id": req_id,
                }))

            else:
                await ws.send(json.dumps({
                    "type": REPLY_ERROR, "id": req_id,
                    "message": f"未知指令: {msg_type}",
                }))

    except websockets.exceptions.ConnectionClosed:
        print(f"[bridge] 客户端断开: {peer}")
        _clients.discard(ws)
    except Exception as exc:
        print(f"[bridge] 异常: {exc}")
        _clients.discard(ws)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser(description="DeepSeek TUI 远程桥接服务器 v2")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--auth", default=None)
    parser.add_argument("--deepseek", default=None, help="DeepSeek CLI 路径")
    args = parser.parse_args()

    deepseek_path = args.deepseek
    if not deepseek_path:
        candidates = [
            "deepseek-tui-windows-x64.exe",
            "deepseek-tui",
            "deepseek",
            "./deepseek-tui-windows-x64.exe",
        ]
        for c in candidates:
            found = shutil.which(c)
            if found or Path(c).exists():
                deepseek_path = str(Path(c).resolve())
                break

    if deepseek_path and Path(deepseek_path).exists():
        print(f"[bridge] DeepSeek CLI: {deepseek_path}")
    else:
        print("[bridge] WARNING: DeepSeek CLI not found, chat disabled")

    print(f"+----------------------------------------+")
    print(f"|  DeepSeek TUI Bridge Server v{VERSION}  |")
    print(f"|  Listen: {args.host}:{args.port}                  |")
    print(f"|  Auth:   {'on' if args.auth else 'off'}                     |")
    print(f"|  Host:   {platform.node()}              |")
    print(f"|  Monitor:{'available' if HAS_PSUTIL else 'need psutil'}            |")
    print(f"+----------------------------------------+")

    async with serve(
        lambda ws: handler(ws, deepseek_path, args.auth),
        args.host,
        args.port,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[bridge] stopped")
