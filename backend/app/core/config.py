"""
Acoustic-Camera Configuration
Author: Nikita Zhuravlov
"""
from dataclasses import dataclass

@dataclass
class SonarConfig:
    sample_rate: int = 48000
    
    # Mode: "stereo" or "mono"
    operating_mode: str = "stereo"
    
    # Audio I/O channels
    # Stereo requires 2 input channels; Mono uses 1
    in_channels: int = 2
    out_channels: int = 2
    
    # PortAudio device indices (None = system default)
    input_device_index: int | None = None
    output_device_index: int | None = None
    
    buffer_frames: int = 1024
    ring_buffer_size: int = 48000 * 2
    
    # Acoustic FMCW chirp parameters (within flat response curve of commercial drivers)
    chirp_f0: float = 3800.0
    chirp_f1: float = 7800.0
    chirp_duration: float = 0.04
    pulse_repetition_interval: float = 0.08
    
    # Metric bounding volume
    max_range_m: float = 2.2
    
    # Stereo physical capsule spacing (in meters)
    # Typical laptop dual-mic arrays: 0.12m - 0.18m. Desktop stereo pairs: adjust to your setup.
    mic_separation_m: float = 0.15