# backend/app/api/server.py
import asyncio
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ..core.config import SonarConfig
from ..core.audio_stream import DuplexAudioPipeline
from ..core.canceller import EchoProcessor

app = FastAPI(title="Acoustic Sonar Visualizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cfg = SonarConfig()
pipeline = DuplexAudioPipeline(config=cfg)
processor = EchoProcessor(config=cfg)

@app.on_event("startup")
def startup_event():
    pipeline.start()

@app.on_event("shutdown")
def shutdown_event():
    pipeline.stop()

@app.websocket("/ws/sonar")
async def sonar_stream(websocket: WebSocket):
    await websocket.accept()
    pri_samples = int(cfg.sample_rate * cfg.pulse_repetition_interval)
    
    try:
        while True:
            raw_audio = pipeline.get_latest_rx(pri_samples)
            frame = processor.process_frame(raw_audio)
            
            # Send raw Float32 binary bytes over WebSocket
            await websocket.send_bytes(frame.tobytes())
            
            # ~30 FPS loop
            await asyncio.sleep(0.033)
            
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass