"""
Vocera - Teams Meeting Side Panel bridge
-------------------------------------------
This is the local server that makes the "Start"/"Stop" button inside
your Teams meeting side panel actually work.

It does three jobs:
1. Serves the tiny side-panel web page (web/tab.html) and its config
   page (web/config.html) that Teams loads inside the meeting.
2. Exposes /start and /stop so the panel's buttons can turn your Azure
   speech recognizer on and off.
3. Runs the same NLP word->sign mapping as before, and pushes each
   recognized sequence to the panel over a WebSocket so it can play
   the matching clips.

Run this on your own machine, expose it over HTTPS with a dev tunnel,
and point your Teams app manifest at that tunnel URL. See README.md.
"""

import os
import time
import json
import threading
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

import azure.cognitiveservices.speech as speechsdk
import nltk
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from dotenv import load_dotenv

# ------------------ CONFIG ------------------

load_dotenv("Azure_keys.env")
SUBSCRIPTION_KEY = os.getenv("AZURE_SPEECH_KEY")
REGION = os.getenv("AZURE_SPEECH_REGION")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_PATH = os.path.join(BASE_DIR, "assets")
WEB_PATH = os.path.join(BASE_DIR, "web")

app = FastAPI()
app.mount("/assets", StaticFiles(directory=ASSETS_PATH), name="assets")

# ------------------ SHARED STATE ------------------

listening = False
recognizer_thread = None
main_loop = None
clients = set()

# ------------------ TEXT -> SIGN SEQUENCE ------------------
# Unchanged from the original app.py.

def process_text_to_animation_sequence(text):
    text = text.lower()
    words = word_tokenize(text)
    tagged = nltk.pos_tag(words)
    tense = {
        "future": len([w for w in tagged if w[1] == "MD"]),
        "present": len([w for w in tagged if w[1] in ["VBP", "VBZ", "VBG"]]),
        "past": len([w for w in tagged if w[1] in ["VBD", "VBN"]]),
        "present_continuous": len([w for w in tagged if w[1] == "VBG"])
    }
    stop_words = set(nltk.corpus.stopwords.words('english'))
    lr = WordNetLemmatizer()
    filtered = []
    for w, p in tagged:
        if w not in stop_words:
            if p in ['VBG', 'VBD', 'VBZ', 'VBN', 'NN']:
                filtered.append(lr.lemmatize(w, pos='v'))
            elif p in ['JJ', 'JJR', 'JJS', 'RBR', 'RBS']:
                filtered.append(lr.lemmatize(w, pos='a'))
            else:
                filtered.append(lr.lemmatize(w))
    words = ['Me' if w == 'I' else w for w in filtered]
    probable_tense = max(tense, key=tense.get)
    if probable_tense == "past":
        words = ["Before"] + words
    elif probable_tense == "future" and "will" not in words:
        words = ["Will"] + words
    elif probable_tense == "present" and tense["present_continuous"] >= 1:
        words = ["Now"] + words
    final_sequence = []
    for w in words:
        file_name = w.title() + ".mp4"
        path = os.path.join(ASSETS_PATH, file_name)
        if not os.path.exists(path):
            final_sequence.extend(list(w))  # fallback: fingerspell
        else:
            final_sequence.append(w.title())
    return final_sequence

# ------------------ SPEECH THREAD ------------------

def handle_result(evt):
    if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
        text = evt.result.text
        if not text.strip():
            return
        print(f"[Speech] Recognized: {text}")
        seq = process_text_to_animation_sequence(text)
        print("[Sequence]", seq)
        message = {"type": "sequence", "text": text, "clips": seq}
        if main_loop:
            asyncio.run_coroutine_threadsafe(broadcast(message), main_loop)
    elif evt.result.reason == speechsdk.ResultReason.NoMatch:
        print("[Speech] NoMatch: could not recognize speech.")


def run_recognition():
    global listening
    speech_config = speechsdk.SpeechConfig(subscription=SUBSCRIPTION_KEY, region=REGION)
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    recognizer.recognized.connect(handle_result)
    recognizer.start_continuous_recognition()
    print("[Speech] Listening...")
    while listening:
        time.sleep(0.3)
    recognizer.stop_continuous_recognition()
    print("[Speech] Stopped.")


async def broadcast(message):
    dead = set()
    payload = json.dumps(message)
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)

# ------------------ ROUTES ------------------

@app.on_event("startup")
async def on_startup():
    global main_loop
    main_loop = asyncio.get_event_loop()


@app.get("/")
async def root():
    return FileResponse(os.path.join(WEB_PATH, "tab.html"))


@app.get("/tab.html")
async def tab():
    return FileResponse(os.path.join(WEB_PATH, "tab.html"))


@app.get("/config.html")
async def config():
    return FileResponse(os.path.join(WEB_PATH, "config.html"))


@app.post("/start")
async def start():
    global listening, recognizer_thread
    if not listening:
        listening = True
        recognizer_thread = threading.Thread(target=run_recognition, daemon=True)
        recognizer_thread.start()
    return {"status": "listening"}


@app.post("/stop")
async def stop():
    global listening
    listening = False
    return {"status": "stopped"}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; content ignored
    except WebSocketDisconnect:
        clients.discard(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
