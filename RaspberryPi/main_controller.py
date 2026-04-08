import time
import board
import busio
import smbus
import math
import adafruit_bme280.advanced as adafruit_bme280
import adafruit_bh1750
from gpiozero import InputDevice, OutputDevice, PWMOutputDevice, DistanceSensor, RotaryEncoder
import firebase_admin
from firebase_admin import credentials, firestore
import threading
import sys
import socket
import random
import json
import os
from datetime import datetime

# Configuration
SERVICE_ACCOUNT_KEY_PATH = '/home/tp073666/tp073666-fyp-firebase-adminsdk-fbsvc-d427ca4238.json'
LOCAL_CONFIG_FILE = 'rack_local_config.json'

FIRESTORE_COLLECTION_SENSORS = 'sensor_data'
FIRESTORE_DOCUMENT_SENSORS = 'live_data'
FIRESTORE_COLLECTION_CONTROL = 'control'
FIRESTORE_DOCUMENT_CONTROL = 'motor_command'
FIRESTORE_COLLECTION_CONFIG = 'config'
FIRESTORE_DOCUMENT_CONFIG_IP = 'pi_config'
FIRESTORE_DOCUMENT_CONFIG_TARGET = 'target_position'
FIRESTORE_DOCUMENT_CONFIG_SCHEDULE = 'schedule'
FIRESTORE_COLLECTION_LOGS = 'system_events'

# I2C Addresses
BME280_ADDRESS = 0x76
BH1750_ADDRESS = 0x23
MPU6050_ADDRESS = 0x68

# GPIO Pins
MOTOR_A_IN1 = 17
MOTOR_A_IN2 = 18
MOTOR_A_ENA = 22
MOTOR_B_IN3 = 23
MOTOR_B_IN4 = 24
MOTOR_B_ENB = 25
ENCODER_A_PIN_A = 9
ENCODER_A_PIN_B = 10
ENCODER_B_PIN_A = 7
ENCODER_B_PIN_B = 8
FRONT_TRIG_PIN = 5
FRONT_ECHO_PIN = 6
BACK_TRIG_PIN = 19
BACK_ECHO_PIN = 26
RAIN_SENSOR_PIN = 27
BUZZER_PIN = 13

# Tuning
MOTOR_SPEED_MOVE = 0.87
MOTOR_SPEED_TURN = 0.60

# PI Controller Tuning
GYRO_P_GAIN = 0.06
GYRO_I_GAIN = 0.005
MAX_CORRECTION = 0.81

OBSTACLE_STOP_DISTANCE_CM = 20
SENSOR_UPDATE_INTERVAL_SECONDS = 5.0

# TIMEOUTS
FIRESTORE_TIMEOUT_CRITICAL = 10
FIRESTORE_TIMEOUT_LIVE = 3

# Global Variables
db = None
bme280, bh1750, mpu6050 = None, None, None
motor_a_in1, motor_a_in2, motor_a_ena = None, None, None
motor_b_in3, motor_b_in4, motor_b_enb = None, None, None
encoder_a, encoder_b, front_sensor, back_sensor, rain_sensor, buzzer = None, None, None, None, None, None

current_rack_status = "stopped"
manual_control_active = False
bird_repellent_active = False
stop_threads = threading.Event()

# PATH RECORDING & GYRO GLOBALS
path_log = []
current_segment_start = {}
recorded_path_data = {'path': [], 'last_updated': 0}
current_heading = 0.0
target_lock_heading = 0.0
accumulated_error = 0.0

# ENCODER SOFTWARE ZEROING
encoder_offset_a = 0
encoder_offset_b = 0

# SCHEDULER GLOBALS
active_schedule = {'enabled': False, 'time': '00:00', 'action': 'none'}
last_schedule_run_date = None

# Get Corrected Steps
def get_steps():
    """Returns (steps_a, steps_b) corrected by the software offset (Home=0)."""
    raw_a = encoder_a.steps if encoder_a else 0
    raw_b = encoder_b.steps if encoder_b else 0
    return (raw_a - encoder_offset_a), (raw_b - encoder_offset_b)

# MPU6050 & Heading Tracking
class MPU6050_SMBus:
    def __init__(self, address=0x68, bus_num=1):
        self.address = address
        self.bus = smbus.SMBus(bus_num)
        try: self.bus.write_byte_data(self.address, 0x6B, 0)
        except: pass
    def _read_word(self, reg):
        try:
            high = self.bus.read_byte_data(self.address, reg)
            low = self.bus.read_byte_data(self.address, reg + 1)
            val = (high << 8) + low
            return -((65535 - val) + 1) if val >= 0x8000 else val
        except: return 0
    @property
    def gyro_z(self):
        raw = self._read_word(0x47)
        return raw / 131.0

