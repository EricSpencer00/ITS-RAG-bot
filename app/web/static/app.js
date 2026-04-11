const sendBtn = document.getElementById("sendBtn");
const clearBtn = document.getElementById("clearBtn");
const textInput = document.getElementById("textInput");
const messagesEl = document.getElementById("messages");
const partialEl = document.getElementById("partial-transcript");
const connectionStatus = document.getElementById("connection-status");
const connectionDot = document.getElementById("connection-dot");
const audioToggle = document.getElementById("audioToggle");
const modelSelect = document.getElementById("modelSelect");
const engineSelect = document.getElementById("engineSelect");
const micBtn = document.getElementById("micBtn");
const welcomeEl = document.getElementById("welcome");
const recordingOverlay = document.getElementById("recording-overlay");
const recordingText = document.getElementById("recording-text");
const recordingStop = document.getElementById("recording-stop");

let ws = null;
let currentEngine = "cascaded"; // "cascaded" | "personaplex"
let ppStream = null;
let ppAudioContext = null;
let ppSourceNode = null;
let ppProcessorNode = null;
let ppActive = false;
// Cascaded-mode capture state (server-side Whisper STT via /ws/audio)
let cascStream = null;
let cascAudioContext = null;
let cascSourceNode = null;
let cascProcessorNode = null;
let cascActive = false;
const CASCADED_TARGET_SR = 16000;
let isListening = false;
let isSpeaking = false;
let currentAudio = null;
let audioQueue = [];
let isPlayingQueue = false;
let currentAssistantMessageDiv = null;
let currentAssistantBubble = null;
let currentAssistantRawText = "";
let typingIndicator = null;
let currentModel = "";
let recognition = null;
let finalTranscript = "";
let hasMessages = false;

// ── Welcome / Messages visibility ────────────────────────────────────
function showMessages() {
    if (!hasMessages) {
        hasMessages = true;
        welcomeEl.classList.add("hidden");
        messagesEl.classList.add("active");
    }
}

// ── Web Speech API (last-resort fallback only) ───────────────────────
//
// Web Speech API in Chromium routes to Google's cloud speech service.
// On any network hiccup, VPN, or firewall it fires `onerror: "network"`
// within ~100 ms — that was the silently-failing-mic bug. We now prefer
// AudioContext + server-side Whisper, and only initialize this fallback
// if AudioContext / getUserMedia are missing entirely.
function initSpeechRecognition() {
    const hasAudioContext = !!(window.AudioContext || window.webkitAudioContext);
    const hasGetUserMedia = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    if (hasAudioContext && hasGetUserMedia) {
        // Skip Web Speech entirely. We'll use AudioContext capture.
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.warn("Web Speech API not supported");
        micBtn.disabled = true;
        micBtn.title = "Speech not supported — try Chrome or Edge";
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        isListening = true;
        finalTranscript = "";
        micBtn.classList.add("recording");
        recordingOverlay.classList.add("active");
        recordingText.textContent = "Listening...";
        updateStatus();
    };

    recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const t = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += t;
            } else {
                interim += t;
            }
        }

        const display = (finalTranscript + interim).trim();
        if (display) {
            recordingText.textContent = display;
            partialEl.textContent = display;
            partialEl.classList.add("visible");
        }

        // Barge-in
        if (isSpeaking && display) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "barge_in" }));
            }
            stopPlayback();
        }
    };

    recognition.onend = () => {
        isListening = false;
        micBtn.classList.remove("recording");
        recordingOverlay.classList.remove("active");
        updateStatus();

        const text = finalTranscript.trim();
        partialEl.textContent = "";
        partialEl.classList.remove("visible");

        if (text) {
            submitText(text);
        }

        finalTranscript = "";
    };

    recognition.onerror = (event) => {
        console.error("Speech error:", event.error);
        isListening = false;
        micBtn.classList.remove("recording");
        recordingOverlay.classList.remove("active");
        updateStatus();
        partialEl.textContent = "";
        partialEl.classList.remove("visible");

        if (event.error === "not-allowed") {
            alert("Microphone access denied. Please allow mic access in your browser settings.");
        }
    };
}

