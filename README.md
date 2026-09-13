# sdrpy
Using an SDR dongle and a Raspberry Pi to track VHF animal trackers.

## Setup Instructions

### 1. Prerequisites
You will need a Raspberry Pi and an RTL-SDR Blog V4 dongle.

### 2. Install System Dependencies
Update your package list and install the required tools to build the RTL-SDR drivers.
```bash
sudo apt update
sudo apt install git cmake build-essential libusb-1.0-0-dev python3-pip
```

### 3. Install RTL-SDR Blog V4 Drivers
The RTL-SDR Blog V4 requires updated drivers to function properly. You must compile these from source:

```bash
git clone https://github.com/rtlsdrblog/rtl-sdr-blog
cd rtl-sdr-blog
mkdir build
cd build
cmake ../ -DINSTALL_UDEV_RULES=ON
make
sudo make install
sudo cp ../rtl-sdr.rules /etc/udev/rules.d/
sudo ldconfig
```

After installation, reboot your Raspberry Pi or reload the udev rules to apply the changes.

### 4. Install Python Dependencies
Install the required python packages using pip:
```bash
pip3 install -r requirements.txt
```

### 5. Configuration
Copy the `.env.example` file to create your `.env` configuration file:
```bash
cp .env.example .env
```
Edit the `.env` file to match your specific settings (GPS coordinates, frequencies mapped to animal names, SDR gain, and scan time). Ensure the animal frequencies are in JSON format.

### 6. Run the Tracker
To start the tracking script:
```bash
python3 tracker.py
```

The script will tune to each frequency for the specified scan time, calculate the signal strength using FFT, estimate the Beats Per Minute (BPM) based on signal pulses (40 BPM for moving, 80 BPM for stationary), and log the results (including time, animal name, frequency, peak signal strength, estimated BPM, and GPS coordinates) to a CSV file.

### 7. Run the Web Interface
A web dashboard is provided to monitor the logs and update settings.
```bash
python3 app.py
```
Open a web browser and navigate to `http://<raspberry_pi_ip>:5000` to view the dashboard and manage settings.