def heading_tracker_loop():
    global current_heading, mpu6050
    print("DEBUG: Calibrating Gyro...")
    bias = 0.0
    samples = 100
    if mpu6050:
        for _ in range(samples):
            bias += mpu6050.gyro_z
            time.sleep(0.01)
        bias /= samples
    print(f"DEBUG: Gyro Bias: {bias:.4f}")

    last_time = time.time()

    while not stop_threads.is_set():
        if mpu6050:
            try:
                now = time.time()
                dt = now - last_time
                last_time = now
                rate = mpu6050.gyro_z - bias
                if abs(rate) < 1.0: rate = 0
                current_heading += rate * dt
            except: pass
        time.sleep(0.02)

def active_correction_loop():
    global motor_a_ena, motor_b_enb, current_heading, target_lock_heading, current_rack_status, accumulated_error
    while not stop_threads.is_set():
        if current_rack_status in ["extending", "retracting"]:
            error = current_heading - target_lock_heading
            accumulated_error += error
            accumulated_error = max(-30.0, min(30.0, accumulated_error))
            correction = (error * GYRO_P_GAIN) + (accumulated_error * GYRO_I_GAIN)
            correction = max(-MAX_CORRECTION, min(MAX_CORRECTION, correction))

            # Reverse Logic
            if current_rack_status == "retracting": correction = -correction

            # Apply Correction
            speed_a = max(0.0, min(1.0, MOTOR_SPEED_MOVE + correction))
            speed_b = max(0.0, min(1.0, MOTOR_SPEED_MOVE - correction))

            motor_a_ena.value = speed_a
            motor_b_enb.value = speed_b

            print(f"PID: Err={error:.1f} Corr={correction:.2f} SpdA={speed_a:.2f} SpdB={speed_b:.2f}")
        else:
            accumulated_error = 0.0
        time.sleep(0.05)

# Scheduler Logic
def scheduler_loop():
    global active_schedule, last_schedule_run_date
    print("DEBUG: Scheduler Started")

    while not stop_threads.is_set():
        try:
            if active_schedule.get('enabled', False):
                now = datetime.now()
                current_time_str = now.strftime("%H:%M")
                target_time = active_schedule.get('time', '00:00')

                if current_time_str == target_time:
                    today_str = now.strftime("%Y-%m-%d %H:%M")
                    if last_schedule_run_date != today_str:
                        action = active_schedule.get('action')
                        print(f"DEBUG: Schedule Triggered! {action} at {current_time_str}")
                        log_event(f"Schedule: {action}")
                        last_schedule_run_date = today_str

                        if action == 'auto_extend':
                            threading.Thread(target=execute_auto_extend).start()
                        elif action == 'auto_retract':
                            threading.Thread(target=execute_auto_retract).start()
        except Exception as e:
            print(f"Scheduler Error: {e}")
        time.sleep(1)

# Local Storage
def load_local_config():
    global recorded_path_data
    if os.path.exists(LOCAL_CONFIG_FILE):
        try:
            with open(LOCAL_CONFIG_FILE, 'r') as f:
                content = f.read()
                if not content:
                    print("DEBUG: Local Config File is EMPTY.")
                    return
                data = json.loads(content)
                recorded_path_data = data
                print(f"DEBUG: Loaded Path: {len(recorded_path_data.get('path', []))} segments")
        except Exception as e:
            print(f"DEBUG: Error loading config: {e}")

def save_local_config(data):
    try:
        json_str = json.dumps(data)
        with open(LOCAL_CONFIG_FILE, 'w') as f:
            f.write(json_str)
            f.flush()
            os.fsync(f.fileno())
        print(f"DEBUG: Saved Local Config to {LOCAL_CONFIG_FILE}")
    except Exception as e:
        print(f"DEBUG: Error saving local config: {e}")

def log_event(message):
    if db:
        try: db.collection(FIRESTORE_COLLECTION_LOGS).add({'message': message, 'timestamp': firestore.SERVER_TIMESTAMP})
        except: pass

# Initialization
def get_ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]; s.close()
    except: IP = '127.0.0.1'
    return IP