function toggleListening() {
    if (currentEngine === "personaplex") {
        // PersonaPlex uses full-duplex capture over its own WebSocket.
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            alert("PersonaPlex is still loading. Please wait for the status to read 'Ready'.");
            return;
        }
        if (ppActive) {
            stopPersonaPlexCapture();
        } else {
            startPersonaPlexCapture();
        }
        return;
    }

    // Cascaded mode: prefer server-side Whisper STT (over /ws/audio).
    // The browser's Web Speech API requires Google's cloud speech service,
    // which fails with "network" errors on offline / firewalled / VPN setups
    // and tears the recording overlay down within 100 ms. Capturing raw PCM
    // and letting the server's Whisper instance transcribe is reliable and
    // works fully offline.
    const ContextClass = window.AudioContext || window.webkitAudioContext;
    if (ContextClass && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        if (cascActive) {
            stopCascadedCapture();
        } else {
            startCascadedCapture();
        }
        return;
    }

    // Last-resort fallback: browser Web Speech API.
    if (!recognition) {
        alert("Speech recognition not supported. Try Chrome or Edge.");
        return;
    }
    if (isListening) {
        recognition.stop();
    } else {
        finalTranscript = "";
        recognition.start();
    }
}

// ── Submit text (shared by typing, voice, and chips) ─────────────────
function submitText(text) {
    if (!text) return;
    showMessages();
    createMessage("user", text);
    currentAssistantBubble = null;
    currentAssistantMessageDiv = null;
    showTypingIndicator();

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "text", text }));
    } else {
        fetch("/api/text", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        })
        .then(r => r.json())
        .then(data => {
            if (data.response) {
                hideTypingIndicator();
                appendToAssistantMessage(data.response);
                renderSources(data.sources || []);
            }
        })
        .catch(e => console.error("HTTP chat failed:", e));
    }
}

// ── Model Display ────────────────────────────────────────────────────
async function updateModelDisplay() {
    try {
        const resp = await fetch("/api/models");
        const data = await resp.json();
        const model = data.current;
        currentModel = model.includes("/") ? model.split("/")[1] : model;
        updateStatus();
    } catch (e) {
        console.error("Failed to fetch model info:", e);
    }
}

// ── Chat UI ──────────────────────────────────────────────────────────
function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showTypingIndicator() {
    if (typingIndicator) return;

    const msgDiv = document.createElement("div");
    msgDiv.className = "message assistant";

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`;

    const bubble = document.createElement("div");
    bubble.className = "bubble typing-bubble";
    bubble.innerHTML = `<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>`;

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bubble);
    messagesEl.appendChild(msgDiv);
    typingIndicator = msgDiv;
    scrollToBottom();
    updateStatus();
}

function hideTypingIndicator() {
    if (typingIndicator) {
        typingIndicator.remove();
        typingIndicator = null;
        updateStatus();
    }
}

function linkifyText(text) {
    if (!text) return "";
    return text.replace(/https?:\/\/[^\s<>"\)]+/g, (url) => {
        let clean = url, trail = '';
        while (clean.length && /[.,;:!?\)]/.test(clean[clean.length - 1])) {
            trail = clean[clean.length - 1] + trail;
            clean = clean.slice(0, -1);
        }
        return `<a href="${clean}" target="_blank" class="inline-link">${clean}</a>${trail}`;
    });
}

function createMessage(role, content = "") {
    showMessages();

    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    if (role === "assistant") {
        avatar.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`;
    } else {
        avatar.textContent = "You";
    }

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (role === "assistant") {
        currentAssistantRawText = content;
        bubble.innerHTML = linkifyText(content);
    } else {
        bubble.textContent = content;
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bubble);
    messagesEl.appendChild(msgDiv);
    scrollToBottom();
    return { msgDiv, bubble };
}

function appendToAssistantMessage(text) {
    if (!currentAssistantBubble) {
        const { bubble, msgDiv } = createMessage("assistant");
        currentAssistantBubble = bubble;
        currentAssistantMessageDiv = msgDiv;
        currentAssistantRawText = "";
    }

    currentAssistantRawText += text;

    const lower = currentAssistantRawText.toLowerCase();
    const isError = lower.includes("error") || lower.includes("trouble") || lower.includes("encountered");
    currentAssistantBubble.classList.toggle("error", isError);
    currentAssistantBubble.innerHTML = linkifyText(currentAssistantRawText);
    scrollToBottom();
}

