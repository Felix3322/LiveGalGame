const cameraFeed = document.getElementById('camera-feed');
const spriteImage = document.getElementById('sprite');
const switchCameraBtn = document.getElementById('switch-camera');
const spritePositionSelect = document.getElementById('sprite-position');
const spriteFileInput = document.getElementById('sprite-file');
const subtitleSpan = document.getElementById('subtitle');
const cursorSpan = document.getElementById('type-cursor');
const namePlate = document.getElementById('speaker-name');
const optionsContainer = document.getElementById('options');
const optionTemplate = document.getElementById('option-template');
const genderWarning = document.getElementById('gender-warning');
const closeWarningBtn = document.getElementById('close-warning');

let mediaStream = null;
let facingMode = 'user';
let genderIntervalId = null;
let asrSocket = null;
let mediaRecorder = null;
let typewriterController = null;
let latestTranscript = '';

const TYPE_SPEED = 32;
const GENDER_CHECK_INTERVAL = 3000;
const QUESTION_TRIGGER_PATTERN = /[?？吗麼嘛呢吧]/;

function log(...args) {
    console.debug('[Agent]', ...args);
}

async function initCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
        alert('当前浏览器不支持摄像头访问');
        return;
    }

    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode },
            audio: true,
        });
        cameraFeed.srcObject = mediaStream;
        startAudioStreaming(mediaStream);
        startGenderGuard();
    } catch (err) {
        console.error('获取摄像头失败', err);
        alert('无法访问摄像头/麦克风: ' + err.message);
    }
}

async function switchCamera() {
    facingMode = facingMode === 'user' ? 'environment' : 'user';
    if (mediaStream) {
        mediaStream.getTracks().forEach((track) => track.stop());
    }
    await initCamera();
}

function applySpritePosition(position) {
    spriteImage.classList.remove('left', 'right');
    spriteImage.classList.add(position);
}

spritePositionSelect.addEventListener('change', (event) => {
    applySpritePosition(event.target.value);
});

spriteFileInput.addEventListener('change', (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    spriteImage.src = url;
    spriteImage.hidden = false;
});

switchCameraBtn.addEventListener('click', () => {
    switchCamera().catch((err) => console.error(err));
});

closeWarningBtn.addEventListener('click', () => {
    genderWarning.classList.add('hidden');
});

function typewrite(text) {
    if (typewriterController) {
        typewriterController.abort();
    }

    subtitleSpan.textContent = '';
    cursorSpan.style.visibility = 'visible';

    const controller = new AbortController();
    typewriterController = controller;

    (async () => {
        for (const char of text) {
            if (controller.signal.aborted) return;
            subtitleSpan.textContent += char;
            await new Promise((resolve) => setTimeout(resolve, TYPE_SPEED));
        }
        cursorSpan.style.visibility = 'hidden';
    })();
}

function setOptions(options) {
    optionsContainer.innerHTML = '';
    if (!Array.isArray(options) || !options.length) return;

    options.forEach((option) => {
        const button = optionTemplate.content.firstElementChild.cloneNode(true);
        button.textContent = option.text;
        button.addEventListener('click', () => handleOptionSelected(option));
        optionsContainer.appendChild(button);
    });
}

async function handleOptionSelected(option) {
    log('Option selected', option);
    try {
        const response = await fetch('/gpt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ option: option.id, history: latestTranscript }),
        });
        if (!response.ok) throw new Error('选项提交失败');
        const data = await response.json();
        updateDialogue(data.text ?? '……', data.speaker ?? '系统');
        setOptions(data.options ?? []);
    } catch (error) {
        console.error(error);
    }
}

function updateDialogue(text, speaker = '？？？') {
    namePlate.textContent = speaker;
    typewrite(text);
}

function startAudioStreaming(stream) {
    if (mediaRecorder) {
        mediaRecorder.stop();
        mediaRecorder = null;
    }
    if (asrSocket) {
        asrSocket.close();
        asrSocket = null;
    }

    try {
        const audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        const destination = audioContext.createMediaStreamDestination();
        source.connect(destination);

        mediaRecorder = new MediaRecorder(destination.stream, { mimeType: 'audio/webm' });
        const wsUrl = `${location.origin.replace(/^http/, 'ws')}/ws_asr`;
        asrSocket = new WebSocket(wsUrl);

        asrSocket.binaryType = 'arraybuffer';

        asrSocket.addEventListener('open', () => {
            log('ASR WebSocket connected');
            mediaRecorder.start(500);
        });

        asrSocket.addEventListener('message', async (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.text) {
                    latestTranscript = data.text;
                    updateDialogue(data.text, data.speaker || '主角');
                    if (QUESTION_TRIGGER_PATTERN.test(data.text)) {
                        await requestBranchOptions(data.text);
                    }
                }
                if (data.options) {
                    setOptions(data.options);
                }
            } catch (err) {
                console.error('解析ASR消息失败', err);
            }
        });

        asrSocket.addEventListener('close', () => {
            log('ASR WebSocket closed');
            mediaRecorder?.stop();
        });

        mediaRecorder.addEventListener('dataavailable', (event) => {
            if (event.data?.size && asrSocket?.readyState === WebSocket.OPEN) {
                event.data.arrayBuffer().then((buffer) => {
                    asrSocket.send(buffer);
                });
            }
        });
    } catch (err) {
        console.error('初始化音频流失败', err);
    }
}

async function requestBranchOptions(text) {
    try {
        const response = await fetch('/gpt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: text }),
        });
        if (!response.ok) throw new Error('剧情生成失败');
        const data = await response.json();
        if (data.text) updateDialogue(data.text, data.speaker || 'AI同伴');
        if (data.options) setOptions(data.options);
    } catch (error) {
        console.error('请求剧情分支失败', error);
    }
}

function showGenderWarning() {
    genderWarning.classList.remove('hidden');
}

async function checkGender() {
    if (!cameraFeed.videoWidth || !cameraFeed.videoHeight) return;

    const canvas = document.createElement('canvas');
    canvas.width = cameraFeed.videoWidth;
    canvas.height = cameraFeed.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(cameraFeed, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.7));
    if (!blob) return;

    try {
        const response = await fetch('/yolo_gender', {
            method: 'POST',
            body: blob,
        });
        if (!response.ok) throw new Error('性别识别失败');
        const result = await response.json();
        if (result.class && result.class !== 'female' && (result.confidence ?? 0) > 0.7) {
            showGenderWarning();
        }
    } catch (error) {
        console.error('YOLO识别异常', error);
    }
}

function startGenderGuard() {
    if (genderIntervalId) {
        clearInterval(genderIntervalId);
    }
    genderIntervalId = setInterval(checkGender, GENDER_CHECK_INTERVAL);
}

function init() {
    applySpritePosition(spritePositionSelect.value);
    initCamera();
    updateDialogue('启动中……准备好进入现实Galgame的世界了吗？', '系统');
}

init();
