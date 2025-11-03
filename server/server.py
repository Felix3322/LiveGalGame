"""Live Galgame 后端服务。

该 FastAPI 应用负责：
1. `/ws_asr` WebSocket：接收浏览器发送的音频流，调用 Vosk 识别
   （默认提供占位逻辑，方便快速启动）。
2. `/gpt` POST：根据语音文本生成剧情分支，可接入 OpenAI 或本地 LLM。
3. `/yolo_gender` POST：使用 YOLO 模型进行性别检测。

实际部署时，请将 `VoskStreamingRecognizer` 与 `GenderClassifier`
替换为真实的模型实例。本文件提供了清晰的挂钩点和注释，便于拓展。
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import Body, FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .yolo_api import GenderClassifier


class GPTRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, description="最新一句话文本")
    option: Optional[str] = Field(default=None, description="选项 ID")
    history: Optional[str] = Field(default=None, description="历史上下文")


class GPTResponse(BaseModel):
    text: str
    speaker: str = "系统"
    options: list[dict[str, Any]] = Field(default_factory=list)


class DummyBranchEngine:
    """一个简单的剧情生成占位实现。

    实际环境下，可以用 OpenAI、ChatGLM 等模型替换。
    """

    fallback_options = [
        {"id": "comfort", "text": "安慰她"},
        {"id": "joke", "text": "讲个冷笑话"},
        {"id": "silence", "text": "保持沉默"},
    ]

    def build_reply(self, request: GPTRequest) -> GPTResponse:
        if request.option:
            text = f"你选择了选项：{request.option}。剧情将在此基础上继续展开。"
            speaker = "系统"
        else:
            prompt = request.prompt or request.history or ""
            if prompt:
                text = f"听到你说：{prompt}\n（接入 GPT 后可替换为模型生成的剧情回复）"
            else:
                text = "说点什么来触发分支吧～"
            speaker = "AI同伴"
        return GPTResponse(text=text, speaker=speaker, options=self.fallback_options)


class VoskStreamingRecognizer:
    """Vosk 流式识别包装。

    如果本地未安装 `vosk` 或者没有模型，本类会回退到占位实现。
    当具备模型时，可将 `MODEL_PATH` 指向 Vosk 模型目录。
    """

    def __init__(self, model_path: Optional[str] = None, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self._available = False
        self._notified_placeholder = False
        self._recognizer = None

        if model_path and Path(model_path).exists():
            try:
                from vosk import KaldiRecognizer, Model  # type: ignore

                model = Model(model_path)
                self._recognizer = KaldiRecognizer(model, sample_rate)
                self._recognizer.SetWords(True)
                self._available = True
            except Exception as exc:  # pragma: no cover - 取决于外部依赖
                print(f"[ASR] 无法加载 Vosk 模型: {exc}")

    async def accept_audio(self, data: bytes) -> AsyncIterator[str]:
        if not data:
            return

        if not self._available:
            if not self._notified_placeholder:
                self._notified_placeholder = True
                yield "（语音识别占位，安装 Vosk 模型以获得真实字幕）"
            return

        if self._recognizer.AcceptWaveform(data):
            result = json.loads(self._recognizer.Result())
            text = result.get("text", "").strip()
            if text:
                yield text
        else:
            partial = json.loads(self._recognizer.PartialResult()).get("partial")
            if partial:
                yield partial


MODEL_PATH = os.environ.get("VOSK_MODEL_PATH")
branch_engine = DummyBranchEngine()
recognizer = VoskStreamingRecognizer(model_path=MODEL_PATH)
gender_classifier = GenderClassifier(weights=os.environ.get("YOLO_WEIGHTS"))

app = FastAPI(title="Live Galgame Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws_asr")
async def ws_asr(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            data = message.get("bytes")
            if data is None:
                continue

            async for text in recognizer.accept_audio(data):
                payload = {"text": text, "speaker": "主角"}
                await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()


@app.post("/gpt", response_model=GPTResponse)
async def gpt_endpoint(request: GPTRequest = Body(...)) -> GPTResponse:
    return branch_engine.build_reply(request)


@app.post("/yolo_gender")
async def yolo_gender(file: UploadFile = File(...)) -> dict[str, Any]:
    image_bytes = await file.read()
    result = gender_classifier.classify(image_bytes)
    return result.to_dict()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
