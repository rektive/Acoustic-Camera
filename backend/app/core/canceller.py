# backend/app/core/canceller.py
from collections import deque
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
        self.alpha = 0.06
        
        # 1D A-Scan display resolution
        self.output_bins = 200
        self.smoothed_ascan = np.zeros(self.output_bins, dtype=np.float32)

        # 2D Live Grid Dimensions (80x80 gives optimal 30 FPS performance)
        self.grid_w = 80
        self.grid_h = 80
        self.x_coords = np.linspace(-0.8, 0.8, self.grid_w, dtype=np.float32)
        self.y_coords = np.linspace(0.2, 2.0, self.grid_h, dtype=np.float32)

        # Rolling aperture buffer (~0.8s of motion history)
        self.rolling_len = 24
        self.aperture_len_m = 0.40
        self.envelope_buffer = deque(maxlen=self.rolling_len)

        # Precompute backprojection distance & sample index lookup tables
        self.index_table = np.zeros((self.rolling_len, self.grid_h, self.grid_w), dtype=np.int32)
        self.tgc_table = np.zeros((self.rolling_len, self.grid_h, self.grid_w), dtype=np.float32)
        self._precompute_spatial_tables()

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

    def _precompute_spatial_tables(self):
        sensor_x = np.linspace(-self.aperture_len_m / 2.0, self.aperture_len_m / 2.0, self.rolling_len)
        XX, YY = np.meshgrid(self.x_coords, self.y_coords)

        for k in range(self.rolling_len):
            # Round-trip distance from synthetic aperture point to (x, y)
            dist_k = 2.0 * np.sqrt((XX - sensor_x[k]) ** 2 + (YY ** 2))
            sample_idx = np.round((dist_k / self.c) * self.cfg.sample_rate).astype(np.int32)
            self.index_table[k] = np.clip(sample_idx, 0, self.max_sample_delay - 1)
            # Distance attenuation compensation
            self.tgc_table[k] = (YY / 0.2) ** 1.3

    def process_live_frame(self, audio_block: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        flat = audio_block.flatten()
        
        # 1. Matched filter
        corr = signal.correlate(flat, self.reference_chirp, mode='full', method='fft')
        envelope = np.abs(signal.hilbert(corr)).astype(np.float32)
        chirp_len = len(self.reference_chirp)
        raw_env = envelope[chirp_len - 1: chirp_len - 1 + self.max_sample_delay]

        # 2. Resample for 1D A-Scan monitor
        indices_1d = np.linspace(0, len(raw_env) - 1, self.output_bins).astype(int)
        profile_1d = raw_env[indices_1d]

        # 3. Direct-path speaker crosstalk cancellation
        if self.background_profile is None:
            self.background_profile = profile_1d.copy()
            clean_1d = np.zeros(self.output_bins, dtype=np.float32)
        else:
            dynamic_1d = np.maximum(profile_1d - self.background_profile, 0.0)
            self.background_profile = (1.0 - self.alpha) * self.background_profile + self.alpha * profile_1d

            peak = np.max(dynamic_1d)
            if peak > 1e-4:
                clean_1d = np.power(dynamic_1d / peak, 1.4)
            else:
                clean_1d = np.zeros(self.output_bins, dtype=np.float32)

        self.smoothed_ascan = 0.65 * self.smoothed_ascan + 0.35 * clean_1d

        # 4. Push to rolling aperture buffer
        self.envelope_buffer.append(raw_env)

        # 5. Live 2D backprojection across the rolling buffer
        buf_len = len(self.envelope_buffer)
        image_2d = np.zeros((self.grid_h, self.grid_w), dtype=np.float32)

        for k in range(buf_len):
            env_k = self.envelope_buffer[k]
            image_2d += env_k[self.index_table[k]] * self.tgc_table[k]

        max_2d = np.max(image_2d)
        if max_2d > 1e-5:
            # Contrast boost to focus reflective targets
            image_2d = np.maximum((image_2d / max_2d) - 0.25, 0.0) / 0.75
            image_2d = np.power(image_2d, 2.0)
        else:
            image_2d.fill(0)

        return self.smoothed_ascan.astype(np.float32), image_2d.astype(np.float32)