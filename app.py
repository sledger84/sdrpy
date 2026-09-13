import os
import glob
import csv
import json
import psutil
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv, set_key

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

        return redirect(url_for('config'))

    # GET request: load current config
    current_config = {
        'sdr_gain': os.getenv('SDR_GAIN', 'auto'),
        'scan_time': os.getenv('SCAN_TIME_SECONDS', '10'),
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
