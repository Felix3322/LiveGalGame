# Voice-Galgame Agent (with YOLO Gender Check)

本项目是一个集【真人摄像头画面】【AI语音剧情】【YOLO性别识别】【Galgame原汁原味UI】于一体的浏览器互动系统。
- 支持切换前后摄像头，画面实时渲染为Galgame背景
- 支持实时语音识别，字幕像真正Galgame一样逐字打印+剧情分支
- 检测“吗”等疑问句自动调用GPT生成对话选项
- **集成YOLO性别识别**，如果主角不是女的，弹窗恶搞警告

---

## 主要功能

1. **摄像头Galgame背景+角色立绘**
    - 可选自定义立绘，UI全仿日系AVG
2. **实时ASR字幕+剧情分支**
    - 用Vosk流式识别
    - “吗”触发GPT
    - UI多分支对话框
3. **YOLO性别识别**
    - 定时抽帧canvas，推给后端YOLO服务
    - 目标检测+性别分类
    - 若不是女，弹窗：“小心我把你送到成都”

---

## 技术架构

前端(JS/HTML)        <—视频/音频—>         后端API(Flask/FastAPI)
├─ getUserMedia(摄像头/麦克风)
├─ video + canvas  ←——→  YOLOv5 RESTful
├─ WebSocket音频  ←——→  Vosk流式ASR
└─ GPT分支API     ←——→  OpenAI/本地LLM

---

## 性别识别服务说明

- 前端定时将摄像头画面用canvas抽帧成JPEG/png
- POST到 `/yolo_gender` 接口
- YOLO返回主区域的人脸性别(女/男/置信度)
- 前端收到不是女性，自动弹窗

YOLO后端推荐：
- yolov5 + gender_classification.py
- ultralytics/YOLOv8 +自训练gender head
- 或自选轻量open source性别模型

API样例返回：
```json
{
  "class": "male",
  "confidence": 0.91
}


⸻

UI和交互规范
	•	背景: 实时摄像头画面，全屏
	•	立绘: PNG透明层覆盖，人物左右站位可切换
	•	对话框: 底部大半透明带头像，文字逐字打印，带姓名
	•	选项: Galgame样式分支（圆角框/渐变/浮动）
	•	弹窗: 非女性时居中弹出红色警告框，文案：“小心我把你送到成都”

⸻

目录结构建议

/
│ index.html       # Galgame主页面
│ agent.js         # UI/ASR/YOLO/分支总逻辑
│ styles.css       # Galgame风格CSS
│立绘/            # PNG角色图层
│
└─ server/
    │ server.py    # Vosk流式+GPT分支
    │ yolo_api.py  # YOLO性别检测API
    │ model-cn/    # Vosk中文模型
    │ yolov5/      # YOLO模型文件
    └ config.json  # API KEY/参数


⸻

各服务API规范
	•	/ws_asr   → 音频WebSocket实时字幕
	•	/gpt      → POST文本返回分支选项
	•	/yolo_gender → POST图片返回性别/置信度

⸻

示例前端伪代码（性别识别部分）

async function checkGender() {
    // 定时canvas截图推送YOLO
    let canvas = document.createElement('canvas');
    let video = document.getElementById('cam');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    let blob = await new Promise(res => canvas.toBlob(res, 'image/jpeg'));
    let resp = await fetch('/yolo_gender', {
        method: 'POST',
        body: blob
    });
    let result = await resp.json();
    if(result.class !== 'female' && result.confidence > 0.7) {
        showAlert('小心我把你送到成都');
    }
}
setInterval(checkGender, 3000);


⸻

扩展方向
	•	角色声线识别（区分男女说话）
	•	剧情树持久化，自动保存分支
	•	选项影响后续剧情（记忆flag）
	•	多人互动同屏（多人镜头）

⸻

“恶搞Galgame，现实变AVG”

项目本质：
	•	真人摄像头实时背景
	•	语音驱动剧情分支
	•	AI自动生成对话选项
	•	实时鉴别主角性别，不女就警告

“现实世界变AVG”，全程AI自动主导，无需剧本。

---

**再提醒：YOLO部分必须有服务端模型，不能全部前端实现。你只需定时canvas截图POST图片到后端就能用。**
