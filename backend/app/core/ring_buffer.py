# backend/app/core/ring_buffer.py
import threading
import numpy as np

class RingBuffer:
    def __init__(self, capacity: int, channels: int = 2, dtype=np.float32):
        self.capacity = capacity
        self.channels = channels
        self.dtype = dtype
        
        # Pre-allocate buffer in memory so GC doesn't kick in during audio loops
        self.buffer = np.zeros((capacity, channels), dtype=dtype)
        
        self.write_idx = 0
        self.read_idx = 0
        self.size = 0
        self.lock = threading.Lock()

    def write(self, data: np.ndarray) -> int:
        """Writes samples into circular storage. Drops oldest data if full."""
        frames = len(data)
        if frames == 0:
            return 0
        
        with self.lock:
            # If incoming data exceeds capacity, just keep the latest slice
            if frames > self.capacity:
                data = data[-self.capacity:]
                frames = self.capacity

            # Calculate slice boundaries for wrap-around
            end_idx = self.write_idx + frames
            if end_idx <= self.capacity:
                self.buffer[self.write_idx:end_idx] = data
            else:
                first_part = self.capacity - self.write_idx
                second_part = frames - first_part
                self.buffer[self.write_idx:] = data[:first_part]
                self.buffer[:second_part] = data[first_part:]

            self.write_idx = end_idx % self.capacity
            self.size = min(self.size + frames, self.capacity)
            return frames

    def read_latest(self, num_frames: int) -> np.ndarray:
        """Reads the most recent N frames without advancing read pointer."""
        with self.lock:
            if self.size == 0 or num_frames <= 0:
                return np.zeros((num_frames, self.channels), dtype=self.dtype)

            # Cap request to currently available samples
            n = min(num_frames, self.size)
            start_idx = (self.write_idx - n) % self.capacity

            if start_idx + n <= self.capacity:
                out = self.buffer[start_idx:start_idx + n].copy()
            else:
                first_part = self.capacity - start_idx
                second_part = n - first_part
                out = np.vstack((self.buffer[start_idx:], self.buffer[:second_part]))

            # Zero-pad if user requested more frames than currently buffered
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