def initial_network_setup():
    global recorded_path_data, active_schedule
    print("DEBUG: Network Setup...")
    retries = 0
    while not stop_threads.is_set() and retries < 5:
        try:
            ip = get_ip_address()
            if ip != '127.0.0.1' and db:
                db.collection(FIRESTORE_COLLECTION_CONFIG).document(FIRESTORE_DOCUMENT_CONFIG_IP).set({'ip_address': ip}, timeout=FIRESTORE_TIMEOUT_CRITICAL)
                break
        except: pass
        time.sleep(5); retries += 1

    try:
        if db:
            doc = db.collection(FIRESTORE_COLLECTION_CONFIG).document(FIRESTORE_DOCUMENT_CONFIG_TARGET).get(timeout=FIRESTORE_TIMEOUT_CRITICAL)
            if doc.exists:
                cloud_data = doc.to_dict()
                if cloud_data.get('last_updated', 0) >= recorded_path_data.get('last_updated', 0):
                    recorded_path_data = cloud_data
                    save_local_config(recorded_path_data)
                    print("DEBUG: Synced Path from Cloud")
                else:
                    db.collection(FIRESTORE_COLLECTION_CONFIG).document(FIRESTORE_DOCUMENT_CONFIG_TARGET).set(recorded_path_data)

            sched_doc = db.collection(FIRESTORE_COLLECTION_CONFIG).document(FIRESTORE_DOCUMENT_CONFIG_SCHEDULE).get(timeout=FIRESTORE_TIMEOUT_CRITICAL)
            if sched_doc.exists:
                active_schedule = sched_doc.to_dict()
                print(f"DEBUG: Loaded Schedule: {active_schedule}")

    except: pass

def init_firebase():
    global db
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        t = threading.Thread(target=initial_network_setup, daemon=True); t.start()
        print("DEBUG: Firebase Credential Loaded.")
        return True
    except Exception as e:
        print(f"DEBUG: Firebase Init Error: {e}")
        return False

def init_hardware():
    global bme280, bh1750, mpu6050, motor_a_in1, motor_a_in2, motor_a_ena, motor_b_in3, motor_b_in4, motor_b_enb, encoder_a, encoder_b, front_sensor, back_sensor, rain_sensor, buzzer
    print("DEBUG: Initializing Hardware...")
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        try: bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=BME280_ADDRESS)
        except: pass
        try: bh1750 = adafruit_bh1750.BH1750(i2c, address=BH1750_ADDRESS)
        except: pass
        try: mpu6050 = MPU6050_SMBus(address=MPU6050_ADDRESS)
        except: pass
    except: pass

    try:
        motor_a_in1 = OutputDevice(MOTOR_A_IN1); motor_a_in2 = OutputDevice(MOTOR_A_IN2); motor_a_ena = PWMOutputDevice(MOTOR_A_ENA)
        motor_b_in3 = OutputDevice(MOTOR_B_IN3); motor_b_in4 = OutputDevice(MOTOR_B_IN4); motor_b_enb = PWMOutputDevice(MOTOR_B_ENB)
        encoder_a = RotaryEncoder(ENCODER_A_PIN_A, ENCODER_A_PIN_B, max_steps=0)
        encoder_b = RotaryEncoder(ENCODER_B_PIN_A, ENCODER_B_PIN_B, max_steps=0)
        front_sensor = DistanceSensor(echo=FRONT_ECHO_PIN, trigger=FRONT_TRIG_PIN, max_distance=2)
        back_sensor = DistanceSensor(echo=BACK_ECHO_PIN, trigger=BACK_TRIG_PIN, max_distance=2)
        rain_sensor = InputDevice(RAIN_SENSOR_PIN, pull_up=True)
        buzzer = PWMOutputDevice(BUZZER_PIN, initial_value=0, frequency=1000)
        return True
    except Exception as e:
        print(f"DEBUG: Hardware Init Error: {e}")
        return False

