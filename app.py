import os
import glob
import csv
import json
import psutil
import subprocess
import sys
import time
import struct
import numpy as np
import io
import wave
from scipy import signal
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, Response, send_file
from dotenv import load_dotenv, set_key

# Import tracker logic for the stream
from tracker import load_config, measure_signal_strength

app = Flask(__name__)

def is_tracker_running():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and 'python' in proc.info['name'].lower():
                # Check if tracker.py is in the arguments
                if any('tracker.py' in arg for arg in cmdline):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def start_tracker():
    if not is_tracker_running():
        # Run it in the background, redirecting output
        subprocess.Popen([sys.executable, 'tracker.py'],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         start_new_session=True)

def stop_tracker():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and 'python' in proc.info['name'].lower():
                if any('tracker.py' in arg for arg in cmdline):
                    proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

def get_all_detections():
    """Reads all tracking_log_*.csv files and returns a list of dictionaries."""
    detections = []
    # Find all csv files starting with tracking_log_
    csv_files = glob.glob('tracking_log_*.csv')

    for file in csv_files:
        try:
            with open(file, mode='r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    detections.append(row)
        except Exception as e:
            print(f"Error reading {file}: {e}")

    # Sort by Date/Time descending
    detections.sort(key=lambda x: x.get('Date/Time', ''), reverse=True)
    return detections

def get_latest_detections(detections):
    """Returns a dictionary with the latest detection for each animal."""
    latest = {}
    for det in detections:
        animal = det.get('Animal Name')
        if animal and animal not in latest:
            # Determine movement status based on BPM
            try:
                bpm = float(det.get('BPM', 0))
            except ValueError:
                bpm = 0.0

            status = 'Unknown'
            if bpm > 0:
                if bpm >= 70:
                    status = 'Stationary'
                elif bpm > 20:
                    status = 'Active'

            det['Status'] = status
            latest[animal] = det
    return latest

@app.route('/')
def index():
    tracker_running = is_tracker_running()
    all_detections = get_all_detections()
    latest_detections = get_latest_detections(all_detections)

    return render_template('index.html',
                           tracker_running=tracker_running,
                           latest=latest_detections)

@app.route('/animal/<name>')
def animal(name):
    all_detections = get_all_detections()
    animal_history = [d for d in all_detections if d.get('Animal Name') == name]

    return render_template('animal.html',
                           name=name,
                           history=animal_history)

@app.route('/start', methods=['POST'])
def start():
    start_tracker()
    return redirect(url_for('index'))

@app.route('/stop', methods=['POST'])
def stop():
    stop_tracker()
    return redirect(url_for('index'))

@app.route('/stream')
def stream_page():
    config = load_config()
    animals = list(config['animals'].keys())
    return render_template('stream.html', animals=animals)

@app.route('/listen')
def listen_page():
    config = load_config()
    animals = list(config['animals'].keys())
    return render_template('listen.html', animals=animals)

# Global SDR state for audio chunks to avoid slow initialization on every chunk fetch
audio_sdr_instance = None
audio_was_running = False

@app.route('/audio_start')
def audio_start():
    """Initializes the SDR for listening."""
    global audio_sdr_instance, audio_was_running
    target = request.args.get('target')

    if audio_sdr_instance:
        return {"status": "already running"}

    config = load_config()
    if not target or target not in config['animals']:
        return {"error": "Invalid target"}, 400

    audio_was_running = is_tracker_running()
    if audio_was_running:
        stop_tracker()
        time.sleep(0.5)

    try:
        from rtlsdr import RtlSdr
        sdr_class = RtlSdr
    except ImportError:
        try:
            from mock_tracker import MockRtlSdr
            sdr_class = MockRtlSdr
        except ImportError:
            return {"error": "No SDR library"}, 500

    try:
        sdr = sdr_class()
        sdr.sample_rate = 2.048e6
        sdr.gain = config['sdr_gain']
        sdr.center_freq = config['animals'][target]
        time.sleep(0.1) # settle
        audio_sdr_instance = sdr
        return {"status": "started"}
    except Exception as e:
        if audio_was_running:
            start_tracker()
        return {"error": str(e)}, 500

@app.route('/audio_stop')
def audio_stop():
    """Stops the SDR and resumes tracking."""
    global audio_sdr_instance, audio_was_running
    if audio_sdr_instance:
        audio_sdr_instance.close()
        audio_sdr_instance = None
        if audio_was_running:
            start_tracker()
    return {"status": "stopped"}

@app.route('/audio_chunk')
def audio_chunk():
    """Returns a short WAV chunk of demodulated CW audio."""
    global audio_sdr_instance
    if not audio_sdr_instance:
        return {"error": "SDR not initialized"}, 400

    sdr_sample_rate = 2.048e6
    audio_sample_rate = 32000
    decimation_factor = int(sdr_sample_rate / audio_sample_rate) # 64

    # Read ~0.5 seconds of data (must be power of 2 for easy read_samples)
    num_samples = 1048576

    try:
        samples = audio_sdr_instance.read_samples(num_samples)
    except Exception as e:
        return {"error": str(e)}, 500

    # CW Demodulation: mix with a 1kHz BFO
    t = np.arange(len(samples)) / sdr_sample_rate
    bfo_tone = np.exp(2j * np.pi * 1000 * t)
    mixed = samples * bfo_tone

    # Take real part (or magnitude) and decimate
    # Using simple array slicing for speed to avoid IIR filter clicking
    baseband = np.real(mixed)[::decimation_factor]

    # Fixed scaling to prevent AGC noise pumping.
    # The max value from the SDR is usually ~1.0. We scale it up, but clamp.
    scaled = np.clip(baseband * 30000, -32768, 32767)
    audio_pcm = np.int16(scaled)

    # Create WAV in memory
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(audio_sample_rate)
        wf.writeframes(audio_pcm.tobytes())

    buf.seek(0)
    return send_file(buf, mimetype='audio/wav')


@app.route('/stream_feed')
def stream_feed():
    target = request.args.get('target', 'cycle')

    def generate():
        # Stop background tracker if running so it frees the SDR
        was_running = is_tracker_running()
        if was_running:
            stop_tracker()
            time.sleep(1) # wait for sdr to be freed

        config = load_config()

        # Determine sdr class
        try:
            from rtlsdr import RtlSdr
            sdr_class = RtlSdr
        except ImportError:
            # Fallback to mock for testing
            try:
                from mock_tracker import MockRtlSdr
                sdr_class = MockRtlSdr
            except ImportError:
                yield f"data: {json.dumps({'error': 'No SDR library or mock found'})}\n\n"
                return

        try:
            sdr = sdr_class()
            sdr.sample_rate = 2.048e6
            sdr.gain = config['sdr_gain']

            animals_to_scan = config['animals']
            if target != 'cycle' and target in animals_to_scan:
                animals_to_scan = {target: animals_to_scan[target]}

            if not animals_to_scan:
                yield f"data: {json.dumps({'error': 'No animals configured'})}\n\n"
                return

            # Keep yielding data
            while True:
                for animal, freq in animals_to_scan.items():
                    sdr.center_freq = freq
                    time.sleep(0.1) # settle time

                    samples = sdr.read_samples(256 * 1024)
                    power = measure_signal_strength(samples)

                    data = {
                        'time': datetime.now().strftime('%H:%M:%S'),
                        'animal': animal,
                        'freq': freq,
                        'power': float(power)
                    }

                    yield f"data: {json.dumps(data)}\n\n"
                    time.sleep(0.1) # prevent flooding

        except GeneratorExit:
            # Client disconnected
            pass
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if 'sdr' in locals():
                sdr.close()
            # Restart background tracker if it was running before
            if was_running:
                start_tracker()

    return Response(generate(), mimetype='text/event-stream')

@app.route('/config', methods=['GET', 'POST'])
def config():
    env_path = '.env'
    if not os.path.exists(env_path):
        # Create from example if it doesn't exist
        if os.path.exists('.env.example'):
            with open('.env.example', 'r') as ex, open(env_path, 'w') as env:
                env.write(ex.read())
        else:
            with open(env_path, 'w') as env:
                env.write("")

    load_dotenv(dotenv_path=env_path, override=True)

    if request.method == 'POST':
        # Update values
        set_key(env_path, 'SDR_GAIN', request.form.get('sdr_gain', 'auto'))
        set_key(env_path, 'SCAN_TIME_SECONDS', request.form.get('scan_time', '10'))
        set_key(env_path, 'SIGNAL_THRESHOLD_DB', request.form.get('signal_threshold_db', '0.0'))
        set_key(env_path, 'GPS_LATITUDE', request.form.get('latitude', '0.0'))
        set_key(env_path, 'GPS_LONGITUDE', request.form.get('longitude', '0.0'))

        # Parse animals from form text area
        animals_text = request.form.get('animals', '{}')
        try:
            # Validate JSON
            json.loads(animals_text)
            set_key(env_path, 'ANIMALS_FREQUENCIES', animals_text)
        except json.JSONDecodeError:
            pass # Or handle error visually

        # Restart if requested
        if request.form.get('restart_tracker') == 'true':
            stop_tracker()
            start_tracker()

        return redirect(url_for('config'))

    # GET request: load current config
    current_config = {
        'sdr_gain': os.getenv('SDR_GAIN', 'auto'),
        'scan_time': os.getenv('SCAN_TIME_SECONDS', '10'),
        'signal_threshold_db': os.getenv('SIGNAL_THRESHOLD_DB', '0.0'),
        'lat': os.getenv('GPS_LATITUDE', '0.0'),
        'lon': os.getenv('GPS_LONGITUDE', '0.0'),
        'animals': os.getenv('ANIMALS_FREQUENCIES', '{}')
    }

    # Prettify json for the textarea
    try:
        parsed_animals = json.loads(current_config['animals'])
        current_config['animals_pretty'] = json.dumps(parsed_animals, indent=2)
    except json.JSONDecodeError:
        current_config['animals_pretty'] = current_config['animals']

    return render_template('config.html', config=current_config)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
