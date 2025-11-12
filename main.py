import os
import json
import asyncio
from base64 import b64encode
from dotenv import load_dotenv
from openai import OpenAI
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

load_dotenv()

DID_API_KEY = os.getenv("DID_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")          
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")  
if not ELEVENLABS_API_KEY:
    raise ValueError("ELEVENLABS_API_KEY is required in .env")    



# Validate
missing = [k for k, v in {
    "DID_API_KEY": DID_API_KEY,
    "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
    "OPENAI_API_KEY": OPENAI_API_KEY
}.items() if not v]
if missing:
    raise ValueError(f"Missing env vars: {', '.join(missing)}")

client = OpenAI(api_key=OPENAI_API_KEY)

# D-ID headers 
# --> keep same base64 encoding as your working reference (no trailing colon)
b64 = b64encode(DID_API_KEY.encode("ascii")).decode("ascii")
did_headers = {
    "Authorization": f"Basic {b64}",
    "Content-Type": "application/json"
}

app = FastAPI()
frontend_path = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

conversations = {}
welcome_shown = set()


def get_gpt_response(user_message, conv_id):
    if conv_id not in conversations:
        conversations[conv_id] = [
            {"role": "system", "content": "You are a friendly AI. Keep replies short."}
        ]
    conversations[conv_id].append({"role": "user", "content": user_message})

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=conversations[conv_id],
        max_tokens=150,
        temperature=0.7
    )
    txt = resp.choices[0].message.content.strip()
    conversations[conv_id].append({"role": "assistant", "content": txt})
    return txt




def create_did_video(text):
    # --> minimal change: do NOT include 'api_key' in provider; match working reference
    data = {
        "script": {
            "type": "text",
            "input": text,
            "provider": {
                "type": "elevenlabs",
                "voice_id": ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"
            }
        },
        "presenter_id": "amy-jcwCkr1grs",
        "config": {"fluent": False, "pad_audio": 0.0}
    }

    print("\n=== D-ID PAYLOAD ===")
    print(json.dumps(data, indent=2))

    response = requests.post("https://api.d-id.com/talks", json=data, headers=did_headers)
    print(f"D-ID response: {response.status_code} {response.text}")

    if response.status_code == 201:
        return response.json().get('id')
    return None


async def wait_for_video(video_id, max_attempts=60):
    for _ in range(max_attempts):
        await asyncio.sleep(3)
        resp = requests.get(f"https://api.d-id.com/talks/{video_id}", headers=did_headers)
        if resp.status_code != 200:
            continue
        data = resp.json()
        if data.get("status") == "done":
            return data.get("result_url")
        if data.get("status") == "error":
            print("D-ID error:", data)
            return None
    return None


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    conv_id = str(id(ws))
    welcome_key = conv_id

    try:
        # ---- WELCOME VIDEO (once) ----
        if welcome_key not in welcome_shown:
            welcome_shown.add(welcome_key)
            await ws.send_json({"type": "welcome", "video_url": "/static/welcome.mp4"})
            await asyncio.sleep(1)

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw).get("message", "").strip()
            if not msg:
                continue

            # 1. Thinking → still image
            await ws.send_json({
                "type": "status",
                "message": "Thinking...",
                "image": "/static/loading-avatar.png"
            })

            # 2. GPT
            gpt_text = await asyncio.to_thread(get_gpt_response, msg, conv_id)
            await ws.send_json({"type": "text_response", "message": gpt_text})

            # 3. Speaking → still image
            await ws.send_json({
                "type": "status",
                "message": "Speaking...",
                "image": "/static/loading-avatar.png"
            })

            # 4. D-ID
            talk_id = await asyncio.to_thread(create_did_video, gpt_text)
            if not talk_id:
                await ws.send_json({"type": "error", "message": "Failed to start video"})
                continue

            video_url = await wait_for_video(talk_id)
            if video_url:
                await ws.send_json({
                    "type": "video_ready",
                    "video_url": video_url,
                    "message": gpt_text
                })
            else:
                await ws.send_json({"type": "error", "message": "Video timed out"})

    except WebSocketDisconnect:
        conversations.pop(conv_id, None)
        welcome_shown.discard(welcome_key)
    except Exception as e:
        print("WS error:", e)
        await ws.send_json({"type": "error", "message": "Server error"}) 


@app.get("/")
async def root():
    return FileResponse(frontend_path / "index.html")
