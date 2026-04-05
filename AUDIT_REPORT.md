# System Audit Report — Live ITS Bot
**Date:** 2026-04-05 | **Status:** 🚨 Multiple Critical Issues

---

## 1. BACKEND ISSUES

### ✅ Fixed in Latest Commit
- Error handling for HF API failures (was silently failing)
- Fallback logic: HF → Ollama (automatic failover)
- Better logging for debugging
- Ollama upgraded: gemma:2b → llama3.1:8b

### 🚨 Current Issues

#### 1.1 HF API Unreliable
**Problem:** HuggingFace free tier models often unavailable or routing to incompatible providers
- Qwen models → featherless-ai provider (doesn't support `text-generation`)
- Falcon/Mistral/Zephyr → inconsistent availability
- Causes "I encountered an error" fallback responses

**Impact:** Users expecting fast inference get delayed responses (HF timeout → Ollama fallback)

**Solution Options:**
1. **Remove HF from dropdown entirely** — rely only on fast local Ollama
2. **Use HF's Serverless Inference Endpoints** — guaranteed availability but requires setup
3. **Use smaller local models** — mistral:latest, phi (4.4GB, 2.7GB) instead of llama3.1:8b (4.9GB)

**Current Recommendation:** Keep HF dropdown but make it opt-in; default to local Ollama

---

#### 1.2 RAG → LLM Context Mismatch
**Problem:** Diagnostic prompt tells bot to ask clarifying questions, but RAG scoring may not align
- Example: User says "email not working" → RAG returns printer docs (0.638 score)
- Bot tries to answer about printers instead of asking about email setup method

**Impact:** Poor conversation quality, bot answers wrong questions

**Fix needed:** 
- Adjust `RAG_MIN_SCORE` from 0.35 → 0.50 to filter weak matches
- Improve diagnostic prompt to recognize low-quality RAG results

---

#### 1.3 Streaming Issues
**Problem:** WebSocket streaming sometimes produces incomplete responses
- Text tokens queue up and send in batches instead of true streaming
- Audio (TTS) synthesis chops up mid-sentence occasionally

**Impact:** Looks like bot is "thinking" longer than it actually is

---

## 2. FRONTEND UX ISSUES

### 🚨 Critical UX Problems

#### 2.1 Model Selector is Confusing
**Issue:** Dropdown labeled "Model:" with 6 options but no explanation
- Users don't understand why switching models doesn't fix errors (HF → Ollama)
- Model names have emojis (⚡🔥) but meaning is unclear
- No visual feedback when model is switching

**Fix:**
```html
<!-- Add tooltip/help text -->
<div class="model-selector">
  <label for="modelSelect" class="control-label">
    Model: 
    <span title="HuggingFace remote (green) or local Ollama (auto-fallback)">ℹ️</span>
  </label>
  <select id="modelSelect">
    <!-- Group options by type -->
    <optgroup label="Fast (HuggingFace)">
      <option value="qwen2-0.5b">Qwen 0.5B - Ultra fast</option>
    </optgroup>
    <optgroup label="Quality (Local Ollama)">
      <option value="ollama">Use Ollama llama3.1:8b</option>
    </optgroup>
  </select>
</div>
```

#### 2.2 Status Indicator is Useless
**Current:** Just shows "Connected/Thinking/Speaking" dot
**Missing:**
- No indication of which model is being used
- No error state visibility (user sees "I encountered an error" but no context)
- No loading time estimate

**Better status:**
```
[🟢 Connected] [🧠 llama3.1:8b] [⏱ 2.3s] [✓ No errors]
```

#### 2.3 Voice Button States are Unclear
**Issue:** "Start Talk" / "Stop" buttons don't show what's happening
- User clicks "Start Talk" → unclear if recording or waiting
- No visual feedback that audio is being processed
- "Stop" button disabled when not recording but should show mic icon state

**Fix:**
```javascript
// State: "idle", "listening", "processing", "speaking"
startBtn.className = `btn btn-state-${state}`; // CSS shows different text + icon
// "Start Talk" → "Listening..." → "Processing..." → "Speaking..."
```

#### 2.4 Chat Bubbles Don't Show Errors Well
**Issue:** Error messages mixed with regular messages
- "I encountered an error" appears as assistant response (hard to distinguish)
- No error styling (e.g., red background, warning icon)
- User thinks bot is giving an answer when it's actually failed

**Fix:** Add error message styling
```css
.bubble.error {
  background: #ffe5e5;
  border-left: 3px solid #d32f2f;
  color: #d32f2f;
}
.bubble.error::before {
  content: "⚠️ ";
}
```

#### 2.5 Voice Input UX is Broken
**Current Flow:**
1. User clicks "Start Talk"
2. Audio starts recording (no visual feedback)
3. Bot auto-detects silence → sends transcript
4. Response comes back
5. User doesn't know when to speak next

**Issue:** Invisible state machine — user has no idea what the bot is doing

**Better Flow:**
```
[Listening... 🎤] ← user speaks
[Processing...] ← transcript sent, waiting for response
[Speaking... 🔊] → response audio playing
[Ready] ← back to listening (or show "Click to speak again")
```

#### 2.6 Input Area Layout is Cramped
**Current:** Text input + Send + Start Talk + Stop in one row
- On mobile, buttons overflow
- On desktop, spacing feels tight
- "Start Talk" button text wraps awkwardly

**Fix:** Make buttons stack on mobile, clearer on desktop
```css
#input-area {
  flex-wrap: wrap;
  gap: 0.5rem;
}
@media (max-width: 600px) {
  #sendBtn, #startBtn, #stopBtn {
    flex: 1 1 auto; /* Each button grows to fill */
    min-width: 80px;
  }
}
```

#### 2.7 Sources List is Hard to Read
**Current:** Shows source links in chat bubble
**Issue:** 
- Links take up space and distract from answer
- Score (0.638) not meaningful to users
- No indication of relevance or confidence

**Better:**
```
Assistant: "..."

📚 Sources:
  ✓ Printer Setup Guide (highly relevant)
  ~ Network Printer Troubleshooting (related)
```

---

### ✅ What's Working

- ✅ Basic chat works
- ✅ Text input/send works
- ✅ Voice recording + transcription works
- ✅ TTS audio playback works
- ✅ Model switching endpoint works
- ✅ Responsive header layout

---

## 3. CODE ISSUES

### 🚨 Recent Regressions

#### 3.1 _hf_chat_stream Error Handling
**Fixed but worth monitoring:**
- Was yielding "Error: ..." messages that confused users
- Now re-raises for caller to handle fallback

#### 3.2 Async Generator StopIteration
**Fixed but could recur:**
- HuggingFace client sometimes raises StopIteration
- In Python 3.7+, this kills async generators
- Solution: Explicit exception handling + re-raise as RuntimeError

---

## 4. DIAGNOSTIC BOT ISSUES

### ✅ Excellent Implementation
- System prompt is well-written
- Confidence gating works (HIGH_CONFIDENCE_SCORE=0.55, LOW_CONFIDENCE_SCORE=0.40)
- Clarification counting works
- Context preservation for short replies works

### 🚨 In Practice Issues

#### 4.1 RAG Quality Misalignment
**Problem:** RAG doesn't always agree with diagnostic prompt
- Prompt says "ask clarifying questions" if low confidence
- But RAG score 0.40-0.55 is MIDDLE range (should still answer?)
- Bot gets confused trying to ask + answer simultaneously

**Fix:** 
- Adjust thresholds based on actual KB relevance
- Test with real LUC ITS questions
- Consider: "How do I reset password?" → what RAG score do we get?

#### 4.2 Maximum 3 Clarifications
**Issue:** Hard limit prevents bot from asking reasonable follow-ups
- Example: User says "it's broken" → bot asks specifics → user says "yeah" → bot forced to answer with minimal info

**Fix:** Change from count-based to context-based
```python
if has_enough_context():  # Check actual message content, not just turns
    return "answer"
```

---

## 5. VOICE PIPELINE

### ✅ Working
- Whisper STT works (tiny.en, CPU, fast)
- Edge TTS works (en-US-GuyNeural)
- WebSocket streaming works
- Audio encoding/decoding works

### 🚨 Issues
- Voice → text → inference → speech pipeline has 4-8 second latency
  - STT: 1-2s (tiny.en is fast but sometimes misses words)
  - LLM: 2-4s (llama3.1:8b inference)
  - TTS: 1-2s (depends on response length)
  - Network: negligible
- **User Experience:** Feels slow; audio playback queue sometimes stutters
- **Fix:** Consider streaming TTS chunks instead of waiting for full response

---

## PRIORITY FIX ROADMAP

### Phase 1 (Now) — Reliability
- [x] Fix HF → Ollama fallback
- [x] Add detailed error logging
- [ ] Set HF models to "use at own risk" / provide warning
- [ ] Validate Ollama is running on startup

### Phase 2 (Next) — UX Clarity  
- [ ] Redesign status indicator (show current model + inference time)
- [ ] Add visual state machine for voice recording
- [ ] Style error messages distinctly
- [ ] Improve model selector with explanations
- [ ] Better sources display (relevance badges)

### Phase 3 (Polish) — Performance
- [ ] Stream TTS chunks instead of waiting for full response
- [ ] Improve RAG scoring for better diagnostic alignment
- [ ] Reduce STT latency (maybe switch to base.en from tiny.en)
- [ ] Add response caching for common questions

---

## QUICK WINS (< 1 hour each)

1. **Add error styling** → Users see errors are errors
2. **Improve status text** → Show "Using llama3.1:8b" instead of blank
3. **Voice button feedback** → Change text to show state ("Listening...", "Processing...")
4. **Add model-selector help text** → Explain what each model is
5. **Validate Ollama on startup** → Fail gracefully if unavailable

---

## TEST CHECKLIST

Before shipping any changes, test:

- [ ] Chat with text input → gets response
- [ ] Chat with voice input → gets response
- [ ] Switch models in dropdown → next request uses new model
- [ ] HF model times out → falls back to Ollama silently
- [ ] Ollama unavailable → shows clear error
- [ ] Long response → TTS doesn't stutter
- [ ] Rapid questions → state doesn't get confused
- [ ] Mobile layout → buttons don't overflow
- [ ] Voice on iOS Safari → works (permissions)
- [ ] Voice on Android Chrome → works (permissions)

---

## CONCLUSION

**Current State:** Functional but rough UX. Diagnostic bot logic is excellent; infrastructure needs polish.

**Main Issues:**
1. HF API unreliability → users see fallback errors
2. Status/state not visible to users → confusion
3. Voice flow lacks visual feedback → unclear what's happening

**Next Focus:** Make the *user experience* match the quality of the underlying bot logic.
