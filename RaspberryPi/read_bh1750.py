import time
import board
import adafruit_bh1750

# Create I2C Bus Interface.
i2c = board.I2C()

# Create BH1750 Sensor Object.
# The address 0x23 is the default for this sensor.
try:
    sensor = adafruit_bh1750.BH1750(i2c, address=0x23)
except Exception as e:
    print(f"Error initializing BH1750 sensor at address 0x23: {e}")
    # Some boards use address 0x5C, let's try that as a fallback.
    try:
        print("Trying fallback address 0x5C...")
        sensor = adafruit_bh1750.BH1750(i2c, address=0x5C)
        print("Sensor found at 0x5C!")
    except Exception as e2:
        print(f"Error initializing BH1750 sensor at fallback address 0x5C: {e2}")
        print("Could not find the BH1750 sensor. Please check your wiring.")
        exit()


print("BH1750 Light Sensor Test. Press Ctrl+C to exit.")
print("-" * 20)

try:
    while True:
        # Read Light Level in Lux.
        light_level = sensor.lux

        print(f"Light: {light_level:.2f} lux")

        time.sleep(1)

except KeyboardInterrupt:
    print("\nScript stopped by user.")

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    print("Script finished.")