def stop_motors():
    global current_rack_status, manual_control_active, path_log, current_segment_start, accumulated_error

    # 1. Disable PID Loop to Prevent Fighting
    previous_status = current_rack_status
    current_rack_status = "stopped"

    # 2. Hard Brake
    motor_a_ena.value = 1.0; motor_b_enb.value = 1.0
    motor_a_in1.on(); motor_a_in2.on(); motor_b_in3.on(); motor_b_in4.on()
    time.sleep(0.1)

    # 3. Release
    motor_a_in1.off(); motor_a_in2.off(); motor_b_in3.off(); motor_b_in4.off()
    motor_a_ena.value = 0; motor_b_enb.value = 0
    accumulated_error = 0.0

    # RECORDING LOGIC
    if current_segment_start and manual_control_active:
        seg_type = current_segment_start.get('type')

        if seg_type == 'line':

            st_a, st_b = get_steps()
            current_avg_enc = (st_a + st_b) / 2
            start_avg_enc = current_segment_start.get('start_val', 0)
            delta = current_avg_enc - start_avg_enc

            print(f"DEBUG: Stop. Line Delta: {delta} (Avg Start: {start_avg_enc}, End: {current_avg_enc})")

            if abs(delta) > 50:
                path_log.append({'type': 'line', 'val': delta})
                print(f"DEBUG: >>> Recorded Line: {delta}")

        elif seg_type == 'turn':
            start_angle = current_segment_start.get('start_val', 0)
            delta = current_heading - start_angle

            print(f"DEBUG: Stop. Turn Delta: {delta}")

            if abs(delta) > 2.0:
                path_log.append({'type': 'turn', 'val': delta})
                print(f"DEBUG: >>> Recorded Turn: {delta:.1f}")

    current_segment_start = {}
    manual_control_active = False

def move(direction):
    global current_rack_status, current_segment_start, target_lock_heading, accumulated_error
    target_lock_heading = current_heading
    accumulated_error = 0.0

    st_a, st_b = get_steps()
    start_val = (st_a + st_b) / 2

    current_segment_start = {
        'type': 'line',
        'start_val': start_val
    }

    if direction == "forward":
        if front_sensor.distance * 100 < OBSTACLE_STOP_DISTANCE_CM: stop_motors(); return
        current_rack_status = "extending"
        motor_a_in1.on(); motor_a_in2.off(); motor_b_in3.on(); motor_b_in4.off()
    elif direction == "backward":
        if back_sensor.distance * 100 < OBSTACLE_STOP_DISTANCE_CM: stop_motors(); return
        current_rack_status = "retracting"
        motor_a_in1.off(); motor_a_in2.on(); motor_b_in3.off(); motor_b_in4.on()

    motor_a_ena.value = MOTOR_SPEED_MOVE; motor_b_enb.value = MOTOR_SPEED_MOVE

def turn(direction):
    global current_rack_status, current_segment_start
    current_segment_start = {'type': 'turn', 'start_val': current_heading}

    if direction == "left":
        current_rack_status = "turning_l"
        motor_a_in1.off(); motor_a_in2.on(); motor_b_in3.on(); motor_b_in4.off()
    elif direction == "right":
        current_rack_status = "turning_r"
        motor_a_in1.on(); motor_a_in2.off(); motor_b_in3.off(); motor_b_in4.on()
    motor_a_ena.value = MOTOR_SPEED_TURN; motor_b_enb.value = MOTOR_SPEED_TURN

# Playback Logic
def execute_segment_line(target_delta):
    global current_rack_status, target_lock_heading, accumulated_error
    target_lock_heading = current_heading
    accumulated_error = 0.0

    st_a, st_b = get_steps()
    start_enc = (st_a + st_b) / 2
    target_enc = start_enc + target_delta
    direction = "forward" if target_delta > 0 else "backward"

    if direction == "forward":
        motor_a_in1.on(); motor_a_in2.off(); motor_b_in3.on(); motor_b_in4.off()
        current_rack_status = "extending"
    else:
        motor_a_in1.off(); motor_a_in2.on(); motor_b_in3.off(); motor_b_in4.on()
        current_rack_status = "retracting"

    motor_a_ena.value = MOTOR_SPEED_MOVE; motor_b_enb.value = MOTOR_SPEED_MOVE
    timeout = time.time() + 10

    while time.time() < timeout:
        curr_a, curr_b = get_steps()
        current_enc = (curr_a + curr_b) / 2

        if direction == "forward" and current_enc >= target_enc: break
        if direction == "backward" and current_enc <= target_enc: break

        if direction == "forward" and front_sensor.distance * 100 < OBSTACLE_STOP_DISTANCE_CM: break
        if direction == "backward" and back_sensor.distance * 100 < OBSTACLE_STOP_DISTANCE_CM: break
        time.sleep(0.05)
    motor_a_ena.value = 0; motor_b_enb.value = 0; current_rack_status = "stopped"

