# backend/app/core/canceller.py
import numpy as np
from scipy import signal
from .config import SonarConfig

class EchoProcessor:
    def __init__(self, config: SonarConfig = SonarConfig()):
        self.cfg = config
        self.c = 343.0
        self.max_range_m = 2.5
        self.max_sample_delay = int((2.0 * self.max_range_m / self.c) * self.cfg.sample_rate)
        
        self.reference_chirp = self._generate_reference_chirp()
        self.background_profile = None
        self.alpha = 0.05

    def _generate_reference_chirp(self) -> np.ndarray:
        fs = self.cfg.sample_rate
        n_samples = int(fs * self.cfg.chirp_duration)
        t = np.linspace(0, self.cfg.chirp_duration, n_samples, endpoint=False)
        
        freq_slope = (self.cfg.chirp_f1 - self.cfg.chirp_f0) / self.cfg.chirp_duration
        phase = 2.0 * np.pi * (self.cfg.chirp_f0 * t + 0.5 * freq_slope * (t ** 2))
        chirp = np.sin(phase).astype(np.float32)
        
        window = np.ones(n_samples, dtype=np.float32)
        edge = int(n_samples * 0.1)
        window[:edge] = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, edge)))
        window[-edge:] = 0.5 * (1.0 - np.cos(np.linspace(np.pi, 0, edge)))
        return chirp * window

    def matched_filter(self, channel_data: np.ndarray) -> np.ndarray:
        corr = signal.correlate(channel_data.flatten(), self.reference_chirp, mode='full', method='fft')
        envelope = np.abs(signal.hilbert(corr)).astype(np.float32)
        
        chirp_len = len(self.reference_chirp)
        valid_envelope = envelope[chirp_len - 1:]
        return valid_envelope[:self.max_sample_delay]

    def process_frame(self, audio_block: np.ndarray) -> np.ndarray:
        """Processes 1D mono audio block and subtracts direct-path speaker crosstalk."""
        corr = self.matched_filter(audio_block)

        if self.background_profile is None:
            self.background_profile = corr.copy()
            return np.zeros_like(corr)

        # Dynamic echo extraction
        dynamic = np.maximum(corr - self.background_profile, 0.0)
        
        # Adaptive background update
        self.background_profile = (1.0 - self.alpha) * self.background_profile + self.alpha * corr

        # Normalize 0.0 to 1.0
        max_val = np.max(dynamic)
        if max_val > 1e-5:
            dynamic = dynamic / max_val

        return dynamic

    def sample_index_to_meters(self, index: int) -> float:
        return (index / self.cfg.sample_rate * self.c) / 2.0