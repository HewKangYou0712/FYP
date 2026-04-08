from gpiozero import OutputDevice, PWMOutputDevice, RotaryEncoder
import time

# Configuration
# L298N Motor Control Pins (BCM)
MOTOR_A_IN1 = 17
MOTOR_A_IN2 = 18
MOTOR_A_ENA = 22
MOTOR_B_IN3 = 23
MOTOR_B_IN4 = 24
MOTOR_B_ENB = 25

# Encoder Signal Pins (BCM)
ENCODER_A_PIN_A = 9  # Left Motor Encoder A
ENCODER_A_PIN_B = 10 # Left Motor Encoder B
ENCODER_B_PIN_A = 7  # Right Motor Encoder A
ENCODER_B_PIN_B = 8  # Right Motor Encoder B

# Setup
print("Initializing motor and encoder pins...")

# Motors
motor_a_in1 = OutputDevice(MOTOR_A_IN1)
motor_a_in2 = OutputDevice(MOTOR_A_IN2)
motor_a_ena = PWMOutputDevice(MOTOR_A_ENA)

motor_b_in3 = OutputDevice(MOTOR_B_IN3)
motor_b_in4 = OutputDevice(MOTOR_B_IN4)
motor_b_enb = PWMOutputDevice(MOTOR_B_ENB)

# Encoders
encoder_a = RotaryEncoder(ENCODER_A_PIN_A, ENCODER_A_PIN_B, max_steps=0)
encoder_b = RotaryEncoder(ENCODER_B_PIN_A, ENCODER_B_PIN_B, max_steps=0)
print("Initialization complete.")

# Motor Control Functions
def set_speed(speed=0.8):
    motor_a_ena.value = speed
    motor_b_enb.value = speed

def stop_motors():
    motor_a_in1.off()
    motor_a_in2.off()
    motor_b_in3.off()
    motor_b_in4.off()
    set_speed(0.0)

def motor_a_forward():
    set_speed(0.8)
    motor_a_in1.on()
    motor_a_in2.off()

def motor_a_backward():
    set_speed(0.8)
    motor_a_in1.off()
    motor_a_in2.on()

def motor_b_forward():
    set_speed(0.8)
    motor_b_in3.on()
    motor_b_in4.off()

def motor_b_backward():
    set_speed(0.8)
    motor_b_in3.off()
    motor_b_in4.on()

# Main Test Sequence
print("Encoder Test. Press Ctrl+C to exit.")
print("-" * 30)

try:
    # Test Motor A (Left)
    print(f"--- Testing Motor A (Left)")
    print(f"Initial Encoder A Steps: {encoder_a.steps}")

    print("Running Motor A FORWARD for 2 seconds...")
    motor_a_forward()
    time.sleep(2)
    stop_motors()
    time.sleep(1)
    print(f"  Encoder A Steps after forward: {encoder_a.steps}")

    print("Running Motor A BACKWARD for 2 seconds...")
    motor_a_backward()
    time.sleep(2)
    stop_motors()
    time.sleep(1)
    print(f"  Encoder A Steps after backward: {encoder_a.steps}")
    print("\n" + "-" * 30 + "\n")

    # Test Motor B (Right)
    print(f"--- Testing Motor B (Right)")
    print(f"Initial Encoder B Steps: {encoder_b.steps}")

    print("Running Motor B FORWARD for 2 seconds...")
    motor_b_forward()
    time.sleep(2)
    stop_motors()
    time.sleep(1)
    print(f"  Encoder B Steps after forward: {encoder_b.steps}")

    print("Running Motor B BACKWARD for 2 seconds...")
    motor_b_backward()
    time.sleep(2)
    stop_motors()
    time.sleep(1)
    print(f"  Encoder B Steps after backward: {encoder_b.steps}")
    print("\nTest sequence complete.")

except KeyboardInterrupt:
    print("\nScript stopped by user.")

finally:
    stop_motors()
    print("Exiting script.")