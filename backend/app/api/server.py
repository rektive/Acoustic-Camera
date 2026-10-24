"""
Acoustic Camera WebSocket Streaming Server
Author: Nikita Zhuravlov
"""
import asyncio
import json
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ..core.config import SonarConfig
from ..core.audio_stream import DuplexAudioPipeline
from ..core.canceller import EchoProcessor

app = FastAPI(title="Precision Acoustic Camera")

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
current_mode = cfg.operating_mode

def reconfigure_pipeline(mode: str):
    global pipeline, processor, current_mode, cfg
    current_mode = mode
    cfg.operating_mode = mode
    cfg.in_channels = 2 if mode == "stereo" else 1
    
    pipeline.stop()
    pipeline = DuplexAudioPipeline(config=cfg)
    processor = EchoProcessor(config=cfg)
    pipeline.start()

@app.on_event("startup")
def startup_event():
    try:
        pipeline.start()
    except Exception as e:
        print(f"[Warning] Fallback on mono stream if stereo default is missing: {e}")
        reconfigure_pipeline("mono")

@app.on_event("shutdown")
def shutdown_event():
    pipeline.stop()

@app.websocket("/ws/sonar")
async def sonar_stream(websocket: WebSocket):
    global current_mode
    await websocket.accept()
    pri_samples = int(cfg.sample_rate * cfg.pulse_repetition_interval)

    async def incoming_router():
        global current_mode
        try:
            while True:
                msg = await websocket.receive_text()
                data = json.loads(msg)
                if data.get("action") == "SET_MODE":
                    target_mode = data.get("mode", "stereo")
                    if target_mode != current_mode:
                        reconfigure_pipeline(target_mode)
        except Exception:
            pass

    router_task = asyncio.create_task(incoming_router())

    try:
        while True:
            raw_audio = pipeline.get_latest_rx(pri_samples)
            ascan, image_2d = processor.process_frame(raw_audio, current_mode)

            # 16-byte header: [width, height, ascan_length, mode_code (1=mono, 2=stereo)]
            mode_code = 2 if current_mode == "stereo" else 1
            header = np.array([processor.grid_w, processor.grid_h, processor.output_bins, mode_code], dtype=np.uint32)
            
            payload = header.tobytes() + ascan.tobytes() + image_2d.tobytes()
            await websocket.send_bytes(payload)
            await asyncio.sleep(0.033)

    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        router_task.cancel()