# backend/app/core/canceller.py
import numpy as np
from scipy import signal
from .config import SonarConfig

class EchoProcessor:
    def __init__(self, config: SonarConfig = SonarConfig()):
        self.cfg = config
        self.c = 343.0
        self.max_sample_delay = int((2.0 * self.cfg.max_range_m / self.c) * self.cfg.sample_rate)
        
        self.reference_chirp = self._generate_reference_chirp()
        self.background_profile = None
        self.alpha = 0.08
        
        # Number of output distance bins sent to frontend
        self.output_bins = 200

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

    def process_frame(self, audio_block: np.ndarray) -> np.ndarray:
        flat_audio = audio_block.flatten()
        
        # 1. Matched filter via FFT correlation
        corr = signal.correlate(flat_audio, self.reference_chirp, mode='full', method='fft')
        envelope = np.abs(signal.hilbert(corr)).astype(np.float32)
        
        valid = envelope[len(self.reference_chirp) - 1: len(self.reference_chirp) - 1 + self.max_sample_delay]
        
        # 2. Resample to standard display resolution (200 bins)
        indices = np.linspace(0, len(valid) - 1, self.output_bins).astype(int)
        profile = valid[indices]

        # 3. Direct-path speaker crosstalk cancellation
        if self.background_profile is None:
            self.background_profile = profile.copy()
            return np.zeros(self.output_bins, dtype=np.float32)

        dynamic = np.maximum(profile - self.background_profile, 0.0)
        self.background_profile = (1.0 - self.alpha) * self.background_profile + self.alpha * profile

        # 4. Normalize 0.0 to 1.0 with contrast power
        peak = np.max(dynamic)
        if peak > 1e-4:
            dynamic = dynamic / peak
            dynamic = np.power(dynamic, 1.6)
            
        return dynamic.astype(np.float32)