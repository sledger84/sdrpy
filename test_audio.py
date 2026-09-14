import time
import numpy as np
from flask import Flask, Response

app = Flask(__name__)

def generate_audio():
    # WAV Header
    # 32kHz, 16-bit, mono
    sample_rate = 32000

    # 44 bytes header
    # "RIFF"
    # ChunkSize (0xFFFFFFFF)
    # "WAVE"
    # "fmt "
    # Subchunk1Size (16 for PCM)
    # AudioFormat (1 for PCM)
    # NumChannels (1)
    # SampleRate (32000)
    # ByteRate (32000 * 2)
    # BlockAlign (2)
    # BitsPerSample (16)
    # "data"
    # Subchunk2Size (0xFFFFFFFF)
    import struct
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
                         b'RIFF', 0xFFFFFFFF, b'WAVE', b'fmt ', 16, 1, 1,
                         sample_rate, sample_rate * 2, 2, 16, b'data', 0xFFFFFFFF)
    yield header

    t = 0.0
    while True:
        # Generate 0.1 seconds of audio
        samples = int(sample_rate * 0.1)
        time_array = np.arange(samples) / sample_rate + t
        t += 0.1

        # 1 kHz tone, pulsing on and off
        if (t % 1.5) < 0.1:
            audio = 10000 * np.sin(2 * np.pi * 1000 * time_array)
        else:
            audio = np.random.normal(scale=100, size=samples)

        audio_int16 = np.int16(audio)
        yield audio_int16.tobytes()
        time.sleep(0.1)

@app.route('/audio')
def audio():
    return Response(generate_audio(), mimetype='audio/x-wav')

if __name__ == '__main__':
    app.run(port=5001)