def execute_segment_turn(target_delta_angle):
    start_angle = current_heading
    target_angle = start_angle + target_delta_angle
    if target_delta_angle > 0: motor_a_in1.off(); motor_a_in2.on(); motor_b_in3.on(); motor_b_in4.off()
    else: motor_a_in1.on(); motor_a_in2.off(); motor_b_in3.off(); motor_b_in4.on()
    motor_a_ena.value = MOTOR_SPEED_TURN; motor_b_enb.value = MOTOR_SPEED_TURN
    timeout = time.time() + 5
    while time.time() < timeout:
        if target_delta_angle > 0 and current_heading >= target_angle: break
        if target_delta_angle < 0 and current_heading <= target_angle: break
        time.sleep(0.02)
    motor_a_ena.value = 0; motor_b_enb.value = 0

def execute_auto_retract():
    global manual_control_active, current_rack_status
    manual_control_active = True
    path = recorded_path_data.get('path', [])

    if not path or len(path) == 0:
        print("DEBUG: ERROR - Auto Retract called but PATH IS EMPTY")
        log_event("Error: Auto Failed (No Path)")
        manual_control_active = False
        current_rack_status = "stopped"
        return

    print("DEBUG: Smart Retract")
    for segment in reversed(path):
        seg_type = segment['type']; val = segment['val']
        if seg_type == 'line': execute_segment_line(-val)
        elif seg_type == 'turn': execute_segment_turn(-val)
        time.sleep(0.5)
    manual_control_active = False; current_rack_status = "stopped"
    set_home_position()

def execute_auto_extend():
    global manual_control_active, current_rack_status
    manual_control_active = True
    path = recorded_path_data.get('path', [])

    if not path or len(path) == 0:
        print("DEBUG: ERROR - Auto Extend called but PATH IS EMPTY")
        log_event("Error: Auto Failed (No Path)")
        manual_control_active = False
        current_rack_status = "stopped"
        return

    for segment in path:
        seg_type = segment['type']; val = segment['val']
        if seg_type == 'line': execute_segment_line(val)
        elif seg_type == 'turn': execute_segment_turn(val)
        time.sleep(0.5)
    manual_control_active = False; current_rack_status = "stopped"

def set_home_position():
    global encoder_offset_a, encoder_offset_b, path_log, current_heading, target_lock_heading, accumulated_error, recorded_path_data

    # SOFT ZERO
    if encoder_a and encoder_b:
        encoder_offset_a = encoder_a.steps
        encoder_offset_b = encoder_b.steps

    path_log = []
    current_heading = 0.0
    target_lock_heading = 0.0
    accumulated_error = 0.0

    log_event("Home Set & Path Cleared")
    print(f"DEBUG: Soft Home Set. Offsets: A={encoder_offset_a}, B={encoder_offset_b}")

def save_target_position():
    global recorded_path_data, path_log

    print(f"DEBUG: Saving Target. Current Path Log has {len(path_log)} items.")
    for i, p in enumerate(path_log):
        print(f"  [{i}] {p}")

    new_data = {'path': list(path_log), 'last_updated': time.time()}
    recorded_path_data = new_data
    save_local_config(new_data)
    try:
        db.collection(FIRESTORE_COLLECTION_CONFIG).document(FIRESTORE_DOCUMENT_CONFIG_TARGET).set(new_data, timeout=FIRESTORE_TIMEOUT_CRITICAL)
        log_event(f"Path Saved: {len(path_log)} steps")
    except: pass

def bird_repellent_loop():
    while not stop_threads.is_set():
        if bird_repellent_active and buzzer:
            freq = random.randint(2000, 8000)
            try: buzzer.frequency = freq; buzzer.value = 0.5; time.sleep(0.5); buzzer.value = 0; time.sleep(random.uniform(0.5, 2.0))
            except: pass
        else:
            if buzzer: buzzer.value = 0
            time.sleep(1)

