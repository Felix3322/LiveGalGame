# Live Galgame Agent

一个将现实摄像头画面、语音剧情、YOLO 性别识别和 Galgame UI 融合到一起的原型项目。

## 功能概览

- 🎥 **实时摄像头背景**：支持前后摄像头切换，画面自动铺满背景。
- 🖼️ **角色立绘系统**：上传透明 PNG 立绘，左右站位随时切换。
- 🗣️ **语音字幕**：浏览器采集麦克风音频，通过 WebSocket 推送后端进行识别，字幕逐字打印。
- 🤖 **自动剧情分支**：识别到疑问句自动请求 `/gpt` 接口获取 Galgame 样式选项。
- 🚨 **YOLO 性别警告**：定时截图发送 `/yolo_gender`，若置信度高且非女性即弹窗“送你去成都”。

## 目录结构

```
/
├── index.html          # Galgame 主界面
├── agent.js            # 前端核心逻辑
├── styles.css          # UI 样式
└── server/
    ├── server.py       # FastAPI 后端（ASR / GPT / YOLO 接口）
    └── yolo_api.py     # YOLO 性别识别封装
```

## 快速启动

### 1. 启动后端

```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi[all] uvicorn
python -m server.server
```

可选：
- 安装 `vosk` 并将模型路径写入 `VOSK_MODEL_PATH` 环境变量，可获得真实语音识别。
- 安装 `ultralytics` 并设置 `YOLO_WEIGHTS` 环境变量，即可启用 YOLO 性别识别。

### 2. 启动前端

使用任意静态资源服务器，例如：

```bash
python -m http.server 5173
```

然后浏览器打开 `http://localhost:5173`。

> 若通过 `http.server` 提供静态文件，请确保反向代理或浏览器允许跨域访问后端（默认 FastAPI 已开启 CORS）。

## 模型接入说明

- **Vosk ASR**：`VoskStreamingRecognizer` 中包含占位逻辑，真实部署时请将 MediaRecorder 推送的 WebM 转换为 PCM 后再交给 Vosk。
- **YOLO**：`GenderClassifier` 默认返回 `female`，以避免误报。传入权重后会自动调用 `ultralytics.YOLO` 进行推理。

## TODO（扩展方向）

- 集成真正的对话大模型，实现上下文剧情生成。
- 补充存档系统，让选项影响后续剧情。
- 多人摄像头与角色声线识别。