function renderSources(sources) {
    if (!currentAssistantMessageDiv || !sources || sources.length === 0) return;

    let sourcesDiv = currentAssistantMessageDiv.querySelector(".meta-sources");
    if (!sourcesDiv) {
        sourcesDiv = document.createElement("div");
        sourcesDiv.className = "meta-sources";
        currentAssistantMessageDiv.appendChild(sourcesDiv);
    }

    sourcesDiv.innerHTML = '<strong>Sources</strong>';
    sources.forEach((src) => {
        const div = document.createElement("div");
        div.className = "source-item";

        const score = parseFloat(src.score) || 0;
        let relevance = "Low", badge = "low";
        if (score >= 0.7) { relevance = "High"; badge = "high"; }
        else if (score >= 0.55) { relevance = "Good"; badge = "high"; }
        else if (score >= 0.40) { relevance = "Related"; badge = "mid"; }

        const sourceUrl = src.source || "";
        const title = src.title || "Document";

        let html = `<span class="source-badge ${badge}">${relevance}</span>`;
        if (sourceUrl.startsWith("http")) {
            html += ` <a href="${sourceUrl}" target="_blank" class="source-link">${title}</a>`;
        } else {
            html += ` <span>${title}</span>`;
        }

        div.innerHTML = html;
        div.title = sourceUrl;
        sourcesDiv.appendChild(div);
    });
    scrollToBottom();
}

// ── Status ───────────────────────────────────────────────────────────
function setConnection(connected) {
    if (!connected) {
        connectionStatus.textContent = "Offline";
        connectionDot.className = "status-dot";
        sendBtn.disabled = true;
        micBtn.disabled = true;
    } else {
        sendBtn.disabled = false;
        micBtn.disabled = false;
        updateStatus();
    }
}

function updateStatus() {
    let state = "Ready";
    let dot = "connected";

    if (isListening) { state = "Listening"; dot = "listening"; }
    else if (typingIndicator) { state = "Thinking"; dot = "thinking"; }
    else if (isSpeaking) { state = "Speaking"; dot = "speaking"; }

    connectionStatus.textContent = currentModel ? `${state} · ${currentModel}` : state;
    connectionDot.className = `status-dot ${dot}`;
}

// ── Audio Playback ───────────────────────────────────────────────────
function stopPlayback() {
    audioQueue = [];
    isPlayingQueue = false;
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.removeAttribute("src");
        currentAudio = null;
    }
    isSpeaking = false;
    updateStatus();
}

function playNextInQueue() {
    if (audioQueue.length === 0) {
        isPlayingQueue = false;
        isSpeaking = false;
        updateStatus();
        return;
    }

    isPlayingQueue = true;
    isSpeaking = true;
    updateStatus();
    const b64 = audioQueue.shift();

    try {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const blob = new Blob([bytes.buffer], { type: "audio/wav" });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        currentAudio = audio;
        audio.onended = () => { URL.revokeObjectURL(url); playNextInQueue(); };
        audio.onerror = () => { URL.revokeObjectURL(url); playNextInQueue(); };
        audio.play().catch(() => playNextInQueue());
    } catch (e) {
        console.error("Audio decode error:", e);
        playNextInQueue();
    }
}

function playAudio(b64) {
    if (!audioToggle.checked) return;
    audioQueue.push(b64);
    if (!isPlayingQueue) playNextInQueue();
}

// ── WebSocket ────────────────────────────────────────────────────────
function wsPath() {
    return currentEngine === "personaplex" ? "/ws/personaplex" : "/ws/audio";
}

