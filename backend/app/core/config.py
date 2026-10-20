# backend/app/core/config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class SonarConfig:
    # 48000 Hz or 44100 Hz. 48k is standard on most modern laptop soundcards
    sample_rate: int = 48000
    
    # 2 output channels (stereo speakers) and 2 input channels (stereo mic array)
    in_channels: int = 2
    out_channels: int = 2
    
    # Block size per callback. 1024 frames @ 48kHz = ~21.3ms per audio slice
    buffer_frames: int = 1024
    
    # Ring buffer capacity (holds ~2 seconds of continuous stereo audio)
    ring_buffer_size: int = 48000 * 2
    
    # Ultrasonic FMCW chirp parameters
    chirp_f0: float = 18500.0  # start freq (Hz)
    chirp_f1: float = 21500.0  # end freq (Hz)
    chirp_duration: float = 0.04  # 40ms sweep duration
    pulse_repetition_interval: float = 0.08  # 80ms interval (40ms chirp + 40ms silence for echoes)