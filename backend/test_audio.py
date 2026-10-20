# backend/test_audio.py
import time
import numpy as np
from app.core.config import SonarConfig
from app.core.audio_stream import DuplexAudioPipeline

def run_test():
    print("[*] Initializing Sonar Audio Pipeline...")
    cfg = SonarConfig()
    pipeline = DuplexAudioPipeline(config=cfg)

    print(f"[*] Starting duplex stream at {cfg.sample_rate} Hz (Stereo I/O)...")
    pipeline.start()

    try:
        # Run test for 3 seconds
        for second in range(1, 4):
            time.sleep(1.0)
            
            # Read latest 4096 samples from both microphone channels
            samples = pipeline.get_latest_rx(4096)
            rms_left = np.sqrt(np.mean(samples[:, 0] ** 2))
            rms_right = np.sqrt(np.mean(samples[:, 1] ** 2))

            print(
                f"[t={second}s] Captured: {len(samples)} frames | "
                f"RMS L: {rms_left:.4f} | RMS R: {rms_right:.4f} | "
                f"Buffer Size: {pipeline.rx_buffer.size} samples"
            )

        print("[+] Test completed without hardware crashes.")
        print(f"[*] Overflow count: {pipeline.overflow_count}, Underflows: {pipeline.underflow_count}")

    finally:
        print("[*] Stopping audio stream...")
        pipeline.stop()

if __name__ == "__main__":
    run_test()