<p align="center">
  <img src="https://img.shields.io/badge/Android-3DDC84?style=for-the-badge&amp;logo=android&amp;logoColor=white" alt="Android"/>
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&amp;logo=python&amp;logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/WebSocket-4A4A55?style=for-the-badge&amp;logo=socket.io&amp;logoColor=white" alt="WebSocket"/>
  <img src="https://img.shields.io/badge/DeepSeek-4F46E5?style=for-the-badge&amp;logo=deepseek&amp;logoColor=white" alt="DeepSeek"/>
</p>

<h1 align="center">DeepSeek Remote</h1>

<p align="center">
  <b>Remote control your DeepSeek TUI terminal from your Android phone.</b><br>
  Chat with DeepSeek AI, monitor system resources, browse files,<br>
  and run shell commands — all from the palm of your hand.
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-components">Components</a> •
  <a href="#-protocol">Protocol</a> •
  <a href="#-tech-stack">Tech Stack</a>
</p>

<br>

---

## ✦ Features

| | Capability | Details |
|---|---|---|
| 💬 | **AI Chat Relay** | Talk to DeepSeek V4 from your phone. Messages are relayed through the bridge server and streamed back token by token. |
| 📊 | **System Monitor** | Real-time CPU, memory, disk, and network usage from your PC — updated every 3 seconds. |
| 📂 | **Remote File Browser** | Navigate directories, read files, and browse the remote filesystem from your phone. |
| 🔄 | **Multi-Client Sync** | The bridge server maintains a shared conversation. Connect your phone AND a PC terminal — both see the same chat history in real time. |
| 🌐 | **ngrok / Public Access** | Expose the bridge server over the internet via ngrok (wss://). Connect from anywhere. |
| 💳 | **Top-Up Shortcut** | In-app WebView to the DeepSeek platform billing page for quick API credit top-ups. |
| 💾 | **Local History** | Chat messages are persisted in SQLite on the phone. History survives app restarts. |

---

## ✦ Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        YOUR PC                                │
│                                                               │
│  ┌──────────────────────┐         ┌─────────────────────────┐ │
│  │   deepseek-tui CLI   │         │   Bridge Server         │ │
│  │   (deepseek-tui-     │         │   (Python / WebSocket)  │ │
│  │    windows-x64.exe)  │         │   port :9876             │ │
│  └──────────┬───────────┘         └──────────┬──────────────┘ │
│             │                                │                │
│             └─────── (future plugin) ────────┘                │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │   PC Client (pc_client.py)                              │  │
│  │   Terminal-based chat via bridge                        │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                              ▲                │
└──────────────────────────────────────────────┼────────────────┘
                                               │
                                  WebSocket (ws:// or wss://)
                                               │
                                               ▼
┌──────────────────────────────────────────────────────────────┐
│                     YOUR ANDROID PHONE                        │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│   DeepSeek Remote App                                       │
│   ┌─────────┐ ┌──────────┐ ┌────────┐ ┌───────────┐       │
│   │  Chat   │ │ Monitor  │ │  File  │ │ Recharge  │       │
│   │  Tab    │ │  Tab     │ │  Tab   │ │   Tab     │       │
│   └─────────┘ └──────────┘ └────────┘ └───────────┘       │
│                         │                                   │
│              WebSocketManager (OkHttp)                      │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Phone  ──chat message──▶  Bridge Server  ──API call──▶  DeepSeek API
                                                   │
Phone  ◀──stream tokens──  Bridge Server  ◀──stream───┘

Phone  ──monitor request──▶  Bridge Server  ──psutil──▶  System Stats
Phone  ◀──CPU/Mem/Disk────  Bridge Server

Phone  ──ls/read─────────▶  Bridge Server  ──os──▶  Filesystem
Phone  ◀──file list──────  Bridge Server
```

---

## ✦ Quick Start

### 1. Start the Bridge Server

```bash
cd bridge/
pip install -r requirements.txt

# Basic mode — standalone relay
python bridge_server.py --port 9876

# Or point it at your deepseek-tui binary (for future plugin integration)
python bridge_server.py --deepseek ./deepseek-tui-windows-x64.exe --port 9876
```

### 2. Connect the Android App

- Open the app on your phone
- Tap the status bar to open the connection dialog
- **LAN**: enter your PC's IP address and port `9876`
- **ngrok**: enter your ngrok tunnel domain (e.g. `xxx.ngrok-free.app`) and port `443`

### 3. Start Chatting

Once connected, type a message on either the phone or the PC client — it syncs to all connected devices in real time.

---

## ✦ Components

### Android App (`app/`)

| Tab | Description | Key Files |
|---|---|---|
| 💬 **Chat** | Full AI chat interface with streaming responses, token usage display, and SQLite history. | `ChatFragment.java`, `ChatAdapter.java`, `ChatDatabaseHelper.java` |
| 📊 **Monitor** | Live system resource monitoring (CPU, memory, disk, network, uptime) with auto-refresh every 3 seconds. | `MonitorFragment.java` |
| 📂 **File** | Remote file browser with directory navigation and file preview. | `FileBrowserFragment.java`, `FileListAdapter.java` |
| 💳 **Recharge** | WebView wrapper for the DeepSeek platform top-up page. | `RechargeFragment.java` |

**Key Android classes:**

- **`WebSocketManager`** — Singleton WebSocket connection handler built on OkHttp. Manages connection lifecycle, JSON message dispatch, and a multi-listener callback system. Supports both `ws://` (LAN) and `wss://` (ngrok) connections.
- **`ChatDatabaseHelper`** — SQLite persistence layer for chat messages. Survives app restarts.
- **`ChatMessage`** — Data model for chat entries (user, model, system).
- **`SystemStats`** — Parsed system monitoring data from the bridge server.
- **`TokenUsage`** — Token counting and cost estimation (DeepSeek V4 pricing model).

### Bridge Server (`bridge/`)

| File | Purpose |
|---|---|
| `bridge_server.py` | Core WebSocket relay server (~720 lines). Handles chat, exec, monitor, file I/O, and sync protocols. |
| `pc_client.py` | Terminal-based Python client that connects to the bridge. Same chat experience as the phone. |
| `launcher.py` | Launch script for the bridge server. |
| `api_test.py` | Quick HTTP endpoint scanner for local API discovery. |
| `explore_api.py` | Extended API path exploration utility. |
| `test_ws.py` | Integration test for multi-client sync verification. |
| `run_server.bat` | One-click Windows launcher for the bridge server. |
| `ngrok_tunnel.bat` | Start an ngrok TCP tunnel to port 9876. |

**Bridge protocol messages:**

| Type | Direction | Purpose |
|---|---|---|
| `chat` | Client → Server | Send a message to DeepSeek AI |
| `output` | Server → Client | Streaming chat token |
| `chat_response` | Server → Client | Final chat response with token usage |
| `monitor` | Client → Server | Request system stats |
| `monitor_data` | Server → Client | CPU, memory, disk, network data |
| `exec` | Client → Server | Execute a shell command |
| `ls` | Client → Server | List directory contents |
| `read` | Client → Server | Read a file |
| `work` | Client → Server | Request active task/work status |
| `sync_message` | Server → All | Broadcast a new message to all clients |
| `sync_full` | Server → Client | Send full conversation history on connect |
| `status` | Client → Server | Ping / get server info |
| `ping` / `pong` | Both | Keepalive |
| `error` | Server → Client | Error notification |

### Plugin (`plugins/deepseek-remote/`)

A draft plugin for DeepSeek TUI's native plugin system. Once the TUI supports plugin auto-loading, the bridge server can be started directly from within the terminal interface.

---

## ✦ System Monitor Data

The monitor tab displays:

```
CPU:     ████████████████████░░ 45.2%  16 cores (8 physical)
Memory:  ████████████████░░░░░░ 50.0%  32.0 GB / 64.0 GB
Disk:    ██████████░░░░░░░░░░░░ 25.1%  256.7 GB / 1.0 TB
Network: ↑ 1.2 GB  ↓ 3.8 GB
Uptime:  14d 6h
```

Data refreshes automatically every 3 seconds while the tab is visible.

---

## ✦ Tech Stack

**Android App**
- Java 11 + Android SDK 36 (minSdk 28)
- Material Design 3 — terminal-inspired dark theme
- OkHttp 4.12 — WebSocket client
- Gson 2.10 — JSON serialization
- SQLite — local message persistence
- AndroidX (AppCompat, Activity, ConstraintLayout, RecyclerView, Lifecycle)

**Bridge Server**
- Python 3.10+
- `websockets` 13.1 — async WebSocket server
- `psutil` 7.2 — system monitoring (optional)
- DeepSeek Chat Completions API (streaming)

**Infrastructure**
- ngrok — public tunnel for remote access
- Gradle 9.x + AGP 9.1.1

---

## ✦ Development

### Building the Android App

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/deepseekaui.git
cd deepseekaui

# Build with Gradle
./gradlew assembleDebug

# The APK will be at:
# app/build/outputs/apk/debug/app-debug.apk
```

### Running Tests

```bash
# Start the bridge server
cd bridge
python bridge_server.py --port 9876

# In another terminal, run the sync test
python test_ws.py
```

---

## ✦ License

Distributed under the MIT License. See `LICENSE` for more information.

---

<p align="center">
  <sub>Built with ♥ to make DeepSeek TUI accessible from anywhere.</sub>
</p>
