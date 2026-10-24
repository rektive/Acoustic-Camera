"""
Thread-safe Circular Audio Buffer
Author: Nikita Zhuravlov
"""
import threading
import numpy as np

class CircularAudioBuffer:
    def __init__(self, capacity: int, channels: int = 1):
        self.capacity = capacity
        self.channels = channels
        self.buffer = np.zeros((capacity, channels), dtype=np.float32)
        self.write_index = 0
        self.lock = threading.Lock()

    def write(self, data: np.ndarray):
        with self.lock:
            # Handle 1D array by reshaping to (N, 1)
            if data.ndim == 1:
                data = data[:, np.newaxis]
            
            # If incoming channels differ from buffer allocation, slice or broadcast
            if data.shape[1] != self.channels:
                if data.shape[1] > self.channels:
                    data = data[:, :self.channels]
                else:
                    data = np.repeat(data, self.channels, axis=1)

            n_samples = data.shape[0]
            if n_samples >= self.capacity:
                self.buffer[:] = data[-self.capacity:]
                self.write_index = 0
                return

            end_index = self.write_index + n_samples
            if end_index <= self.capacity:
                self.buffer[self.write_index:end_index] = data
                self.write_index = end_index % self.capacity
            else:
                first_part = self.capacity - self.write_index
                self.buffer[self.write_index:] = data[:first_part]
                second_part = n_samples - first_part
                self.buffer[:second_part] = data[first_part:]
                self.write_index = second_part

    def read_latest(self, num_samples: int) -> np.ndarray:
        with self.lock:
            num_samples = min(num_samples, self.capacity)
            start_index = self.write_index - num_samples
            if start_index >= 0:
                result = self.buffer[start_index:self.write_index].copy()
            else:
                result = np.vstack((
                    self.buffer[start_index % self.capacity:],
                    self.buffer[:self.write_index]
                ))
            
            # Flatten to 1D if single-channel mono
            if self.channels == 1:
                return result.flatten()
            return result