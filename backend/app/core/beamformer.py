# backend/app/core/beamformer.py
import numpy as np
from .config import SonarConfig

class PolarBeamformer:
    def __init__(self, config: SonarConfig = SonarConfig()):
        self.cfg = config
        self.c = 343.0  # Speed of sound in air (m/s)
        
        # Physical distance between laptop stereo microphones (~15 cm default)
        self.mic_distance = 0.15
        
        # Angular grid: 61 discrete angles spanning -60 deg (left) to +60 deg (right)
        self.angles_deg = np.linspace(-60.0, 60.0, 61, dtype=np.float32)
        self.angles_rad = np.radians(self.angles_deg)
        
        # Range grid: 100 distance bins from 0.1m up to 2.5m
        self.min_range_m = 0.1
        self.max_range_m = 2.5
        self.num_range_bins = 100
        self.ranges_m = np.linspace(self.min_range_m, self.max_range_m, self.num_range_bins, dtype=np.float32)
        
        # Precompute sample delays for each angle to avoid recalculating in hot loops
        # tau = (d * sin(theta)) / c
        # delta_samples = tau * fs
        self.delay_samples = (self.mic_distance * np.sin(self.angles_rad) * self.cfg.sample_rate / self.c)
        
        # Precompute sample indices corresponding to each range bin
        # n = (2 * r / c) * fs
        self.range_sample_indices = np.round((2.0 * self.ranges_m / self.c) * self.cfg.sample_rate).astype(np.int32)
        
        # Precompute Time-Gain Compensation (TGC) curve
        # Sound pressure falls off proportionally with distance squared
        self.tgc_curve = np.linspace(1.0, 3.5, self.num_range_bins, dtype=np.float32)

    def compute_spatial_grid(self, echo_left: np.ndarray, echo_right: np.ndarray) -> np.ndarray:
        """
        Takes the 1D filtered echo envelopes from both channels and constructs
        a normalized 2D spatial energy matrix of shape (num_angles, num_range_bins).
        """
        grid = np.zeros((len(self.angles_deg), self.num_range_bins), dtype=np.float32)
        max_len = min(len(echo_left), len(echo_right))

        for a_idx, delta_s in enumerate(self.delay_samples):
            # Compute channel offsets for this specific steering direction
            half_delay = delta_s / 2.0
            
            for r_idx, center_sample in enumerate(self.range_sample_indices):
                # Calculate sample index for left and right channels
                s_left = int(center_sample + half_delay)
                s_right = int(center_sample - half_delay)
                
                # Check array boundaries
                if 0 <= s_left < max_len and 0 <= s_right < max_len:
                    # Delay and Sum: coherent addition increases SNR
                    combined = echo_left[s_left] + echo_right[s_right]
                    # Power of beamformed signal
                    energy = combined ** 2
                    # Apply Time-Gain Compensation to boost distant reflections
                    grid[a_idx, r_idx] = energy * self.tgc_curve[r_idx]

        # Normalize grid to [0.0, 1.0] for streaming to frontend Canvas
        max_val = np.max(grid)
        if max_val > 1e-6:
            grid = grid / max_val
            
        # Contrast adjustment (suppress noise floor, sharpen reflection centroid)
        grid = np.power(grid, 1.5)
        return grid

    def get_peak_coordinates(self, grid: np.ndarray) -> tuple[float, float, float]:
        """
        Locates the coordinates of the highest energy reflection in the grid.
        Returns: (azimuth_deg, distance_m, intensity)
        """
        peak_idx = np.unravel_index(np.argmax(grid), grid.shape)
        angle_deg = float(self.angles_deg[peak_idx[0]])
        dist_m = float(self.ranges_m[peak_idx[1]])
        intensity = float(grid[peak_idx])
        return angle_deg, dist_m, intensity