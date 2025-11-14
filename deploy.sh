#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")" && pwd)
VENV_PATH="$PROJECT_ROOT/.venv"

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[deploy] 未检测到 ffmpeg，尝试自动安装..."
    if command -v apt-get >/dev/null 2>&1; then
        if command -v sudo >/dev/null 2>&1; then
            sudo apt-get update
            sudo apt-get install -y ffmpeg
        else
            apt-get update
            apt-get install -y ffmpeg
        fi
    else
        echo "[deploy] 无法自动安装 ffmpeg，请手动安装后重试。" >&2
        exit 1
    fi
fi

if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
fi

# shellcheck disable=SC1090
source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install -r "$PROJECT_ROOT/requirements.txt"

export PYTHONPATH="$PROJECT_ROOT"
uvicorn server.server:app --host 0.0.0.0 --port "${PORT:-8000}"
