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

        # Simulate some delay to represent actual sample reading time (~0.125s for 256k samples at 2.048Msps)
        read_time = num_samples / self.sample_rate
        time.sleep(read_time)

        current_time = time.time()

        # Inject a strong signal if tuned to Bear_2 (150.5 MHz) at a simulated 40 BPM (1 pulse every 1.5 seconds)
        if self.center_freq == 150500000:
            # We are pulsing for 100ms every 1.5s
            if (current_time % 1.5) < 0.1:
                t = np.arange(num_samples) / self.sample_rate
                # Simulated CW pulse
                pulse = 10 * np.exp(2j * np.pi * 10000 * t) # Make it strong so it stands out
                samples += pulse

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
    # SCAN_TIME_SECONDS will be 10, and we have 2 animals. So 25 seconds should be enough.
    time.sleep(25)

    print("\nStopping tracker thread.")

if __name__ == '__main__':
    run_test()
