# backend/app/core/audio_stream.py
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
        
        self.tx_signal = self._build_tx_sequence()
        self.tx_pointer = 0

    def _build_tx_sequence(self) -> np.ndarray:
        fs = self.cfg.sample_rate
        chirp_len = int(fs * self.cfg.chirp_duration)
        pri_len = int(fs * self.cfg.pulse_repetition_interval)
        
        t = np.linspace(0, self.cfg.chirp_duration, chirp_len, endpoint=False)
        freq_slope = (self.cfg.chirp_f1 - self.cfg.chirp_f0) / self.cfg.chirp_duration
        phase = 2.0 * np.pi * (self.cfg.chirp_f0 * t + 0.5 * freq_slope * (t ** 2))
        chirp = np.sin(phase).astype(np.float32)
        
        # Apply Tukey window to soften speaker clicks
        window = np.ones(chirp_len, dtype=np.float32)
        edge = int(chirp_len * 0.1)
        window[:edge] = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, edge)))
        window[-edge:] = 0.5 * (1.0 - np.cos(np.linspace(np.pi, 0, edge)))
        chirp *= window

        pulse = np.zeros(pri_len, dtype=np.float32)
        pulse[:chirp_len] = chirp * 0.8
        
        # Duplicate to stereo outputs for the speaker
        stereo_tx = np.zeros((pri_len, self.cfg.out_channels), dtype=np.float32)
        for ch in range(self.cfg.out_channels):
            stereo_tx[:, ch] = pulse
            
        return stereo_tx

    def _audio_callback(self, indata, outdata, frames, time_info, status):
        self.rx_buffer.write(indata)

        remaining = len(self.tx_signal) - self.tx_pointer
        if remaining >= frames:
            outdata[:] = self.tx_signal[self.tx_pointer:self.tx_pointer + frames]
            self.tx_pointer = (self.tx_pointer + frames) % len(self.tx_signal)
        else:
            outdata[:remaining] = self.tx_signal[self.tx_pointer:]
            leftover = frames - remaining
            outdata[remaining:] = self.tx_signal[:leftover]
            self.tx_pointer = leftover

    def start(self):
        if self.is_running:
            return

        self.rx_buffer.clear()
        self.tx_pointer = 0
        
        device_selection = (self.cfg.input_device_index, self.cfg.output_device_index)
        
        self.stream = sd.Stream(
            device=device_selection,
            samplerate=self.cfg.sample_rate,
            blocksize=self.cfg.buffer_frames,
            channels=(self.cfg.in_channels, self.cfg.out_channels),
            dtype='float32',
            callback=self._audio_callback
        )
        self.stream.start()
        self.is_running = True

    def stop(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def get_latest_rx(self, num_samples: int) -> np.ndarray:
        return self.rx_buffer.read_latest(num_samples)