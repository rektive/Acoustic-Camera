# backend/app/api/server.py
import asyncio
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ..core.config import SonarConfig
from ..core.audio_stream import DuplexAudioPipeline
from ..core.canceller import EchoProcessor

app = FastAPI(title="Real-Time Acoustic Camera")

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
            ascan, image_2d = processor.process_live_frame(raw_audio)
            
            # Pack binary frame:
            # 16-byte aligned header: [width, height, ascan_len, 0]
            header = np.array([processor.grid_w, processor.grid_h, processor.output_bins, 0], dtype=np.uint32)
            
            # Concatenate header + float32 arrays
            payload = header.tobytes() + ascan.tobytes() + image_2d.tobytes()
            await websocket.send_bytes(payload)
            
            # ~30 FPS loop
            await asyncio.sleep(0.033)

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass