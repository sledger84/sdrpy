import os
import time
import json
import csv
from datetime import datetime
import numpy as np
from dotenv import load_dotenv

# We will import pyrtlsdr later or handle it in the main block
# from rtlsdr import RtlSdr

def load_config():
    load_dotenv()

    # SDR Settings
    sdr_gain = os.getenv('SDR_GAIN', 'auto')
    try:
        sdr_gain = float(sdr_gain)
    except ValueError:
        sdr_gain = 'auto'

    scan_time = float(os.getenv('SCAN_TIME_SECONDS', '5'))

    # GPS Location
    lat = os.getenv('GPS_LATITUDE', '0.0')
    lon = os.getenv('GPS_LONGITUDE', '0.0')

    # Animals Frequencies
    animals_freqs_str = os.getenv('ANIMALS_FREQUENCIES', '{}')
    animals_frequencies = json.loads(animals_freqs_str)

    return {
        'sdr_gain': sdr_gain,
        'scan_time': scan_time,
        'lat': lat,
        'lon': lon,
        'animals': animals_frequencies
    }

def measure_signal_strength(samples):
    """
    Computes the maximum signal strength from the samples using FFT.
    """
    # Compute FFT
    fft_data = np.fft.fft(samples)
    fft_shifted = np.fft.fftshift(fft_data)

    # Compute power in dB
    power = 10 * np.log10(np.abs(fft_shifted)**2 + 1e-9)

    return np.max(power)

def run_tracker(config, sdr_class=None):
    if not config['animals']:
        print("No animals configured to track. Exiting.")
        return

    # Attempt to import RtlSdr if not provided (allows for mocking)
    if sdr_class is None:
        try:
            from rtlsdr import RtlSdr
            sdr_class = RtlSdr
        except ImportError:
            print("Error: pyrtlsdr is not installed or RtlSdr could not be imported.")
            return

    sdr = sdr_class()
    sdr.sample_rate = 2.048e6
    sdr.gain = config['sdr_gain']

    csv_filename = f"tracking_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    # Setup CSV logging
    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Date/Time', 'Animal Name', 'Frequency (Hz)', 'Signal Strength (dB)', 'Latitude', 'Longitude'])

        print(f"Starting tracking loop. Logging to {csv_filename}...")

        try:
            while True:
                for animal, freq in config['animals'].items():
                    print(f"Tuning to {freq} Hz for {animal}...")
                    sdr.center_freq = freq

                    # Give the SDR a moment to settle after tuning
                    time.sleep(0.1)

                    start_time = time.time()
                    max_power = -float('inf')

                    # Scan for the specified duration
                    while time.time() - start_time < config['scan_time']:
                        # Read samples (e.g., 256 * 1024)
                        samples = sdr.read_samples(256 * 1024)
                        power = measure_signal_strength(samples)
                        if power > max_power:
                            max_power = power

                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{timestamp}] {animal} ({freq} Hz): {max_power:.2f} dB")

                    writer.writerow([timestamp, animal, freq, f"{max_power:.2f}", config['lat'], config['lon']])
                    file.flush()

        except KeyboardInterrupt:
            print("Tracking stopped by user.")
        finally:
            sdr.close()

if __name__ == '__main__':
    config = load_config()
    print("Configuration loaded:")
    print(config)
    run_tracker(config)
