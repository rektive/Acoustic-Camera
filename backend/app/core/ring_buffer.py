# backend/app/core/ring_buffer.py
import threading
import numpy as np

class RingBuffer:
    def __init__(self, capacity: int, channels: int = 1, dtype=np.float32):
        self.capacity = capacity
        self.channels = channels
        self.dtype = dtype
        self.buffer = np.zeros((capacity, channels), dtype=dtype)
        self.write_idx = 0
        self.read_idx = 0
        self.size = 0
        self.lock = threading.Lock()

    def write(self, data: np.ndarray) -> int:
        frames = len(data)
        if frames == 0:
            return 0
        
        # Ensure 2D shape (samples, channels)
        if data.ndim == 1:
            data = data[:, np.newaxis]

        with self.lock:
            if frames > self.capacity:
                data = data[-self.capacity:]
                frames = self.capacity

            end_idx = self.write_idx + frames
            if end_idx <= self.capacity:
                self.buffer[self.write_idx:end_idx] = data
            else:
                first = self.capacity - self.write_idx
                second = frames - first
                self.buffer[self.write_idx:] = data[:first]
                self.buffer[:second] = data[first:]

            self.write_idx = end_idx % self.capacity
            self.size = min(self.size + frames, self.capacity)
            return frames

    def read_latest(self, num_frames: int) -> np.ndarray:
        with self.lock:
            if self.size == 0 or num_frames <= 0:
                return np.zeros((num_frames, self.channels), dtype=self.dtype)

            n = min(num_frames, self.size)
            start_idx = (self.write_idx - n) % self.capacity

            if start_idx + n <= self.capacity:
                out = self.buffer[start_idx:start_idx + n].copy()
            else:
                first = self.capacity - start_idx
                second = n - first
                out = np.vstack((self.buffer[start_idx:], self.buffer[:second]))

            if n < num_frames:
                pad = np.zeros((num_frames - n, self.channels), dtype=self.dtype)
                out = np.vstack((pad, out))

            return out

    def clear(self):
        with self.lock:
            self.write_idx = 0
            self.read_idx = 0
            self.size = 0
            self.buffer.fill(0)