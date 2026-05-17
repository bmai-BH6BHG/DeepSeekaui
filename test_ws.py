"""
综合测试：验证 PC 端 ↔ 手机端对话同步
1. 客户端A 发送消息
2. 客户端B 连接，检查是否能收到 sync_full（完整历史）
3. 客户端A 再发一条，客户端B 是否收到 sync_message
"""
import asyncio, websockets, json, sys

URI = "ws://127.0.0.1:9876"
PASS = 0
FAIL = 0

def ok(msg):
    global PASS; PASS += 1
    print(f"  [PASS] {msg}")

def fail(msg):
    global FAIL; FAIL += 1
    print(f"  [FAIL] {msg}")

async def client_a():
    async with websockets.connect(URI) as ws:
        raw = await ws.recv()
        d = json.loads(raw)
        assert d["type"] == "status"
        ok("客户端A 收到 welcome status")

        raw2 = await ws.recv()
        d2 = json.loads(raw2)
        if d2["type"] == "sync_full":
            ok(f"客户端A 收到 sync_full ({len(d2.get('history',[]))} 条)")

        await ws.send(json.dumps({"type": "chat", "message": "Say OK in 1 word"}))
        ok("客户端A 发送 chat 消息")

        full = ""
        done = False
        has_sync = False
        while not done:
            raw = await ws.recv()
            msg = json.loads(raw)
            t = msg["type"]
            if t == "output" and msg.get("stream") == "chat":
                full += msg.get("data", "")
            elif t == "sync_message":
                has_sync = True
            elif t == "chat_response":
                done = True
                tok = msg.get("token_usage", {})
                ok(f"客户端A 收到 chat_response ({len(full)} chars)")
        if has_sync:
            ok("客户端A 收到自己的 sync_message 广播")
        return full

async def client_b():
    async with websockets.connect(URI) as ws:
        raw = await ws.recv()
        d = json.loads(raw)
        assert d["type"] == "status"
        ok("客户端B 收到 welcome status")

        raw2 = await ws.recv()
        d2 = json.loads(raw2)
        assert d2["type"] == "sync_full"
        history = d2.get("history", [])
        if len(history) >= 2:
            ok(f"客户端B 收到 sync_full: {len(history)} 条历史消息")
            for m in history:
                print(f"       [{m.get('role','')[:4]}] {m.get('content','')[:60]}")
        else:
            fail(f"sync_full 历史不足 ({len(history)}条)")
        return ws

async def main():
    print("=" * 55)
    print("  DeepSeek Remote 同步测试")
    print("=" * 55)
    print()

    print("[Step 1] 客户端A 连接并发送消息...")
    await client_a()
    print()

    print("[Step 2] 客户端B 连接，验证历史同步...")
    ws_b = await client_b()
    print()

    print("[Step 3] 客户端A 再发一条，验证客户端B 收到广播...")
    async with websockets.connect(URI) as ws_a2:
        await ws_a2.recv()
        await ws_a2.recv()
        await ws_a2.send(json.dumps({"type": "chat", "message": "Say TWO in 1 word"}))
        ok("客户端A 发送第二条消息")

        try:
            raw_b = await asyncio.wait_for(ws_b.recv(), timeout=8)
            msg_b = json.loads(raw_b)
            if msg_b["type"] == "sync_message":
                ok(f"客户端B 收到 sync_message: [{msg_b['role']}] {msg_b['content'][:50]}")
            elif msg_b["type"] == "output":
                ok("客户端B 收到流式输出广播")
        except asyncio.TimeoutError:
            fail("客户端B 未收到 sync_message 广播（超时）")
        finally:
            await ws_b.close()

    print()
    print("=" * 55)
    print(f"  结果: {PASS} passed, {FAIL} failed")
    print("=" * 55)
    return 1 if FAIL > 0 else 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
