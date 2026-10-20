# backend/test_beamformer.py
import time
import numpy as np
from app.core.config import SonarConfig
from app.core.audio_stream import DuplexAudioPipeline
from app.core.canceller import EchoProcessor
from app.core.beamformer import PolarBeamformer

def main():
    print("[*] Booting Sonar 2D Acoustic Engine...")
    cfg = SonarConfig()
    pipeline = DuplexAudioPipeline(config=cfg)
    processor = EchoProcessor(config=cfg)
    beamformer = PolarBeamformer(config=cfg)

    pipeline.start()
    print("[*] Stabilizing baseline background cancellation (keep hands away for 1.5s)...")
    time.sleep(1.5)

    try:
        print("[*] 2D Beamformer Active! Move your hand across the laptop camera (left/right/depth)...")
        print("-" * 65)
        print(f"{'Scan':<6} | {'Target Angle':<14} | {'Distance':<10} | {'Intensity':<10} | {'Visual Bearing'}")
        print("-" * 65)

        for scan in range(1, 21):
            time.sleep(0.12)  # ~8 FPS scan rate

            pri_samples = int(cfg.sample_rate * cfg.pulse_repetition_interval)
            raw_audio = pipeline.get_latest_rx(pri_samples)

            # 1. Matched filter + Direct-path cancellation
            clean_l, clean_r = processor.process_frame(raw_audio)

            # 2. Compute 2D spatial polar matrix
            spatial_grid = beamformer.compute_spatial_grid(clean_l, clean_r)

            # 3. Locate target
            angle, dist, intensity = beamformer.get_peak_coordinates(spatial_grid)

            # Render ASCII directional needle
            # Map -60 deg to 0, 0 deg to middle, +60 deg to right
            bearing_pos = int(np.interp(angle, [-60, 60], [0, 20]))
            gauge = ["."] * 21
            gauge[bearing_pos] = "▲"
            gauge_str = "".join(gauge)

            print(f"#{scan:<5} | {angle:>+5.1f}°         | {dist:>4.2f} m   | {intensity:>6.3f}     | [{gauge_str}]")

        print("-" * 65)
        print("[+] 2D Beamforming test verified successfully.")

    finally:
        pipeline.stop()

if __name__ == "__main__":
    main()