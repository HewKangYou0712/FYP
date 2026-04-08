import io
import time
import threading
from flask import Flask, Response                                                                                                   # type: ignore
from picamera2.encoders import JpegEncoder                                                                                                                              # type: ignore
from picamera2 import Picamera2                                                                                                         # type: ignore
from picamera2.outputs import FileOutput                                                                                            # type: ignore

# Global Camera Object
picam2 = None
output = None
lock = threading.Lock()

# Thread-safe Streaming Output Class
class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

    def read(self):
        with self.condition:
            # Wait for A New Frame to be Written by Camera Thread
            self.condition.wait()
            return self.frame

# Flask Web Server Setup
app = Flask(__name__)

# Video Stream Generator
def generate_video_stream():
    global output
    while True:
        try:
            # read() Blocks until A New Frame is Available from StreamingOutput
            frame = output.read()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        except Exception as e:
            print(f"Error in video stream generator: {e}")
            break

# Simple Index Route
@app.route('/')
def index():
    return "Camera Stream is running. Access the feed at /video_feed"

# Main Video Feed Route
@app.route('/video_feed')
def video_feed():
    return Response(generate_video_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# Run in Separate Thread to Capture Camera Frames
def start_camera_thread():
    global picam2, output
    with lock:
        picam2 = Picamera2()
        # Configure Camera for Streaming
        # config = picam2.create_video_configuration(main={"size": (640, 480)})
        config = picam2.create_video_configuration(main={"size": (320, 240), "format": "RGB888"})
        picam2.configure(config)
        
        # Create Thread-safe Output Object
        output = StreamingOutput()
        
        # Wrap Output in FileOutput to Make It Compatible with start_recording
        file_output = FileOutput(output)
        
        # Start Recording to Output Object Using JPEG Encoder
        picam2.start_recording(JpegEncoder(), file_output)
        print("Camera recording started (320x240 optimized).")

# Main Execution
if __name__ == '__main__':
    try:
        # Start Camera Capture in Background Thread
        camera_thread = threading.Thread(target=start_camera_thread, daemon=True)
        camera_thread.start()
        
        # Wait Camera to Initialize
        time.sleep(2)
        
        print("Starting Flask web server...")
        print("Your video stream will be available at: http://<YOUR_PI_IP>:8000/video_feed")
        # Start Flask Web Server
        app.run(host='0.0.0.0', port=8000, threaded=True)
        
    except KeyboardInterrupt:
        print("\nStopping server and camera...")
    finally:
        if picam2:
            picam2.stop_recording()
            picam2.stop()
        print("Server shut down.")