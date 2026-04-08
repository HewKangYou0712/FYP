from gpiozero import DistanceSensor
import time

# Configuration

# Front Sensor
FRONT_TRIGGER_PIN = 5
FRONT_ECHO_PIN    = 6

# Back Sensor
BACK_TRIGGER_PIN  = 19
BACK_ECHO_PIN     = 26

# Setup
try:
    front_sensor = DistanceSensor(echo=FRONT_ECHO_PIN, trigger=FRONT_TRIGGER_PIN)
    back_sensor = DistanceSensor(echo=BACK_ECHO_PIN, trigger=BACK_TRIGGER_PIN)

    print("Both ultrasonic sensors initialized successfully.")

except Exception as e:
    print(f"Error initializing sensors: {e}")
    print("Check your pin numbers and wiring.")
    exit()

print("Dual Distance Sensor Test. Press Ctrl+C to exit.")
print("-" * 30)

try:
    while True:
        # Get Distance
        distance_front_cm = front_sensor.distance * 100
        distance_back_cm  = back_sensor.distance * 100

        print(f"Front: {distance_front_cm:6.1f} cm   |   Back: {distance_back_cm:6.1f} cm")
        time.sleep(1)

except KeyboardInterrupt:
    print("\nScript stopped by user.")

finally:
    print("Exiting.")