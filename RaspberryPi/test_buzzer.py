from gpiozero import PWMOutputDevice
import time

# Configuration
BUZZER_PIN = 13 
# Setup
try:
    buzzer = PWMOutputDevice(BUZZER_PIN, initial_value=0, frequency=1000)
    print(f"Buzzer initialized on GPIO {BUZZER_PIN}")
except Exception as e:
    print(f"Error initializing buzzer: {e}")
    exit()

def play_frequency(freq, duration):
    try:
        print(f"Playing {freq} Hz...")
        buzzer.frequency = freq
        buzzer.value = 0.5 
        time.sleep(duration)
        buzzer.value = 0
    except Exception as e:
        print(f"Failed to play {freq} Hz: {e}")

print("Buzzer Test (Safe Range). Press Ctrl+C to exit.")
print("-" * 30)

try:
    # 1. Audible Tests
    play_frequency(2000, 1.0) # 2 kHz
    time.sleep(0.5)
    play_frequency(5000, 1.0) # 5 kHz
    time.sleep(0.5)
    play_frequency(8000, 1.0) # 8 kHz
    time.sleep(0.5)

    # 2. High Pitch Test (Capped at 10kHz for stability)
    print("Playing High Pitch tone (10000 Hz)...")
    play_frequency(10000, 2.0) 
    print("Test complete.")
except KeyboardInterrupt:
    print("\nStopped by user.")
finally:
    buzzer.off()
    print("Exiting.")