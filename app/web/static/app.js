const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const sendBtn = document.getElementById("sendBtn");
const clearBtn = document.getElementById("clearBtn");
const textInput = document.getElementById("textInput");
const messagesEl = document.getElementById("messages");
const partialEl = document.getElementById("partial-transcript");
const connectionStatus = document.getElementById("connection-status");
const connectionDot = document.getElementById("connection-dot");
const audioToggle = document.getElementById("audioToggle");

let ws = null;
let audioContext = null;
let processor = null;
let input = null;
let stream = null;
let isListening = false;
let isSpeaking = false;
let currentAudio = null;
let audioQueue = [];
let isPlayingQueue = false;
let currentAssistantMessageDiv = null;
let currentAssistantBubble = null;
let currentAssistantRawText = "";
let typingIndicator = null;

const TARGET_SAMPLE_RATE = 16000;

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showTypingIndicator() {
    if (typingIndicator) return;
    
    const msgDiv = document.createElement("div");
    msgDiv.className = "message assistant";
    
    const bubble = document.createElement("div");
    bubble.className = "bubble typing-bubble";
    bubble.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
    `;
    
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
    // Convert URLs in text to clickable links
    // Match http(s) URLs, handling URLs that may end with / or be followed by punctuation
    const urlRegex = /https?:\/\/[^\s<>"\)]+/g;
    return text.replace(urlRegex, (url) => {
        // Remove trailing punctuation that's not part of URL
        let cleanUrl = url;
        let trailingPunct = '';
        while (cleanUrl.length > 0 && /[.,;:!?\)]/.test(cleanUrl[cleanUrl.length - 1])) {
            trailingPunct = cleanUrl[cleanUrl.length - 1] + trailingPunct;
            cleanUrl = cleanUrl.slice(0, -1);
        }
        return `<a href="${cleanUrl}" target="_blank" class="inline-link">${cleanUrl}</a>${trailingPunct}`;
    });
}

function createMessage(role, content = "") {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}`;
    
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (role === "assistant") {
        currentAssistantRawText = content;
        bubble.innerHTML = linkifyText(content);
    } else {
        bubble.textContent = content;
    }
    
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
    currentAssistantBubble.innerHTML = linkifyText(currentAssistantRawText);
    scrollToBottom();
}

function renderSources(sources) {
    if (!currentAssistantMessageDiv || !sources || sources.length === 0) return;
    
    // Check if sources already exist
    let sourcesDiv = currentAssistantMessageDiv.querySelector(".meta-sources");
    if (!sourcesDiv) {
        sourcesDiv = document.createElement("div");
        sourcesDiv.className = "meta-sources";
        currentAssistantMessageDiv.appendChild(sourcesDiv);
    }
    
    sourcesDiv.innerHTML = "<strong>Sources:</strong>";
    sources.forEach((src) => {
        const div = document.createElement("div");
        div.className = "source-item";
        
        // Check if source is a URL
        const sourceUrl = src.source || "";
        if (sourceUrl.startsWith("http")) {
            const link = document.createElement("a");
            link.href = sourceUrl;
            link.target = "_blank";
            link.className = "source-link";
            link.textContent = src.title || sourceUrl;
            div.appendChild(link);
            div.appendChild(document.createTextNode(` (${src.score})`));
        } else {
            div.textContent = `${src.title || "Document"} (${src.score})`;
            div.title = sourceUrl;
        }
        sourcesDiv.appendChild(div);
    });
    scrollToBottom();
}

function setConnection(connected) {
    if (!connected) {
        connectionStatus.textContent = "Disconnected";
        connectionDot.className = "status-dot";
        sendBtn.disabled = true;
        startBtn.disabled = true;
        stopBtn.disabled = true;
    } else {
        updateStatus();
    }
}

function updateStatus() {
    if (isListening) {
        connectionStatus.textContent = "Listening...";
        connectionDot.className = "status-dot listening";
        startBtn.disabled = true;
        stopBtn.disabled = false;
        sendBtn.disabled = false;
    } else if (typingIndicator) {
        connectionStatus.textContent = "Thinking...";
        connectionDot.className = "status-dot thinking";
        startBtn.disabled = false;
        stopBtn.disabled = true;
        sendBtn.disabled = false;
    } else if (isSpeaking) {
        connectionStatus.textContent = "Speaking...";
        connectionDot.className = "status-dot speaking";
        startBtn.disabled = false;
        stopBtn.disabled = true;
        sendBtn.disabled = false;
    } else {
        connectionStatus.textContent = "Connected";
        connectionDot.className = "status-dot connected";
        startBtn.disabled = false;
        stopBtn.disabled = true;
        sendBtn.disabled = false;
    }
}

function setListening(listening) {
    isListening = listening;
    updateStatus();
}

function stopPlayback() {
    audioQueue = [];
    isPlayingQueue = false;
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.removeAttribute('src'); 
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
    const base64Audio = audioQueue.shift();
  
    try {
        const binary = atob(base64Audio);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes.buffer], { type: "audio/wav" });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        currentAudio = audio;
  
        audio.onended = () => {
            URL.revokeObjectURL(url);
            playNextInQueue();
        };
        
        audio.onerror = (e) => {
            console.error("Audio playback error", e);
            URL.revokeObjectURL(url);
            playNextInQueue();
        };
  
        audio.play().catch(e => {
            console.error("Audio play failed:", e);
            playNextInQueue();
        });
    } catch (e) {
        console.error("Error decoding audio", e);
        playNextInQueue();
    }
}

async function playAudio(base64Audio) {
    if (!audioToggle.checked) return; // Don't play if muted
    audioQueue.push(base64Audio);
    if (!isPlayingQueue) {
        playNextInQueue();
    }
}

