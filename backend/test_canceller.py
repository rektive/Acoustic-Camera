# backend/test_canceller.py
import time
import numpy as np
from app.core.config import SonarConfig
from app.core.audio_stream import DuplexAudioPipeline
from app.core.canceller import EchoProcessor

def main():
    cfg = SonarConfig()
    pipeline = DuplexAudioPipeline(config=cfg)
    processor = EchoProcessor(config=cfg)

    print("[*] Starting Audio Hardware Pipeline...")
    pipeline.start()

    # Allow buffer to fill and background baseline to settle
    print("[*] Calibrating direct-path cancellation (keep hands still for 1.5s)...")
    time.sleep(1.5)

    try:
        print("[*] Now tracking dynamic echoes. Move your hand in front of the screen...")
        for iteration in range(15):
            time.sleep(0.15)
            
            # Read latest chunk (matching the pulse repetition window)
            pri_samples = int(cfg.sample_rate * cfg.pulse_repetition_interval)
            raw_audio = pipeline.get_latest_rx(pri_samples)

            clean_l, clean_r = processor.process_frame(raw_audio)

            # Find peak dynamic echo locations
            combined_energy = (clean_l + clean_r) / 2.0
            peak_idx = int(np.argmax(combined_energy))
            peak_intensity = combined_energy[peak_idx]
            detected_dist_m = processor.sample_index_to_meters(peak_idx)

            # Visual bar indicator
            bar_len = int(np.clip(peak_intensity * 20, 0, 30))
            meter = "█" * bar_len

            print(
                f"[Scan {iteration+1:02d}] Target Distance: {detected_dist_m:.2f} m | "
                f"Peak Intensity: {peak_intensity:.4f} | {meter}"
            )

    finally:
        print("[*] Shutting down audio stream...")
        pipeline.stop()

if __name__ == "__main__":
    main()