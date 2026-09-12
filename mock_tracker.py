import os
import time
import numpy as np
from tracker import load_config, run_tracker
import sys
import threading

class MockRtlSdr:
    def __init__(self):
        self.sample_rate = 2.048e6
        self.center_freq = 100e6
        self.gain = 'auto'
        self.closed = False
        print("MockRtlSdr initialized")

    def read_samples(self, num_samples):
        # Generate some noise
        samples = np.random.normal(scale=0.1, size=num_samples) + 1j * np.random.normal(scale=0.1, size=num_samples)
        # Occasionally inject a strong signal if tuned to Bear_2 (150.5 MHz)
        if self.center_freq == 150500000:
            t = np.arange(num_samples) / self.sample_rate
            # Simulated CW pulse
            pulse = np.exp(2j * np.pi * 10000 * t)
            samples += pulse

        # Simulate some delay to represent actual sample reading time
        time.sleep(0.01)
        return samples

    def close(self):
        self.closed = True
        print("MockRtlSdr closed")

def run_test():
    config = load_config()
    print("Running tracker with Mock SDR...")

    # We will run the tracker in a thread so we can stop it after a few seconds
    # since it runs an infinite loop normally.

    def tracker_thread():
        # Temporarily mock sys.exit or let it raise if it tries
        run_tracker(config, sdr_class=MockRtlSdr)

    t = threading.Thread(target=tracker_thread)
    t.daemon = True
    t.start()

    # Let it run for enough time to scan both animals at least once
    # SCAN_TIME_SECONDS in .env is 2, and we have 2 animals. So 5 seconds should be enough.
    time.sleep(5)

    print("\nStopping tracker thread.")

if __name__ == '__main__':
    run_test()
