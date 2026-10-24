"""
DSP Engine: Dual-Mode Real-Time Beamforming & Synthetic Aperture Sonar
Author: Nikita Zhuravlov
"""
from collections import deque
import numpy as np
from scipy import signal
from .config import SonarConfig

class EchoProcessor:
    def __init__(self, config: SonarConfig):
        self.cfg = config
        self.c = 343.0
        self.max_sample_delay = int((2.0 * self.cfg.max_range_m / self.c) * self.cfg.sample_rate)
        
        self.reference_chirp = self._generate_reference_chirp()
        self.background_ascan = None
        self.alpha = 0.05
        
        # Display resolution
        self.output_bins = 200
        self.smoothed_ascan = np.zeros(self.output_bins, dtype=np.float32)

        # 2D Grid Coordinate Space (80 x 80 matrix)
        self.grid_w = 80
        self.grid_h = 80
        self.x_coords = np.linspace(-0.9, 0.9, self.grid_w, dtype=np.float32)
        self.y_coords = np.linspace(0.2, self.cfg.max_range_m, self.grid_h, dtype=np.float32)

        # SAS parameters (Mono)
        self.rolling_len = 20
        self.aperture_len_m = 0.35
        self.envelope_buffer = deque(maxlen=self.rolling_len)
        
        # Precomputed spatial matrices
        self.sas_index_table = np.zeros((self.rolling_len, self.grid_h, self.grid_w), dtype=np.int32)
        self.sas_tgc_table = np.zeros((self.rolling_len, self.grid_h, self.grid_w), dtype=np.float32)
        
        # Stereo beamforming tables
        self.stereo_idx_left = np.zeros((self.grid_h, self.grid_w), dtype=np.int32)
        self.stereo_idx_right = np.zeros((self.grid_h, self.grid_w), dtype=np.int32)
        self.stereo_tgc = np.zeros((self.grid_h, self.grid_w), dtype=np.float32)
        
        self._precompute_tables()

    def _generate_reference_chirp(self) -> np.ndarray:
        fs = self.cfg.sample_rate
        n = int(fs * self.cfg.chirp_duration)
        t = np.linspace(0, self.cfg.chirp_duration, n, endpoint=False)
        slope = (self.cfg.chirp_f1 - self.cfg.chirp_f0) / self.cfg.chirp_duration
        chirp = np.sin(2.0 * np.pi * (self.cfg.chirp_f0 * t + 0.5 * slope * (t ** 2))).astype(np.float32)
        
        window = np.hanning(n).astype(np.float32)
        return chirp * window

    def _precompute_tables(self):
        XX, YY = np.meshgrid(self.x_coords, self.y_coords)
        fs = self.cfg.sample_rate
        
        # 1. Precompute Stereo Delay-and-Sum Lookup
        d = self.cfg.mic_separation_m
        r_tx = np.sqrt(XX**2 + YY**2)
        r_rx_left = np.sqrt((XX + d / 2.0)**2 + YY**2)
        r_rx_right = np.sqrt((XX - d / 2.0)**2 + YY**2)
        
        sample_l = np.round(((r_tx + r_rx_left) / self.c) * fs).astype(np.int32)
        sample_r = np.round(((r_tx + r_rx_right) / self.c) * fs).astype(np.int32)
        
        self.stereo_idx_left = np.clip(sample_l, 0, self.max_sample_delay - 1)
        self.stereo_idx_right = np.clip(sample_r, 0, self.max_sample_delay - 1)
        self.stereo_tgc = (YY / 0.2) ** 1.35

        # 2. Precompute Mono SAS Synthetic Aperture Lookup
        sensor_x = np.linspace(-self.aperture_len_m / 2.0, self.aperture_len_m / 2.0, self.rolling_len)
        for k in range(self.rolling_len):
            dist_k = 2.0 * np.sqrt((XX - sensor_x[k])**2 + YY**2)
            s_idx = np.round((dist_k / self.c) * fs).astype(np.int32)
            self.sas_index_table[k] = np.clip(s_idx, 0, self.max_sample_delay - 1)
            self.sas_tgc_table[k] = (YY / 0.2) ** 1.35

    def _extract_envelope(self, audio_vector: np.ndarray) -> np.ndarray:
        corr = signal.correlate(audio_vector, self.reference_chirp, mode='full', method='fft')
        envelope = np.abs(signal.hilbert(corr)).astype(np.float32)
        offset = len(self.reference_chirp) - 1
        return envelope[offset: offset + self.max_sample_delay]

    def process_frame(self, audio_block: np.ndarray, mode: str) -> tuple[np.ndarray, np.ndarray]:
        # Handle single or multi-channel input structures
        if audio_block.ndim == 1:
            left_raw = audio_block
            right_raw = audio_block
        else:
            left_raw = audio_block[:, 0]
            right_raw = audio_block[:, 1] if audio_block.shape[1] > 1 else audio_block[:, 0]

        env_l = self._extract_envelope(left_raw)
        
        # 1D A-Scan extraction
        indices_1d = np.linspace(0, len(env_l) - 1, self.output_bins).astype(int)
        profile_1d = env_l[indices_1d]

        # Background baseline cancellation
        if self.background_ascan is None:
            self.background_ascan = profile_1d.copy()
            clean_1d = np.zeros(self.output_bins, dtype=np.float32)
        else:
            dynamic = np.maximum(profile_1d - self.background_ascan, 0.0)
            self.background_ascan = (1.0 - self.alpha) * self.background_ascan + self.alpha * profile_1d
            
            pmax = np.max(dynamic)
            clean_1d = np.power(dynamic / pmax, 1.3) if pmax > 1e-4 else np.zeros(self.output_bins, dtype=np.float32)

        self.smoothed_ascan = 0.65 * self.smoothed_ascan + 0.35 * clean_1d

        # 2D Heatmap Reconstitution
        if mode == "stereo":
            env_r = self._extract_envelope(right_raw)
            # Instantaneous Coherent Dual-Beamforming
            image_2d = (env_l[self.stereo_idx_left] + env_r[self.stereo_idx_right]) * self.stereo_tgc
        else:
            # Mono SAS Mode
            self.envelope_buffer.append(env_l)
            image_2d = np.zeros((self.grid_h, self.grid_w), dtype=np.float32)
            n_buf = len(self.envelope_buffer)
            for k in range(n_buf):
                image_2d += self.envelope_buffer[k][self.sas_index_table[k]] * self.sas_tgc_table[k]

        max_val = np.max(image_2d)
        if max_val > 1e-4:
            # Normalize and suppress sidelobes
            norm = np.maximum((image_2d / max_val) - 0.28, 0.0) / 0.72
            image_2d = np.power(norm, 2.2)
        else:
            image_2d.fill(0)

        return self.smoothed_ascan.astype(np.float32), image_2d.astype(np.float32)