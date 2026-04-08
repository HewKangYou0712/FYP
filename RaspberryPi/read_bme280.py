import time
import board
import adafruit_bme280.advanced as adafruit_bme280

# Create I2C Bus Object as Communication Channel
i2c = board.I2C()

# Create Sensor Object by The I2C Bus.
# The address 0x77 is the default for this sensor. If it fails, try 0x76.
try:
    bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x77)
except ValueError:
    print("Failed to find BME280 sensor at address 0x77. Trying 0x76...")
    try:
        bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
        print("Sensor found at 0x76.")
    except ValueError:
        print("Could not find BME280 sensor. Check wiring.")
        exit()

print("BME280 Sensor Test. Press Ctrl+C to exit.")
print("-" * 30)

try:
    while True:
        # Read Sensor Data
        temperature = bme280.temperature
        humidity = bme280.humidity

        print(f"Temperature: {temperature:.2f} °C")
        print(f"Humidity: {humidity:.2f} %")
        print("-" * 30)

        # Wait for 3 Seconds
        time.sleep(3)

except KeyboardInterrupt:
    print("Script stopped by user.")