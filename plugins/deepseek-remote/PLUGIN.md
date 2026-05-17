---
name: deepseek-remote
description: DeepSeek TUI 远程控制桥接插件 —— 在 PC 上启动 WebSocket 服务器，允许手机 APP 远程监控终端、发送指令并接收结果。
status: draft
---

# DeepSeek Remote 插件

让手机通过局域网远程控制 DeepSeek TUI 终端。

## 功能

- 启动 WebSocket 桥接服务器（`bridge/bridge_server.py`）
- 接受手机 APP 连接
- 远程执行 shell 命令并流式返回结果
- 未来：中继 DeepSeek TUI 对话

## 激活方式

当前为草稿阶段。手动启动桥接服务器：

```bash
cd bridge/
pip install -r requirements.txt
python bridge_server.py --port 9876
```

然后在手机上安装配套 Android APP（位于项目 `app/` 目录），输入 PC 的 IP 地址和端口连接即可。

## 未来集成

当 DeepSeek TUI 支持插件自动加载后，此插件可直接在 TUI 内部启动桥接服务器，
并将手机端的 chat 消息中继到 TUI 对话管道。
