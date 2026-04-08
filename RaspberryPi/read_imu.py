import smbus
import time
import math

# MPU6050 Registers
MPU_ADDR = 0x68      # I2C Address of MPU6050
PWR_MGMT_1 = 0x6B    # Power Management Register
ACCEL_XOUT_H = 0x3B  # Start of Accelerometer Data Registers
GYRO_XOUT_H = 0x43   # Start of Ggyroscope Data Registers

# Constants for Conversion
# Accelerometer
ACCEL_SENSITIVITY = 16384.0
EARTH_GRAVITY = 9.80665

# Gyroscope
GYRO_SENSITIVITY = 131.0

# Setup I2C Bus
bus = smbus.SMBus(1)

def read_word(reg):
    """Reads a 16-bit word (two 8-bit bytes) from the I2C device."""
    high = bus.read_byte_data(MPU_ADDR, reg)
    low = bus.read_byte_data(MPU_ADDR, reg + 1)
    value = (high << 8) + low

    # Convert from 16-bit unsigned to 16-bit signed
    if value > 32768:
        value -= 65536
    return value

def setup_mpu():
    bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)
    print("MPU6050 initialized (using smbus)\n")

def loop_read():
    while True:
        raw_acc_x = read_word(ACCEL_XOUT_H)
        raw_acc_y = read_word(ACCEL_XOUT_H + 2)
        raw_acc_z = read_word(ACCEL_XOUT_H + 4)

        raw_gyro_x = read_word(GYRO_XOUT_H)
        raw_gyro_y = read_word(GYRO_XOUT_H + 2)
        raw_gyro_z = read_word(GYRO_XOUT_H + 4)

        # Accelerometer: Raw -> 'g's -> m/s^2
        accel_x_ms2 = (raw_acc_x / ACCEL_SENSITIVITY) * EARTH_GRAVITY
        accel_y_ms2 = (raw_acc_y / ACCEL_SENSITIVITY) * EARTH_GRAVITY
        accel_z_ms2 = (raw_acc_z / ACCEL_SENSITIVITY) * EARTH_GRAVITY

        # Gyroscope: Raw -> °/s -> rad/s
        gyro_x_rads = (raw_gyro_x / GYRO_SENSITIVITY) * (math.pi / 180.0)
        gyro_y_rads = (raw_gyro_y / GYRO_SENSITIVITY) * (math.pi / 180.0)
        gyro_z_rads = (raw_gyro_z / GYRO_SENSITIVITY) * (math.pi / 180.0)

        print(f"Acceleration X: {accel_x_ms2:5.2f}, Y: {accel_y_ms2:5.2f}, Z: {accel_z_ms2:5.2f} m/s^2")
        print(f"Gyroscope    X: {gyro_x_rads:5.2f}, Y: {gyro_y_rads:5.2f}, Z: {gyro_z_rads:5.2f} rad/s")
        print("-" * 20)

        time.sleep(1)

if __name__ == "__main__":
    try:
        setup_mpu()
        loop_read()
    except KeyboardInterrupt:
        print("\nScript stopped by user.")
    except IOError as e:
        print(f"IOError detected: {e}")
        print("This can be a wiring issue OR a kernel driver conflict.")
        print("Please ensure you have run 'sudo nano /etc/modprobe.d/mpu6050-blacklist.conf' and rebooted.")
    finally:
        print("Exiting.")