function connectWebSocket() {
    // Close any existing socket before opening a new one
    if (ws) {
        try { ws.onclose = null; ws.close(); } catch (_) {}
        ws = null;
    }
    stopPersonaPlexCapture();
    stopCascadedCapture();

    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}${wsPath()}`);

    ws.onopen = () => {
        setConnection(true);
        updateModelDisplay();
        if (currentEngine === "cascaded") {
            ws.send(JSON.stringify({ type: "config", audio_enabled: audioToggle.checked }));
        } else {
            connectionStatus.textContent = "Loading PersonaPlex…";
            micBtn.disabled = true; // re-enabled when server sends status:ready
        }
    };

    ws.onclose = () => {
        setConnection(false);
        stopPersonaPlexCapture();
        stopCascadedCapture();
        if (isListening && recognition) recognition.stop();
        setTimeout(connectWebSocket, 3000);
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
            case "partial":
                partialEl.textContent = msg.text + "...";
                partialEl.classList.add("visible");
                break;
            case "final_text":
                // Server-side Whisper detected end-of-utterance and is now
                // about to run the LLM. Stop streaming mic audio so we don't
                // keep buffering during inference.
                if (cascActive) stopCascadedCapture();
                partialEl.textContent = "";
                partialEl.classList.remove("visible");
                showMessages();
                createMessage("user", msg.text);
                currentAssistantBubble = null;
                currentAssistantMessageDiv = null;
                showTypingIndicator();
                break;
            case "meta":
                if (msg.sources) renderSources(msg.sources);
                break;
            case "token":
                hideTypingIndicator();
                appendToAssistantMessage(msg.content);
                break;
            case "tts":
                playAudio(msg.audio);
                break;
            case "audio":
                // PersonaPlex streams WAV chunks under type:"audio"
                playAudio(msg.data);
                break;
            case "status":
                if (currentEngine === "personaplex") {
                    if (msg.message === "loading") {
                        connectionStatus.textContent = "Loading PersonaPlex…";
                        micBtn.disabled = true;
                    } else if (msg.message === "ready") {
                        connectionStatus.textContent = "Ready · PersonaPlex (tap mic to talk)";
                        micBtn.disabled = false;
                    }
                }
                break;
            case "barge_in":
                stopPlayback();
                break;
            case "final":
                hideTypingIndicator();
                if (!currentAssistantBubble && msg.response) createMessage("assistant", msg.response);
                if (msg.sources) renderSources(msg.sources);
                break;
            case "error":
                console.error("Server error:", msg.message);
                hideTypingIndicator();
                createMessage("assistant", "Error: " + msg.message);
                break;
        }
    };
}

// ── PersonaPlex full-duplex mic capture ──────────────────────────────
//
// We deliberately do NOT use MediaRecorder here. MediaRecorder emits
// WebM- or Ogg-wrapped Opus, but the server pipes incoming bytes through
// sphn.OpusStreamReader, which expects raw Opus packets — the very first
// WebM header would trip a "channel closed" error and silently tear down
// the WS. Instead we capture raw Float32 PCM via AudioContext, downconvert
// to Int16, and ship it as base64 under {type:"pcm"}. The server handles
// the resample to PersonaPlex's native 24 kHz.
async function startPersonaPlexCapture() {
    if (ppActive) return;
    try {
        ppStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });

        const ContextClass = window.AudioContext || window.webkitAudioContext;
        // Prefer 24 kHz to match mimi, but some browsers ignore sampleRate
        // on construction — that's OK, the server resamples whatever we send.
        try {
            ppAudioContext = new ContextClass({ sampleRate: 24000 });
        } catch (_) {
            ppAudioContext = new ContextClass();
        }
        if (ppAudioContext.state === "suspended") {
            try { await ppAudioContext.resume(); } catch (_) {}
        }

        const srcRate = ppAudioContext.sampleRate;
        ppSourceNode = ppAudioContext.createMediaStreamSource(ppStream);

        // ScriptProcessorNode is deprecated but universally supported and
        // works without bundling an AudioWorklet module. Buffer size 2048
        // at 24 kHz ≈ 85 ms per chunk, low enough for conversational latency.
        const bufferSize = 2048;
        ppProcessorNode = ppAudioContext.createScriptProcessor(bufferSize, 1, 1);

        ppProcessorNode.onaudioprocess = (ev) => {
            if (!ppActive) return;
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            const input = ev.inputBuffer.getChannelData(0);
            const int16 = new Int16Array(input.length);
            for (let i = 0; i < input.length; i++) {
                const s = Math.max(-1, Math.min(1, input[i]));
                int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            const bytes = new Uint8Array(int16.buffer);
            // btoa on a large binary string can be slow; this is fine for 2048 samples.
            let bin = "";
            for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
            ws.send(JSON.stringify({
                type: "pcm",
                data: btoa(bin),
                sample_rate: srcRate,
            }));
        };

        ppSourceNode.connect(ppProcessorNode);
        // ScriptProcessor needs to reach destination to actually run its callback;
        // we route it through a muted gain so the user doesn't hear their own mic.
        const muted = ppAudioContext.createGain();
        muted.gain.value = 0;
        ppProcessorNode.connect(muted);
        muted.connect(ppAudioContext.destination);

        ppActive = true;
        isListening = true;
        micBtn.classList.add("recording");
        recordingOverlay.classList.add("active");
        recordingText.textContent = "PersonaPlex listening…";
        updateStatus();
    } catch (e) {
        console.error("PersonaPlex capture error:", e);
        createMessage("assistant", "Error: mic access failed for PersonaPlex — " + e.message);
        stopPersonaPlexCapture();
    }
}

// ── Cascaded mode capture (server-side Whisper STT) ─────────────────
//
// Captures Float32 PCM via AudioContext, downsamples to 16 kHz mono Int16,
// and ships it to /ws/audio under {type:"audio"}. The server already does
// VAD + Whisper transcription and replies with {type:"final_text"}.
async function startCascadedCapture() {
    if (cascActive) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert("Not connected to the server yet — try again in a moment.");
        return;
    }
    try {
        cascStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });

        const ContextClass = window.AudioContext || window.webkitAudioContext;
        // Try native 16 kHz first; if the browser refuses we'll resample.
        try {
            cascAudioContext = new ContextClass({ sampleRate: CASCADED_TARGET_SR });
        } catch (_) {
            cascAudioContext = new ContextClass();
        }
        if (cascAudioContext.state === "suspended") {
            try { await cascAudioContext.resume(); } catch (_) {}
        }

        const srcRate = cascAudioContext.sampleRate;
        cascSourceNode = cascAudioContext.createMediaStreamSource(cascStream);

        const bufferSize = 4096;
        cascProcessorNode = cascAudioContext.createScriptProcessor(bufferSize, 1, 1);

        cascProcessorNode.onaudioprocess = (ev) => {
            if (!cascActive) return;
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            const input = ev.inputBuffer.getChannelData(0);

            // Downsample to 16 kHz if the AudioContext didn't honor our request.
            let mono = input;
            if (srcRate !== CASCADED_TARGET_SR) {
                const ratio = CASCADED_TARGET_SR / srcRate;
                const outLen = Math.max(1, Math.floor(input.length * ratio));
                const out = new Float32Array(outLen);
                for (let i = 0; i < outLen; i++) {
                    const srcIdx = i / ratio;
                    const lo = Math.floor(srcIdx);
                    const hi = Math.min(lo + 1, input.length - 1);
                    const frac = srcIdx - lo;
                    out[i] = input[lo] * (1 - frac) + input[hi] * frac;
                }
                mono = out;
            }

            const int16 = new Int16Array(mono.length);
            for (let i = 0; i < mono.length; i++) {
                const s = Math.max(-1, Math.min(1, mono[i]));
                int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            const bytes = new Uint8Array(int16.buffer);
            let bin = "";
            for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
            ws.send(JSON.stringify({ type: "audio", data: btoa(bin) }));
        };

        cascSourceNode.connect(cascProcessorNode);
        const muted = cascAudioContext.createGain();
        muted.gain.value = 0;
        cascProcessorNode.connect(muted);
        muted.connect(cascAudioContext.destination);

        cascActive = true;
        isListening = true;
        micBtn.classList.add("recording");
        recordingOverlay.classList.add("active");
        recordingText.textContent = "Listening…";
        partialEl.textContent = "";
        partialEl.classList.remove("visible");
        updateStatus();
    } catch (e) {
        console.error("Cascaded capture error:", e);
        if (e && e.name === "NotAllowedError") {
            alert("Microphone access denied. Please allow mic access in your browser settings.");
        } else {
            createMessage("assistant", "Error: mic access failed — " + (e && e.message ? e.message : e));
        }
        stopCascadedCapture();
    }
}

function stopCascadedCapture() {
    cascActive = false;
    if (cascProcessorNode) {
        try { cascProcessorNode.disconnect(); } catch (_) {}
        cascProcessorNode.onaudioprocess = null;
        cascProcessorNode = null;
    }
    if (cascSourceNode) {
        try { cascSourceNode.disconnect(); } catch (_) {}
        cascSourceNode = null;
    }
    if (cascAudioContext) {
        try { cascAudioContext.close(); } catch (_) {}
        cascAudioContext = null;
    }
    if (cascStream) {
        cascStream.getTracks().forEach(t => t.stop());
        cascStream = null;
    }
    isListening = false;
    micBtn.classList.remove("recording");
    recordingOverlay.classList.remove("active");
    partialEl.textContent = "";
    partialEl.classList.remove("visible");
    updateStatus();
}

function stopPersonaPlexCapture() {
    ppActive = false;
    if (ppProcessorNode) {
        try { ppProcessorNode.disconnect(); } catch (_) {}
        ppProcessorNode.onaudioprocess = null;
        ppProcessorNode = null;
    }
    if (ppSourceNode) {
        try { ppSourceNode.disconnect(); } catch (_) {}
        ppSourceNode = null;
    }
    if (ppAudioContext) {
        try { ppAudioContext.close(); } catch (_) {}
        ppAudioContext = null;
    }
    if (ppStream) {
        ppStream.getTracks().forEach(t => t.stop());
        ppStream = null;
    }
    if (ws && ws.readyState === WebSocket.OPEN && currentEngine === "personaplex") {
        try { ws.send(JSON.stringify({ type: "stop" })); } catch (_) {}
    }
    isListening = false;
    micBtn.classList.remove("recording");
    recordingOverlay.classList.remove("active");
    updateStatus();
}

// ── Events ───────────────────────────────────────────────────────────
clearBtn.addEventListener("click", () => {
    messagesEl.innerHTML = "";
    messagesEl.classList.remove("active");
    welcomeEl.classList.remove("hidden");
    hasMessages = false;
    currentAssistantBubble = null;
    currentAssistantMessageDiv = null;
});

sendBtn.addEventListener("click", () => {
    const text = textInput.value.trim();
    if (!text) return;
    submitText(text);
    textInput.value = "";
});

textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); sendBtn.click(); }
});

micBtn.addEventListener("click", toggleListening);
recordingStop.addEventListener("click", () => {
    if (currentEngine === "personaplex") {
        stopPersonaPlexCapture();
    } else if (cascActive) {
        stopCascadedCapture();
    } else if (recognition && isListening) {
        recognition.stop();
    }
});

audioToggle.addEventListener("change", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "config", audio_enabled: audioToggle.checked }));
    }
    if (!audioToggle.checked) stopPlayback();
});

// Cached engine descriptors fetched from /api/voice/engines on startup,
// used to refuse the PP option client-side instead of opening a WS that
// will just be killed (or worse, segfault the worker) when the server
// reports PP is unsupported on this host.
let availableEngines = {};

async function fetchAvailableEngines() {
    try {
        const resp = await fetch("/api/voice/engines");
        const data = await resp.json();
        availableEngines = {};
        (data.engines || []).forEach(e => { availableEngines[e.id] = e; });

        // Disable / annotate the PP <option> if the server marked it
        // unavailable, so the user can see *why* before clicking.
        const ppOption = engineSelect.querySelector('option[value="personaplex"]');
        if (ppOption) {
            const pp = availableEngines["personaplex"];
            if (pp && !pp.available) {
                ppOption.disabled = true;
                ppOption.textContent = "PersonaPlex (unavailable)";
                ppOption.title = pp.unavailable_reason || "Not available on this host";
            }
        }
    } catch (e) {
        console.error("Failed to fetch /api/voice/engines:", e);
    }
}

engineSelect.addEventListener("change", () => {
    const requested = engineSelect.value;
    if (requested === "personaplex") {
        const pp = availableEngines["personaplex"];
        if (pp && !pp.available) {
            // Bounce the user back to cascaded with a clear message rather
            // than connecting and waiting for the inevitable error frame.
            engineSelect.value = "cascaded";
            createMessage(
                "assistant",
                "PersonaPlex is unavailable on this server: " +
                (pp.unavailable_reason || "no reason given") +
                "\n\nStaying on the cascaded voice pipeline."
            );
            return;
        }
        createMessage("assistant", "Switching to PersonaPlex (local, full-duplex). First load may download ~15GB and take several minutes.");
    } else {
        createMessage("assistant", "Switched to cascaded voice pipeline.");
    }
    currentEngine = requested;
    connectWebSocket();
});

modelSelect.addEventListener("change", async () => {
    let model = modelSelect.value;
    if (model === "ollama") model = "llama3.1:8b";
    try {
        const resp = await fetch("/api/models/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ model }),
        });
        const data = await resp.json();
        if (data.status === "ok") {
            updateModelDisplay();
        } else {
            console.error("Model switch failed:", data.message);
        }
    } catch (err) {
        console.error("Model switch error:", err);
    }
});

// Quick-start chips
document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
        const q = chip.getAttribute("data-q");
        if (q) submitText(q);
    });
});

// ── Init ─────────────────────────────────────────────────────────────
initSpeechRecognition();
fetchAvailableEngines();
connectWebSocket();