def firestore_listener():
    global manual_control_active, bird_repellent_active, active_schedule

    doc_ref = db.collection(FIRESTORE_COLLECTION_CONTROL).document(FIRESTORE_DOCUMENT_CONTROL)
    sched_ref = db.collection(FIRESTORE_COLLECTION_CONFIG).document(FIRESTORE_DOCUMENT_CONFIG_SCHEDULE)

    def on_snapshot_control(docs, changes, read_time):
        global manual_control_active, bird_repellent_active
        for doc in docs:
            raw_cmd = doc.to_dict().get('command', '')
            cmd = raw_cmd.strip()
            print(f"DEBUG: Cmd: '{cmd}'")
            if cmd == 'move_forward': manual_control_active = True; move("forward")
            elif cmd == 'move_backward': manual_control_active = True; move("backward")
            elif cmd == 'turn_left': manual_control_active = True; turn("left")
            elif cmd == 'turn_right': manual_control_active = True; turn("right")
            elif cmd == 'stop': stop_motors()
            elif cmd == 'auto_extend': threading.Thread(target=execute_auto_extend).start()
            elif cmd == 'auto_retract': threading.Thread(target=execute_auto_retract).start()
            elif cmd == 'set_home' or cmd == 'set_home_position':
                set_home_position()
            elif cmd == 'set_extend' or cmd == 'set_extend_position':
                save_target_position()

            elif cmd == 'bird_on': bird_repellent_active = True; log_event("Bird ON")
            elif cmd == 'bird_off': bird_repellent_active = False; log_event("Bird OFF")

            else:
                print(f"DEBUG: Unknown command ignored: {cmd}")

    def on_snapshot_schedule(docs, changes, read_time):
        global active_schedule
        for doc in docs:
            if doc.exists:
                active_schedule = doc.to_dict()
                print(f"DEBUG: Schedule Updated: {active_schedule}")
                global last_executed_schedule_sig
                last_executed_schedule_sig = "" 

    try:
        doc_ref.on_snapshot(on_snapshot_control)
        sched_ref.on_snapshot(on_snapshot_schedule)
        stop_threads.wait()
    except: pass

def main_loop():
    global current_rack_status, bird_repellent_active
    print("DEBUG: Main Loop Started.")
    while not stop_threads.is_set():
        data = {'timestamp': firestore.SERVER_TIMESTAMP, 'motor_status': current_rack_status}
        if bme280:
            try: data['temp'], data['hum'] = bme280.temperature, bme280.humidity
            except: pass
        if bh1750:
            try: data['lux'] = bh1750.lux
            except: pass
        if rain_sensor: data['rain'] = rain_sensor.is_active

        try:
            st_a, st_b = get_steps()
            data['front_dist'] = front_sensor.distance * 100
            data['back_dist'] = back_sensor.distance * 100
            data['enc_a'] = st_a; data['enc_b'] = st_b
            data['heading'] = current_heading; data['bird_repellent'] = bird_repellent_active
        except: pass

        try:
            db.collection(FIRESTORE_COLLECTION_SENSORS).document(FIRESTORE_DOCUMENT_SENSORS).set(data, merge=True, timeout=FIRESTORE_TIMEOUT_LIVE)
            print("DEBUG: Upload Success!")
        except Exception as e:
            print(f"DEBUG: Upload Error: {e}")

        now_str = datetime.now().strftime("%H:%M:%S")
        msg = f"[{now_str}] Status: {current_rack_status} | "
        if 'temp' in data: msg += f"T: {data['temp']:.1f}C H: {data['hum']:.1f}% | "
        if 'lux' in data: msg += f"L: {data['lux']:.0f}lx | "
        if 'rain' in data: msg += f"Rain: {data['rain']} | "
        try: msg += f"Dist F/B: {data['front_dist']:.1f}/{data['back_dist']:.1f}cm | "
        except: pass
        try: msg += f"Enc A/B: {data['enc_a']}/{data['enc_b']} | Head: {data['heading']:.1f}"
        except: pass
        print(msg)

        if not manual_control_active:
             if rain_sensor and rain_sensor.is_active and current_rack_status == "stopped":
                 if encoder_a.steps > 100:
                     print("DEBUG: Rain detected! Auto Retracting...")
                     threading.Thread(target=execute_auto_retract).start()
        time.sleep(SENSOR_UPDATE_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        if not init_firebase(): print("Firebase Error")
        load_local_config()
        if not init_hardware(): sys.exit(1)

        t1 = threading.Thread(target=firestore_listener, daemon=True); t1.start()
        t2 = threading.Thread(target=bird_repellent_loop, daemon=True); t2.start()
        t3 = threading.Thread(target=heading_tracker_loop, daemon=True); t3.start()
        t4 = threading.Thread(target=active_correction_loop, daemon=True); t4.start()
        t5 = threading.Thread(target=scheduler_loop, daemon=True); t5.start()
        main_loop()

    except KeyboardInterrupt: pass
    finally:
        stop_threads.set()
        if 'motor_a_in1' in globals() and motor_a_in1 is not None: stop_motors()