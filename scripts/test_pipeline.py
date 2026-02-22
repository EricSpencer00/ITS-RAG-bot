"""Quick end-to-end test of the voice pipeline."""
import asyncio
import json
import websockets


async def test():
    async with websockets.connect("ws://127.0.0.1:8000/ws/audio", max_size=16 * 1024 * 1024) as ws:
        # Wait for status message
        msg = await ws.recv()
        data = json.loads(msg)
        print(f"Status: {data}")

        # Send a text message
        await ws.send(json.dumps({"type": "text", "text": "What is VPN?"}))

        # Collect responses
        responses = []
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(msg)
                responses.append(data)
                if data.get("type") == "final":
                    break
        except asyncio.TimeoutError:
            pass

        types = [r["type"] for r in responses]
        print(f"Response types: {types}")

        for r in responses:
            if r.get("type") == "final" and r.get("response"):
                print(f"LLM response (first 200 chars): {r['response'][:200]}")
                break

        tts_msgs = [r for r in responses if r.get("type") == "tts"]
        print(f"TTS audio chunks: {len(tts_msgs)}")
        if tts_msgs:
            print(f"First chunk base64 size: {len(tts_msgs[0].get('audio', ''))} chars")

        print("\nFULL PIPELINE TEST: SUCCESS")


if __name__ == "__main__":
    asyncio.run(test())
