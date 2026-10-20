# backend/app/core/canceller.py
import numpy as np
from scipy import signal
from .config import SonarConfig

class EchoProcessor:
    def __init__(self, config: SonarConfig = SonarConfig()):
        self.cfg = config
        self.reference_chirp = self._generate_reference_chirp()
        
        # Speed of sound in air at ~20°C (m/s)
        self.c = 343.0
        
        # Max detection range in meters (e.g., 2.5 meters in front of the laptop)
        self.max_range_m = 2.5
        self.max_sample_delay = int((2.0 * self.max_range_m / self.c) * self.cfg.sample_rate)
        
        # Background model for Direct-Path Cancellation (one baseline per mic channel)
        self.background_profile = None
        
        # Learning rate for static background adaptation (0.05 = slow adaptive tracking)
        self.alpha = 0.05

    def _generate_reference_chirp(self) -> np.ndarray:
        """Generates the analytical reference chirp used for matched filtering."""
        fs = self.cfg.sample_rate
        n_samples = int(fs * self.cfg.chirp_duration)
        t = np.linspace(0, self.cfg.chirp_duration, n_samples, endpoint=False)
        
        freq_slope = (self.cfg.chirp_f1 - self.cfg.chirp_f0) / self.cfg.chirp_duration
        phase = 2.0 * np.pi * (self.cfg.chirp_f0 * t + 0.5 * freq_slope * (t ** 2))
        chirp = np.sin(phase).astype(np.float32)
        
        # Window the reference identically to the transmitted signal
        window = np.ones(n_samples, dtype=np.float32)
        edge = int(n_samples * 0.1)
        window[:edge] = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, edge)))
        window[-edge:] = 0.5 * (1.0 - np.cos(np.linspace(np.pi, 0, edge)))
        
        return chirp * window

    def matched_filter(self, channel_data: np.ndarray) -> np.ndarray:
        """
        Cross-correlates incoming audio against the reference chirp via FFT.
        Compresses the 40ms sweep into sub-millisecond arrival impulses.
        """
        # FFT-based correlation for low latency
        correlated = signal.correlate(channel_data, self.reference_chirp, mode='full', method='fft')
        
        # Extract the positive-time correlation envelope (analytic signal magnitude)
        analytic = signal.hilbert(correlated)
        envelope = np.abs(analytic).astype(np.float32)
        
        # Align zero-delay offset
        chirp_len = len(self.reference_chirp)
        valid_envelope = envelope[chirp_len - 1:]
        
        # Slice to the maximum physical distance we care about
        return valid_envelope[:self.max_sample_delay]

    def process_frame(self, stereo_block: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Runs matched filter on both mic channels, then subtracts the direct speaker path.
        Returns:
            clean_left: 1D array of echo energy vs distance
            clean_right: 1D array of echo energy vs distance
        """
        corr_l = self.matched_filter(stereo_block[:, 0])
        corr_r = self.matched_filter(stereo_block[:, 1])

        current_profile = np.vstack((corr_l, corr_r))

        # First frame: initialize background profile
        if self.background_profile is None:
            self.background_profile = current_profile.copy()
            return np.zeros_like(corr_l), np.zeros_like(corr_r)

        # Direct-Path Subtraction: subtract static leakage
        dynamic_energy = current_profile - self.background_profile
        # Rectify negative values (energy cannot be negative)
        dynamic_energy = np.maximum(dynamic_energy, 0.0)

        # Slowly update background model to adjust for room temperature and drift
        self.background_profile = (1.0 - self.alpha) * self.background_profile + self.alpha * current_profile

        return dynamic_energy[0], dynamic_energy[1]

    def sample_index_to_meters(self, index: int) -> float:
        """Converts sample delay index into physical round-trip distance in meters."""
        time_sec = index / self.cfg.sample_rate
        distance = (time_sec * self.c) / 2.0
        return distance