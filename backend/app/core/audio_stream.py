# backend/app/core/audio_stream.py
import time
import numpy as np
import sounddevice as sd
from .config import SonarConfig
from .ring_buffer import RingBuffer

class DuplexAudioPipeline:
    def __init__(self, config: SonarConfig = SonarConfig()):
        self.cfg = config
        self.rx_buffer = RingBuffer(
            capacity=self.cfg.ring_buffer_size, 
            channels=self.cfg.in_channels
        )
        
        self.stream = None
        self.is_running = False
        
        # Diagnostic counters
        self.overflow_count = 0
        self.underflow_count = 0
        
        # Pre-synthesize repeating FMCW chirp sequence
        self.tx_signal = self._build_tx_sequence()
        self.tx_pointer = 0

    def _build_tx_sequence(self) -> np.ndarray:
        """Builds a continuous FMCW linear chirp followed by zero-padding."""
        fs = self.cfg.sample_rate
        chirp_len = int(fs * self.cfg.chirp_duration)
        pri_len = int(fs * self.cfg.pulse_repetition_interval)
        
        t = np.linspace(0, self.cfg.chirp_duration, chirp_len, endpoint=False)
        # Linear frequency sweep: f(t) = f0 + ((f1 - f0) / T) * t
        freq_slope = (self.cfg.chirp_f1 - self.cfg.chirp_f0) / self.cfg.chirp_duration
        phase = 2.0 * np.pi * (self.cfg.chirp_f0 * t + 0.5 * freq_slope * (t ** 2))
        chirp = np.sin(phase).astype(np.float32)
        
        # Apply Tukey taper window to prevent speaker click at start/stop
        window = np.ones(chirp_len, dtype=np.float32)
        edge = int(chirp_len * 0.1)
        window[:edge] = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, edge)))
        window[-edge:] = 0.5 * (1.0 - np.cos(np.linspace(np.pi, 0, edge)))
        chirp *= window

        # Pad with silence up to pulse repetition interval (listen for echoes)
        pulse = np.zeros(pri_len, dtype=np.float32)
        pulse[:chirp_len] = chirp * 0.8  # 80% max amplitude to prevent DAC clipping
        
        # Replicate across both output channels if stereo out
        stereo_tx = np.zeros((pri_len, self.cfg.out_channels), dtype=np.float32)
        for ch in range(self.cfg.out_channels):
            stereo_tx[:, ch] = pulse
            
        return stereo_tx

    def _audio_callback(self, indata, outdata, frames, time_info, status):
        """Audio thread callback. Must remain non-blocking (no prints, no file I/O)."""
        if status.input_overflow:
            self.overflow_count += 1
        if status.output_underflow:
            self.underflow_count += 1

        # 1. Pipe incoming microphone audio directly into our ring buffer
        self.rx_buffer.write(indata)

        # 2. Feed outgoing chirp pattern into the speakers
        remaining = len(self.tx_signal) - self.tx_pointer
        if remaining >= frames:
            outdata[:] = self.tx_signal[self.tx_pointer:self.tx_pointer + frames]
            self.tx_pointer = (self.tx_pointer + frames) % len(self.tx_signal)
        else:
            # Wrap around boundary
            outdata[:remaining] = self.tx_signal[self.tx_pointer:]
            leftover = frames - remaining
            outdata[remaining:] = self.tx_signal[:leftover]
            self.tx_pointer = leftover

    def start(self):
        """Initializes hardware devices and opens duplex audio stream."""
        if self.is_running:
            return

        self.rx_buffer.clear()
        self.tx_pointer = 0
        
        self.stream = sd.Stream(
            samplerate=self.cfg.sample_rate,
            blocksize=self.cfg.buffer_frames,
            channels=(self.cfg.in_channels, self.cfg.out_channels),
            dtype='float32',
            callback=self._audio_callback
        )
        self.stream.start()
        self.is_running = True

    def stop(self):
        """Closes stream and releases hardware handles."""
        if not self.is_running:
            return
        self.is_running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def get_latest_rx(self, num_samples: int) -> np.ndarray:
        """Public helper to pull latest recorded microphone block for DSP processing."""
        return self.rx_buffer.read_latest(num_samples)