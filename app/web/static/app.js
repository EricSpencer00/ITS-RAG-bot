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
let ppRecorder = null;
let ppStream = null;
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

// ── Web Speech API ───────────────────────────────────────────────────
function initSpeechRecognition() {
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

    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}${wsPath()}`);

    ws.onopen = () => {
        setConnection(true);
        updateModelDisplay();
        if (currentEngine === "cascaded") {
            ws.send(JSON.stringify({ type: "config", audio_enabled: audioToggle.checked }));
        } else {
            connectionStatus.textContent = "Loading PersonaPlex…";
        }
    };

    ws.onclose = () => {
        setConnection(false);
        stopPersonaPlexCapture();
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
                if (msg.message === "ready" && currentEngine === "personaplex") {
                    connectionStatus.textContent = "Ready · PersonaPlex";
                    startPersonaPlexCapture();
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
async function startPersonaPlexCapture() {
    if (ppRecorder) return;
    try {
        ppStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
            ? "audio/webm;codecs=opus"
            : "audio/ogg;codecs=opus";
        ppRecorder = new MediaRecorder(ppStream, { mimeType: mime });
        ppRecorder.ondataavailable = async (ev) => {
            if (!ev.data || ev.data.size === 0) return;
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            const buf = await ev.data.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let bin = "";
            for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
            const b64 = btoa(bin);
            ws.send(JSON.stringify({ type: "audio", data: b64 }));
        };
        ppRecorder.start(100); // 100ms chunks
        micBtn.classList.add("recording");
        recordingText.textContent = "PersonaPlex listening…";
    } catch (e) {
        console.error("PersonaPlex capture error:", e);
        createMessage("assistant", "Error: mic access failed for PersonaPlex — " + e.message);
    }
}

function stopPersonaPlexCapture() {
    if (ppRecorder) {
        try { ppRecorder.stop(); } catch (_) {}
        ppRecorder = null;
    }
    if (ppStream) {
        ppStream.getTracks().forEach(t => t.stop());
        ppStream = null;
    }
    micBtn.classList.remove("recording");
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
recordingStop.addEventListener("click", () => { if (recognition && isListening) recognition.stop(); });

audioToggle.addEventListener("change", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "config", audio_enabled: audioToggle.checked }));
    }
    if (!audioToggle.checked) stopPlayback();
});

engineSelect.addEventListener("change", () => {
    currentEngine = engineSelect.value;
    if (currentEngine === "personaplex") {
        createMessage("assistant", "Switching to PersonaPlex (local, full-duplex). First load may download ~15GB and take several minutes.");
    } else {
        createMessage("assistant", "Switched to cascaded voice pipeline.");
    }
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
connectWebSocket();
