"""
Acoustic Duplex Audio Stream Engine
Author: Nikita Zhuravlov
"""
import sounddevice as sd
import numpy as np
from .config import SonarConfig
from .ring_buffer import CircularAudioBuffer

class DuplexAudioPipeline:
    def __init__(self, config: SonarConfig):
        self.cfg = config
        self.rx_buffer = CircularAudioBuffer(
            capacity=self.cfg.ring_buffer_size,
            channels=self.cfg.in_channels
        )
        self.tx_signal = self._generate_tx_frame()
        self.tx_cursor = 0
        self.stream = None

    def _generate_tx_frame(self) -> np.ndarray:
        fs = self.cfg.sample_rate
        pri_len = int(fs * self.cfg.pulse_repetition_interval)
        chirp_len = int(fs * self.cfg.chirp_duration)
        
        t = np.linspace(0, self.cfg.chirp_duration, chirp_len, endpoint=False)
        slope = (self.cfg.chirp_f1 - self.cfg.chirp_f0) / self.cfg.chirp_duration
        phase = 2.0 * np.pi * (self.cfg.chirp_f0 * t + 0.5 * slope * (t ** 2))
        chirp = (np.sin(phase) * 0.75).astype(np.float32)
        
        # Tukey edge taper
        edge = int(chirp_len * 0.08)
        chirp[:edge] *= 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, edge)))
        chirp[-edge:] *= 0.5 * (1.0 - np.cos(np.linspace(np.pi, 0, edge)))
        
        frame = np.zeros((pri_len, self.cfg.out_channels), dtype=np.float32)
        for ch in range(self.cfg.out_channels):
            frame[:chirp_len, ch] = chirp
        return frame

    def _callback(self, indata, outdata, frames, time_info, status):
        self.rx_buffer.write(indata)
        
        end_cursor = self.tx_cursor + frames
        tx_len = len(self.tx_signal)
        if end_cursor <= tx_len:
            outdata[:] = self.tx_signal[self.tx_cursor:end_cursor]
            self.tx_cursor = end_cursor % tx_len
        else:
            first_part = tx_len - self.tx_cursor
            outdata[:first_part] = self.tx_signal[self.tx_cursor:]
            second_part = frames - first_part
            outdata[first_part:] = self.tx_signal[:second_part]
            self.tx_cursor = second_part

    def start(self):
        self.stop()
        self.stream = sd.Stream(
            samplerate=self.cfg.sample_rate,
            blocksize=self.cfg.buffer_frames,
            device=(self.cfg.input_device_index, self.cfg.output_device_index),
            channels=(self.cfg.in_channels, self.cfg.out_channels),
            dtype='float32',
            callback=self._callback
        )
        self.stream.start()

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def get_latest_rx(self, num_samples: int) -> np.ndarray:
        return self.rx_buffer.read_latest(num_samples)