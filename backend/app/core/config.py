# backend/app/core/config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class SonarConfig:
    sample_rate: int = 48000
    
    in_channels: int = 1
    out_channels: int = 2
    
    # 8 for Fifine ME6S, None for default system speaker
    input_device_index: int | None = 8
    output_device_index: int | None = None
    
    buffer_frames: int = 1024
    ring_buffer_size: int = 48000 * 2
    
    # 3.5 kHz - 7.5 kHz chirp: Wide bandwidth for high resolution,
    # fully within the frequency response of normal speakers and mics
    chirp_f0: float = 3500.0
    chirp_f1: float = 7500.0
    chirp_duration: float = 0.04
    pulse_repetition_interval: float = 0.08
    
    max_range_m: float = 2.5