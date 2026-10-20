# backend/app/core/config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class SonarConfig:
    sample_rate: int = 48000
    
    # Mono input from Fifine ME6S, stereo output to wired speaker
    in_channels: int = 1
    out_channels: int = 2
    
    # Set to your specific PortAudio device indices (or None for default)
    # Hardware index 8 for ME6S
    input_device_index: int = 8
    output_device_index: int | None = None
    
    buffer_frames: int = 1024
    ring_buffer_size: int = 48000 * 2
    
    # FMCW chirp sweep
    chirp_f0: float = 18500.0
    chirp_f1: float = 21500.0
    chirp_duration: float = 0.04
    pulse_repetition_interval: float = 0.08