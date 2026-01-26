# ITS Voice RAG Bot - PersonaPlex Edition

A **full-duplex speech-to-speech** conversational AI for ITS support, powered by [NVIDIA PersonaPlex](https://huggingface.co/nvidia/personaplex-7b-v1).

## Features

- 🎙️ **Real-time conversation**: Simultaneous listening and speaking
- 🔄 **Natural turn-taking**: Supports interruptions, barge-ins, and overlapping speech
- 🎭 **Voice customization**: Multiple natural and varied voice options
- 📝 **Persona control**: Define assistant personality via text prompts
- 🔊 **Low latency**: Streaming Opus audio for responsive interactions
- 📚 **RAG integration**: Document retrieval for ITS knowledge base (optional)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Browser                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Microphone → Opus Encoder → WebSocket → Server     │   │
│  │  Speaker   ← Opus Decoder ← WebSocket ← Server      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   PersonaPlex Server                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Mimi Encoder     PersonaPlex LM     Mimi Decoder   │   │
│  │  (Audio→Tokens)   (Text+Audio Gen)   (Tokens→Audio) │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  Voice Prompt (acoustic style) + Text Prompt (persona)      │
└─────────────────────────────────────────────────────────────┘
```

## Requirements

- **Python 3.10+**
- **NVIDIA GPU** with CUDA support (recommended)
  - Minimum: 16GB VRAM (with CPU offloading)
  - Recommended: 24GB+ VRAM (A100, H100)
- **HuggingFace account** with PersonaPlex license accepted

## Quick Start

### 1. Install Dependencies

```bash
# Install Opus codec
# macOS
brew install opus

# Ubuntu/Debian
sudo apt install libopus-dev

# Fedora/RHEL
sudo dnf install opus-devel
```

### 2. Set Up Environment

```bash
# Clone this repo
git clone https://github.com/your-org/live-bot-its.git
cd live-bot-its

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Run setup script
python scripts/setup_personaplex.py
```

### 3. Configure HuggingFace Token

1. Get your token at: https://huggingface.co/settings/tokens
2. Accept the PersonaPlex license at: https://huggingface.co/nvidia/personaplex-7b-v1
3. Set the token:

```bash
export HF_TOKEN=your_token_here
```

Or create a `.env` file:
```
HF_TOKEN=your_token_here
```

### 4. Run the Server

```bash
python scripts/run_dev.py
```

The server will:
1. Download the model (~14GB on first run)
2. Generate SSL certificates
3. Start on https://your-ip:8998

### 5. Open in Browser

Navigate to the URL shown in the terminal. Accept the self-signed certificate warning to proceed.

## Configuration

Environment variables (set in `.env` or export):

| Variable | Default | Description |
|----------|---------|-------------|
| `HF_TOKEN` | (required) | HuggingFace API token |
| `PERSONAPLEX_DEVICE` | `cuda` | Device to run on (`cuda`, `cpu`) |
| `PERSONAPLEX_CPU_OFFLOAD` | `false` | Enable CPU offloading for low VRAM |
| `DEFAULT_VOICE_PROMPT` | `NATF2` | Default voice (see below) |
| `DEFAULT_TEXT_PROMPT` | `You are a helpful...` | Persona description |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8998` | Server port |

### Available Voices

**Natural voices** (more conversational):
- `NATF0`, `NATF1`, `NATF2`, `NATF3` - Female
- `NATM0`, `NATM1`, `NATM2`, `NATM3` - Male

**Variety voices** (more diverse):
- `VARF0`, `VARF1`, `VARF2`, `VARF3`, `VARF4` - Female
- `VARM0`, `VARM1`, `VARM2`, `VARM3`, `VARM4` - Male

### Example Prompts

**ITS Support**:
```
You are a helpful ITS support assistant at Loyola University. You help users with technology questions about wifi, email, software, and campus systems.
```

**General Assistant**:
```
You are a wise and friendly teacher. Answer questions or provide advice in a clear and engaging way.
```

**Casual Conversation**:
```
You enjoy having a good conversation. Have a reflective conversation about technology and its impact on education.
```

## API Reference

### WebSocket Endpoint

`GET /api/chat`

Query parameters:
- `voice_prompt`: Voice name (e.g., `NATF2`)
- `text_prompt`: Persona description (URL encoded)
- `seed`: Random seed (-1 for random)

Binary message protocol:
- `0x00`: Handshake complete (server → client)
- `0x01 + data`: Audio data (Opus, bidirectional)
- `0x02 + data`: Text token (server → client)
- `0x03 + data`: Error (server → client)

### REST Endpoints

- `GET /api/status` - Server status and config
- `GET /api/voices` - List available voices

## Development

### Project Structure

```
app/
  ├── config.py          # Configuration
  ├── main.py            # Server entry point
  ├── voice/
  │   └── personaplex.py # PersonaPlex engine
  ├── rag/               # RAG components (optional)
  └── web/
      └── static/        # Frontend assets
scripts/
  ├── run_dev.py         # Dev server runner
  └── setup_personaplex.py
```

### Running with CPU Offloading

For GPUs with limited memory:

```bash
export PERSONAPLEX_CPU_OFFLOAD=true
pip install accelerate
python scripts/run_dev.py
```

### Docker (Coming Soon)

```bash
docker-compose up
```

## Troubleshooting

### "CUDA out of memory"
- Enable CPU offloading: `PERSONAPLEX_CPU_OFFLOAD=true`
- Or use a GPU with more VRAM

### "Model not found" / 401 Error
- Ensure `HF_TOKEN` is set correctly
- Verify you've accepted the license at HuggingFace

### No audio playback in browser
- Use HTTPS (required for microphone access)
- Accept the self-signed certificate
- Check browser permissions for microphone

### High latency
- Use a GPU with more VRAM
- Ensure good network connection
- Try wired ethernet instead of WiFi

## References

- [PersonaPlex Paper](https://research.nvidia.com/labs/adlr/files/personaplex/personaplex_preprint.pdf)
- [PersonaPlex GitHub](https://github.com/NVIDIA/personaplex)
- [Moshi Architecture](https://arxiv.org/abs/2410.00037)

## License

This project uses NVIDIA PersonaPlex under the [NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/).
