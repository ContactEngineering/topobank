import time
from contextlib import contextmanager

class Timer:
    """
    A simple timer class that can be used as a context manager and 
    records durations of named blocks.
    """
    def __init__(self, name=None):
        self.name = name
        self.durations = {}

    @contextmanager
    def __call__(self, block_name):
        start_time = time.perf_counter()
        try:
            yield
        finally:
            end_time = time.perf_counter()
            self.durations[block_name] = end_time - start_time

    def to_dict(self):
        return {
            "name": self.name,
            "durations": self.durations
        }
