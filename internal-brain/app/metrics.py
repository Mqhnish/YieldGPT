"""Per-query wall-clock measurements; isolated across concurrent requests."""
from contextvars import ContextVar
from functools import wraps
import time

CURRENT = ContextVar('query_measurement', default=None)


class Measurement:
    def __init__(self):
        self.phases = {}
    def __enter__(self):
        self.started = time.perf_counter()
        self.token = CURRENT.set(self)
        return self
    def __exit__(self, *args):
        self.phases['total_ms'] = (time.perf_counter() - self.started) * 1000
        CURRENT.reset(self.token)
    def snapshot(self):
        return {k: round(v, 3) for k,v in self.phases.items()}


def timed(name):
    def decorate(fn):
        @wraps(fn)
        def run(*args, **kwargs):
            measurement = CURRENT.get()
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                if measurement is not None:
                    measurement.phases[name] = measurement.phases.get(name, 0) + (time.perf_counter()-start)*1000
        return run
    return decorate
