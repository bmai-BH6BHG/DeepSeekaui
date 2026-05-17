#!/usr/bin/env python3
"""
DeepSeek Remote - PC 终端客户端

在 PC 上运行此脚本代替直接运行 deepseek-tui。
它连接到本地桥接服务器，所有对话自动同步到手机 APP。

用法：
  python pc_client.py                          # 默认 ws://127.0.0.1:9876
  python pc_client.py --host 127.0.0.1 --port 9876
  python pc_client.py --clear                  # 启动时清空对话历史
"""

import argparse
import asyncio
import json
import os
import sys
import signal
from pathlib import Path

try:
    import websockets
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets


async def main():
    parser = argparse.ArgumentParser(description="DeepSeek Remote PC 终端客户端")
    parser.add_argument("--host", default="127.0.0.1", help="桥接服务器地址")
    parser.add_argument("--port", type=int, default=9876, help="桥接服务器端口")
    parser.add_argument("--clear", action="store_true", help="清空对话历史")
    args = parser.parse_args()

    uri = f"ws://{args.host}:{args.port}"
    print(f"+----------------------------------------------+")
    print(f"|  DeepSeek Remote - PC 终端客户端              |")
    print(f"|  连接: {uri}                 |")
    print(f"|  手机 APP 将看到同样的对话                     |")
    print(f"|  输入 /help 查看命令  /quit 退出              |")
    print(f"+----------------------------------------------+")
    print()

    try:
        async with websockets.connect(uri) as ws:
            welcome = await ws.recv()
            data = json.loads(welcome)
            if data.get("type") == "status":
                print(f"[已连接] {data.get('hostname')}  v{data.get('bridge_version')}")
                print(f"[工作区] {data.get('cwd')}")
                print()

            if args.clear:
                await ws.send(json.dumps({"type": "clear"}))

            while True:
                try:
                    text = input(">>> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n[退出]")
                    break

                if not text:
                    continue

                if text in ("/quit", "/exit"):
                    break
                elif text == "/clear":
                    await ws.send(json.dumps({"type": "clear"}))
                    print("[对话已清空]")
                    continue
                elif text == "/help":
                    print("命令: /quit 退出  /clear 清空历史  /status 状态  /history 历史")
                    continue
                elif text == "/status":
                    await ws.send(json.dumps({"type": "work"}))
                    resp = await ws.recv()
                    d = json.loads(resp)
                    if d.get("type") == "work_status":
                        print(f"[对话] {d.get('conversation_len', 0)} 条消息")
                        print(f"[工作] {(d.get('active_work') or '无')[:100]}")
                    continue
                elif text == "/history":
                    continue

                await ws.send(json.dumps({"type": "chat", "message": text}))
                full_text = ""
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    t = msg.get("type", "")
                    if t == "output" and msg.get("stream") == "chat":
                        token = msg.get("data", "")
                        full_text += token
                        print(token, end="", flush=True)
                    elif t == "chat_response":
                        u = msg.get("token_usage", {})
                        print(f"\n[{u.get('elapsed_sec',0)}s  in={u.get('input_tokens',0)}  out={u.get('output_tokens',0)}]")
                        break
                    elif t == "error":
                        print(f"\n[错误] {msg.get('message','')}")
                        break

    except websockets.exceptions.ConnectionClosed:
        print("[连接断开]")
    except ConnectionRefusedError:
        print(f"[错误] 无法连接到桥接服务器 {uri}")
        print("       请确保 bridge_server.py 已在运行")
    except Exception as exc:
        print(f"[错误] {exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[退出]")