// Resampling/Conversion logic
function resampleTo16k(float32Array, inputSampleRate) {
    if (inputSampleRate === TARGET_SAMPLE_RATE) return float32Array;
    const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
    const newLength = Math.round(float32Array.length / ratio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
        const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
        let accum = 0, count = 0;
        for (let i = offsetBuffer; i < nextOffsetBuffer && i < float32Array.length; i++) {
            accum += float32Array[i];
            count++;
        }
        result[offsetResult] = accum / count;
        offsetResult++;
        offsetBuffer = nextOffsetBuffer;
    }
    return result;
}

function floatTo16BitPCM(float32Array) {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    let offset = 0;
    for (let i = 0; i < float32Array.length; i++, offset += 2) {
        let s = Math.max(-1, Math.min(1, float32Array[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buffer;
}

function computeRms(float32Array) {
    let sum = 0;
    for (let i = 0; i < float32Array.length; i++) {
        sum += float32Array[i] * float32Array[i];
    }
    return Math.sqrt(sum / float32Array.length);
}

// WebSocket Management
function connectWebSocket() {
    // use secure websocket when page is served over HTTPS
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/audio`);

    ws.onopen = () => {
        setConnection(true);
        // Send initial config
        ws.send(JSON.stringify({ 
            type: "config", 
            audio_enabled: audioToggle.checked 
        }));
    };

    ws.onclose = () => {
        setConnection(false);
        stopListening();
        // Try reconnect in 3s
        setTimeout(connectWebSocket, 3000);
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        
        switch (msg.type) {
            case "partial":
                partialEl.textContent = msg.text + "...";
                partialEl.style.opacity = "1";
                break;
                
            case "final_text":
                partialEl.textContent = "";
                partialEl.style.opacity = "0";
                createMessage("user", msg.text);
                // Reset assistant bubble for new response
                currentAssistantBubble = null;
                currentAssistantMessageDiv = null;
                showTypingIndicator(); // Show typing indicator when user finishes speaking
                break;
                
            case "meta":
                // Intent info or sources
                if (msg.sources) renderSources(msg.sources);
                break;
                
            case "token":
                // Real-time text streaming
                hideTypingIndicator(); // Hide indicator when tokens start arriving
                appendToAssistantMessage(msg.content);
                break;
                
            case "tts":
                playAudio(msg.audio);
                break;
                
            case "barge_in":
                stopPlayback();
                break;
                
            case "final":
                // Ensure full text is synced or logged
                hideTypingIndicator(); // Hide in case it's still there
                if (!currentAssistantBubble && msg.response) {
                     // In case token streaming failed or wasn't used
                     createMessage("assistant", msg.response);
                }
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

// Audio Capture
async function startListening() {
    if (isListening) return;
    
    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        input = audioContext.createMediaStreamSource(stream);
        processor = audioContext.createScriptProcessor(4096, 1, 1);

        processor.onaudioprocess = (e) => {
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            
            const inputData = e.inputBuffer.getChannelData(0);
            
            // Barge-in detection
            const rms = computeRms(inputData);
            if (isSpeaking && rms > 0.05) { // Slightly higher threshold
                ws.send(JSON.stringify({ type: "barge_in" }));
                stopPlayback();
            }
            
            const resampled = resampleTo16k(inputData, audioContext.sampleRate);
            const pcmBuffer = floatTo16BitPCM(resampled);
            const b64 = btoa(String.fromCharCode(...new Uint8Array(pcmBuffer)));
            
            ws.send(JSON.stringify({ 
                type: "audio", 
                data: b64, 
                sample_rate: TARGET_SAMPLE_RATE 
            }));
        };

        input.connect(processor);
        processor.connect(audioContext.destination); // Needed for Chrome to fire events, usually mute it if echo issues
        
        setListening(true);
    } catch (e) {
        console.error("Mic error:", e);
        alert("Could not access microphone.");
    }
}

async function stopListening() {
    if (!isListening) return;
    if (processor) { processor.disconnect(); processor = null; }
    if (input) { input.disconnect(); input = null; }
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    if (audioContext) { await audioContext.close(); audioContext = null; }
    setListening(false);
    partialEl.textContent = "";
    partialEl.style.opacity = "0";
}

// Event Listeners
clearBtn.addEventListener("click", () => {
    messagesEl.innerHTML = "";
    currentAssistantBubble = null;
    currentAssistantMessageDiv = null;
});

sendBtn.addEventListener("click", async () => {
    const text = textInput.value.trim();
    if (!text) return;

    createMessage("user", text);
    currentAssistantBubble = null;
    currentAssistantMessageDiv = null;
    showTypingIndicator(); // Show typing indicator immediately for text input

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "text", text }));
    } else {
        // fallback to HTTP
        try {
            const resp = await fetch("/api/text", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text }),
            });
            const data = await resp.json();
            // emulate streaming by sending whole response
            if (data.response) {
                appendToAssistantMessage(data.response);
                renderSources(data.sources || []);
            }
        } catch (err) {
            console.error("HTTP chat failed", err);
        }
    }

    textInput.value = "";
});

textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        sendBtn.click();
    }
});

startBtn.addEventListener("click", () => {
    if (audioContext && audioContext.state === 'suspended') {
        audioContext.resume();
    }
    startListening();
});

stopBtn.addEventListener("click", stopListening);

audioToggle.addEventListener("change", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ 
            type: "config", 
            audio_enabled: audioToggle.checked 
        }));
    }
    if (!audioToggle.checked) {
        stopPlayback();
    }
});

// Init
connectWebSocket();
