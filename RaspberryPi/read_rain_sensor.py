from gpiozero import InputDevice
from signal import pause
import time

# Configuration
# Set GPIO Pin Number
RAIN_SENSOR_PIN = 27

# Setup
rain_sensor = InputDevice(RAIN_SENSOR_PIN, pull_up=True)

print("Rain Sensor Test. Press Ctrl+C to exit.")
print("-" * 30)

try:
    while True:
        # Read Sensor's Digital Output.
        # When Sensor = WET, DO Pin = LOW (0).
        # When Sensor = DRY, DO Pin = HIGH (1).
        if rain_sensor.is_active:
            print("Status: WET!")
        else:
            print("Status: DRY")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nScript stopped by user.")

finally:
    print("Exiting.")