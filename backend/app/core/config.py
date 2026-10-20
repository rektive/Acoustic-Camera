# backend/app/core/config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class SonarConfig:
    sample_rate: int = 48000
    
    # Mono capture from Fifine ME6S, stereo output to wired speaker
    in_channels: int = 1
    out_channels: int = 2
    
    # Set to device 8 (ME6S) or None for system default
    input_device_index: int | None = 8
    output_device_index: int | None = None
    
    buffer_frames: int = 1024
    ring_buffer_size: int = 48000 * 2
    
    # FMCW chirp sweep parameters (18.5 kHz - 21.5 kHz)
    chirp_f0: float = 18500.0
    chirp_f1: float = 21500.0
    chirp_duration: float = 0.04
    pulse_repetition_interval: float = 0.08
    
    # Physical space scale (meters)
    max_range_m: float = 2.5