"""Live Galgame 后端服务。

该 FastAPI 应用负责：
1. `/ws_asr` WebSocket：接收浏览器发送的音频流，并通过 Whisper 模型
   实时转写字幕。
2. `/gpt` POST：根据语音文本调用 OpenAI Chat Completions API 生成剧情分支。
3. `/yolo_gender` POST：使用 YOLO 模型或其他检测器进行性别检测。

相比占位实现，本模块内置了真实可用的推理逻辑：

* `WhisperStreamingRecognizer` 通过 `faster-whisper` 加载 Whisper 模型，
  自动调用 `ffmpeg` 将浏览器发送的 WebM 音频转码为 16kHz WAV，再执行
  语音识别。若缺少模型或 `ffmpeg`，会降级输出提示信息。
* `BranchEngine` 在检测到 `OPENAI_API_KEY` 后会直接请求 OpenAI Chat
  Completions 服务，并根据回复动态生成 Galgame 风格的分支选项；若未
  配置 API Key，则回退到内建的分支模板。

因此只要准备好 Whisper 模型权重（或使用默认的 `small`）并设置好
OpenAI Key，整个后端即可开箱即用。
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from typing import Any, AsyncIterator, Optional

from fastapi import (
    Body,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
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


class BranchEngine:
    """剧情分支引擎。

    当检测到 ``OPENAI_API_KEY`` 环境变量时，会自动调用 OpenAI Chat
    Completions API；否则回退到预置的 Galgame 分支模板。
    """

    fallback_options = [
        {"id": "comfort", "text": "轻声安慰她"},
        {"id": "joke", "text": "装作没事讲个冷笑话"},
        {"id": "silence", "text": "只是静静陪在身旁"},
    ]

    def __init__(self) -> None:
        self._client = None
        self._model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
        self._base_url = os.environ.get("OPENAI_BASE_URL")
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            try:
                from openai import AsyncOpenAI  # type: ignore

                self._client = AsyncOpenAI(api_key=api_key, base_url=self._base_url)
            except Exception as exc:  # pragma: no cover - 取决于外部依赖
                print(f"[BranchEngine] 初始化 OpenAI 客户端失败: {exc}")

    async def build_reply(self, request: GPTRequest) -> GPTResponse:
        if request.option:
            text = f"你选择了分支【{request.option}】，剧情的因果正在悄然改变。"
            return GPTResponse(text=text, speaker="系统", options=self.fallback_options)

        prompt = (request.prompt or request.history or "").strip()
        if not prompt:
            return GPTResponse(
                text="说点什么吧，只有这样我才能感知你的心情～",
                speaker="AI同伴",
                options=self.fallback_options,
            )

        if not self._client:
            text = f"听到了：{prompt}\n等你配置 OPENAI_API_KEY 后，我会给出更像 Galgame 的即兴剧情。"
            return GPTResponse(text=text, speaker="AI同伴", options=self.fallback_options)

        options = self._build_dynamic_options(prompt)
        text = await self._call_openai(prompt, options, history=request.history)
        return GPTResponse(text=text, speaker="AI同伴", options=options)

    async def _call_openai(self, prompt: str, options: list[dict[str, str]], *, history: Optional[str]) -> str:
        assert self._client is not None
        system_prompt = (
            "你是一款实时 Galgame 的剧情引擎，需要把玩家的语音转成代入感极强的" "对话回复，语气偏轻小说风格，长度 2~3 句。"
        )
        history_text = history or ""
        user_prompt = (
            "玩家刚刚说：" + prompt + (f"\n之前的记录：{history_text}" if history_text else "")
        )

        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.9,
                max_tokens=220,
            )
            return completion.choices[0].message.content.strip()
        except Exception as exc:  # pragma: no cover - 依赖外部 API
            print(f"[BranchEngine] OpenAI 调用失败: {exc}")
            return "网络有点不稳，我暂时没能接上星界的剧情管道……"

    def _build_dynamic_options(self, prompt: str) -> list[dict[str, str]]:
        lowered = prompt.lower()
        if any(word in lowered for word in ["为什么", "怎么", "吗", "?", "？"]):
            return [
                {"id": "ask_more", "text": "继续追问细节"},
                {"id": "switch", "text": "耍赖，换个话题"},
                {"id": "promise", "text": "郑重其事地承诺"},
            ]
        if any(word in lowered for word in ["开心", "好耶", "太棒了", "great"]):
            return [
                {"id": "celebrate", "text": "一起庆祝"},
                {"id": "tease", "text": "调皮地吐槽"},
                {"id": "plan", "text": "约定下一步"},
            ]
        return self.fallback_options


class WhisperStreamingRecognizer:
    """接收浏览器发来的 WebM 音频切片并转写。

    识别流程：

    1. 将 WebM/Opus 数据写入临时文件；
    2. 通过 `ffmpeg` 转码为 16kHz/mono WAV；
    3. 使用 `faster-whisper` 执行推理并返回文本。
    """

    def __init__(
        self,
        *,
        model_size: str = "small",
        device: str = "auto",
        min_chunk_size: int = 20_000,
        language: Optional[str] = None,
    ) -> None:
        self.sample_rate = 16000
        self.min_chunk_size = min_chunk_size
        self.language = language
        self._buffer = bytearray()
        self._lock = asyncio.Lock()
        self._notified_placeholder = False
        self._available = False
        self._ffmpeg_ok = shutil.which("ffmpeg") is not None

        try:
            from faster_whisper import WhisperModel  # type: ignore

            compute_type = os.environ.get("WHISPER_COMPUTE_TYPE")
            if compute_type is None:
                compute_type = "int8_float16" if device != "cpu" else "int8"
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
            )
            if self._ffmpeg_ok:
                self._available = True
            else:
                print("[ASR] 未检测到 ffmpeg，可执行文件是必须的。")
        except Exception as exc:  # pragma: no cover - 依赖外部环境
            self._model = None
            print(f"[ASR] 初始化 Whisper 模型失败: {exc}")

    async def accept_audio(self, data: bytes) -> AsyncIterator[str]:
        if not data:
            return

        if not self._available:
            if not self._notified_placeholder:
                self._notified_placeholder = True
                yield "（语音识别未就绪，请检查 ffmpeg 与 Whisper 模型）"
            return

        self._buffer.extend(data)
        if len(self._buffer) < self.min_chunk_size:
            return

        if self._lock.locked():
            # Whisper 正在处理上一块音频，避免堆积
            return

        chunk = bytes(self._buffer)
        self._buffer.clear()

        async with self._lock:
            text = await asyncio.to_thread(self._transcribe_chunk, chunk)

        if text:
            yield text

    def _transcribe_chunk(self, chunk: bytes) -> str:
        if not chunk:
            return ""

        assert self._model is not None
        src_fd, src_path = tempfile.mkstemp(suffix=".webm")
        dst_fd, dst_path = tempfile.mkstemp(suffix=".wav")
        try:
            with os.fdopen(src_fd, "wb") as src_file:
                src_file.write(chunk)

            os.close(dst_fd)
            cmd = [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                src_path,
                "-ac",
                "1",
                "-ar",
                str(self.sample_rate),
                dst_path,
            ]
            subprocess.run(cmd, check=True)

            segments, _ = self._model.transcribe(
                dst_path,
                beam_size=3,
                temperature=0.2,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                language=self.language,
            )
            text_parts = [segment.text.strip() for segment in segments if segment.text]
            return " ".join(text_parts).strip()
        except subprocess.CalledProcessError as exc:
            print(f"[ASR] ffmpeg 转码失败: {exc}")
            return ""
        finally:
            for path in (src_path, dst_path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE")

branch_engine = BranchEngine()
recognizer = WhisperStreamingRecognizer(
    model_size=WHISPER_MODEL_SIZE,
    device=WHISPER_DEVICE,
    language=WHISPER_LANGUAGE,
)
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
    return await branch_engine.build_reply(request)


@app.post("/yolo_gender")
async def yolo_gender(file: UploadFile = File(...)) -> dict[str, Any]:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="未收到有效的图像数据")
    result = gender_classifier.classify(image_bytes)
    return result.to_dict()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
