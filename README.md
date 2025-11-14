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

### 一键部署脚本

项目根目录新增了 `deploy.sh`，它会：

1. 检查并自动安装 `ffmpeg`（Whisper 转码所需）；
2. 创建/复用 `.venv` 虚拟环境；
3. 安装 `requirements.txt` 中列出的依赖（FastAPI、faster-whisper、OpenAI SDK、Ultralytics 等）；
4. 启动 `uvicorn server.server:app`。

使用方式：

```bash
chmod +x deploy.sh
./deploy.sh
```

> 默认监听 `0.0.0.0:8000`，可通过 `PORT` 环境变量覆盖。

### 环境变量

| 变量名 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | （可选）提供后 `/gpt` 会实时调用 OpenAI Chat Completions，并生成 Galgame 风格分支。 |
| `OPENAI_MODEL` | 默认 `gpt-3.5-turbo`，可指定其他 Chat Completions 模型。 |
| `OPENAI_BASE_URL` | 对接 Azure/OpenAI 兼容代理时可设置。 |
| `WHISPER_MODEL_SIZE` | Whisper 模型尺寸，默认为 `small`，可改为 `base`/`medium` 等。 |
| `WHISPER_DEVICE` | `auto`/`cpu`/`cuda`，决定 faster-whisper 的推理设备。 |
| `WHISPER_LANGUAGE` | （可选）指定语言代码，可加速推理。 |
| `YOLO_WEIGHTS` | Ultralytics 权重路径，配置后 `/yolo_gender` 将调用真实模型。 |

前端仍可通过任意静态资源服务器托管：

```bash
python -m http.server 5173
```

浏览器访问 `http://localhost:5173`，即可与后端交互。

## 模型接入说明

- **Whisper ASR**：`WhisperStreamingRecognizer` 使用 `faster-whisper` + `ffmpeg` 将 MediaRecorder 发送的 WebM 片段转写为文本。音频缓冲达到 20KB 即触发识别。若缺少模型或 `ffmpeg`，会输出占位提示。
- **OpenAI 剧情引擎**：`BranchEngine` 检测到 `OPENAI_API_KEY` 后会调用 Chat Completions API，根据玩家语音生成 2~3 句 Galgame 风格回复，并结合意图自动给出 3 个分支选项。
- **YOLO 性别识别**：`GenderClassifier` 默认调用 `ultralytics.YOLO` 推理，若未提供权重会退回一个置信度较高的女性结果，以避免误报造成骚扰。

## TODO（扩展方向）

- 集成真正的对话大模型，实现上下文剧情生成。
- 补充存档系统，让选项影响后续剧情。
- 多人摄像头与角色声线识别。
