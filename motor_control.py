#!/usr/bin/env python3
"""
L298N Motor Driver Control for Raspberry Pi 4
Hardware connections:
- ENA (PWM) → GPIO18
- IN1 (Direction) → GPIO23
- IN2 (Direction) → GPIO24
- OUT1 → Motor positive terminal
- OUT2 → Motor negative terminal
- 12V power supply connected to L298N
"""

import RPi.GPIO as GPIO
import time

# GPIO Pin Configuration
ENA_PIN = 18  # PWM control (speed)
IN1_PIN = 23  # Direction control 1
IN2_PIN = 24  # Direction control 2

# PWM Configuration
PWM_FREQUENCY = 1000  # 1 kHz (good for most DC motors)

class MotorController:
    """L298N Motor Driver Controller"""

    def __init__(self, ena_pin=ENA_PIN, in1_pin=IN1_PIN, in2_pin=IN2_PIN, pwm_freq=PWM_FREQUENCY):
        """
        Initialize motor controller

        Args:
            ena_pin: GPIO pin for PWM (speed control)
            in1_pin: GPIO pin for direction control 1
            in2_pin: GPIO pin for direction control 2
            pwm_freq: PWM frequency in Hz (default 1000 Hz)
        """
        self.ena_pin = ena_pin
        self.in1_pin = in1_pin
        self.in2_pin = in2_pin
        self.pwm_freq = pwm_freq
        self.pwm = None
        self.current_speed = 0
        self.current_direction = "STOPPED"

        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Configure pins
        GPIO.setup(self.ena_pin, GPIO.OUT)
        GPIO.setup(self.in1_pin, GPIO.OUT)
        GPIO.setup(self.in2_pin, GPIO.OUT)

        # Initialize PWM on ENA pin
        self.pwm = GPIO.PWM(self.ena_pin, self.pwm_freq)
        self.pwm.start(0)  # Start with 0% duty cycle (motor off)

        # Ensure motor is stopped
        self.stop()

        print(f"✅ Motor controller initialized")
        print(f"   ENA (PWM): GPIO{self.ena_pin}")
        print(f"   IN1: GPIO{self.in1_pin}")
        print(f"   IN2: GPIO{self.in2_pin}")
        print(f"   PWM Frequency: {self.pwm_freq} Hz")

    def set_speed(self, speed):
        """
        Set motor speed

        Args:
            speed: Speed percentage (0-100)
                   0 = stopped
                   100 = full speed
        """
        # Clamp speed to valid range
        speed = max(0, min(100, speed))
        self.current_speed = speed

        if self.pwm:
            self.pwm.ChangeDutyCycle(speed)

    def forward(self, speed=50):
        """
        Run motor forward

        Args:
            speed: Speed percentage (0-100), default 50%
        """
        GPIO.output(self.in1_pin, GPIO.HIGH)
        GPIO.output(self.in2_pin, GPIO.LOW)
        self.set_speed(speed)
        self.current_direction = "FORWARD"
        print(f"▶️  Motor: FORWARD at {speed}%")

    def reverse(self, speed=50):
        """
        Run motor in reverse

        Args:
            speed: Speed percentage (0-100), default 50%
        """
        GPIO.output(self.in1_pin, GPIO.LOW)
        GPIO.output(self.in2_pin, GPIO.HIGH)
        self.set_speed(speed)
        self.current_direction = "REVERSE"
        print(f"◀️  Motor: REVERSE at {speed}%")

    def stop(self):
        """
        Stop motor (coast to stop - low power consumption)
        IN1=LOW, IN2=LOW, PWM=0
        """
        GPIO.output(self.in1_pin, GPIO.LOW)
        GPIO.output(self.in2_pin, GPIO.LOW)
        self.set_speed(0)
        self.current_direction = "STOPPED"
        print("⏹️  Motor: STOPPED (coast)")

    def brake(self):
        """
        Active brake (quick stop - higher power consumption)
        IN1=HIGH, IN2=HIGH, PWM=100
        """
        GPIO.output(self.in1_pin, GPIO.HIGH)
        GPIO.output(self.in2_pin, GPIO.HIGH)
        self.set_speed(100)
        self.current_direction = "BRAKING"
        print("🛑 Motor: BRAKE (active)")

    def get_status(self):
        """
        Get current motor status

        Returns:
            dict: Motor status (direction, speed)
        """
        return {
            'direction': self.current_direction,
            'speed': self.current_speed
        }

    def cleanup(self):
        """
        Cleanup GPIO and stop motor
        """
        print("\n🧹 Cleaning up motor controller...")
        self.stop()
        if self.pwm:
            self.pwm.stop()
        GPIO.cleanup([self.ena_pin, self.in1_pin, self.in2_pin])
        print("✅ Motor controller cleanup complete")


# Standalone test/demo functions
def run_test_sequence():
    """Run a test sequence to verify motor operation"""
    print("\n" + "="*60)
    print("L298N Motor Controller Test Sequence")
    print("="*60)

    motor = MotorController()

    try:
        print("\n1️⃣  Testing FORWARD at 30% speed...")
        motor.forward(30)
        time.sleep(2)

        print("\n2️⃣  Increasing speed to 60%...")
        motor.set_speed(60)
        time.sleep(2)

        print("\n3️⃣  Full speed forward (100%)...")
        motor.forward(100)
        time.sleep(2)

        print("\n4️⃣  Applying BRAKE...")
        motor.brake()
        time.sleep(1)

        print("\n5️⃣  Testing REVERSE at 30% speed...")
        motor.reverse(30)
        time.sleep(2)

        print("\n6️⃣  Increasing reverse speed to 60%...")
        motor.set_speed(60)
        time.sleep(2)

        print("\n7️⃣  Stopping motor...")
        motor.stop()
        time.sleep(1)

        print("\n✅ Test sequence complete!")

    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")

    finally:
        motor.cleanup()


def manual_control():
    """Interactive manual motor control"""
    print("\n" + "="*60)
    print("L298N Motor Controller - Manual Mode")
    print("="*60)
    print("\nCommands:")
    print("  f <speed>  - Forward (e.g., 'f 50' for 50% forward)")
    print("  r <speed>  - Reverse (e.g., 'r 30' for 30% reverse)")
    print("  s          - Stop (coast)")
    print("  b          - Brake (active)")
    print("  q          - Quit")
    print("="*60)

    motor = MotorController()

    try:
        while True:
            cmd = input("\n> ").strip().lower().split()

            if not cmd:
                continue

            if cmd[0] == 'q':
                break

            elif cmd[0] == 'f':
                speed = int(cmd[1]) if len(cmd) > 1 else 50
                motor.forward(speed)

            elif cmd[0] == 'r':
                speed = int(cmd[1]) if len(cmd) > 1 else 50
                motor.reverse(speed)

            elif cmd[0] == 's':
                motor.stop()

            elif cmd[0] == 'b':
                motor.brake()

            else:
                print("❌ Unknown command")

            # Show current status
            status = motor.get_status()
            print(f"   Status: {status['direction']} at {status['speed']}%")

    except KeyboardInterrupt:
        print("\n\n⏹️  Manual control interrupted")

    except Exception as e:
        print(f"\n❌ Error: {e}")

    finally:
        motor.cleanup()


def sequence_rest_dominant():
    """
    Rest-dominant tremor simulation
    Frequency range: 4-6 Hz (within clinical rest band: 3-7 Hz)
    Duration: 120 seconds (4 segments × 30s each)

    Returns:
        list: [(frequency_Hz, amplitude_%, duration_s), ...]
    """
    segments = [
        (4.0, 40, 30),  # Low rest frequency
        (5.0, 45, 30),  # Mid rest frequency
        (6.0, 50, 30),  # High rest frequency (near overlap)
        (5.0, 42, 30),  # Back to mid (simulate variation)
    ]
    return segments


def sequence_essential_dominant():
    """
    Essential tremor simulation
    Frequency range: 8-10 Hz (within clinical essential band: 6-12 Hz)
    Duration: 120 seconds (4 segments × 30s each)

    Returns:
        list: [(frequency_Hz, amplitude_%, duration_s), ...]
    """
    segments = [
        (8.0, 45, 30),  # Low essential frequency
        (9.0, 50, 30),  # Mid essential frequency
        (10.0, 55, 30), # High essential frequency
        (9.0, 48, 30),  # Back to mid (simulate variation)
    ]
    return segments


def run_tremor_sequence(sequence_type="rest"):
    """
    Run automated tremor simulation sequence

    Args:
        sequence_type: "rest" or "essential"
    """
    print("\n" + "="*60)
    print("Tremor Simulation Sequence")
    print("="*60)

    # Select sequence
    if sequence_type == "rest":
        segments = sequence_rest_dominant()
        print("Sequence: REST-DOMINANT TREMOR")
        print("Frequency range: 4-6 Hz (clinical rest band: 3-7 Hz)")
    elif sequence_type == "essential":
        segments = sequence_essential_dominant()
        print("Sequence: ESSENTIAL TREMOR")
        print("Frequency range: 8-10 Hz (clinical essential band: 6-12 Hz)")
    else:
        print(f"❌ Unknown sequence type: {sequence_type}")
        return

    print(f"Total duration: {sum(s[2] for s in segments)} seconds")
    print(f"Segments: {len(segments)}")
    print("="*60)

    motor = MotorController()

    try:
        for i, (freq, amplitude, duration) in enumerate(segments, 1):
            period = 1.0 / freq
            half_period = period / 2.0

            print(f"\n📍 Segment {i}/{len(segments)}")
            print(f"   Frequency: {freq} Hz")
            print(f"   Amplitude: {amplitude}%")
            print(f"   Duration: {duration}s")
            print(f"   Period: {period:.3f}s ({half_period:.3f}s per direction)")

            # Run oscillation for specified duration
            end_time = time.time() + duration
            cycles = 0

            while time.time() < end_time:
                motor.forward(amplitude)
                time.sleep(half_period)
                motor.reverse(amplitude)
                time.sleep(half_period)
                cycles += 1

            print(f"   ✅ Completed {cycles} cycles ({cycles/duration:.2f} Hz measured)")
            motor.stop()
            time.sleep(0.5)  # Brief pause between segments

        print("\n" + "="*60)
        print("✅ Tremor sequence complete!")
        print("="*60)

    except KeyboardInterrupt:
        print("\n\n⏹️  Sequence interrupted by user")

    finally:
        motor.cleanup()


def tremor_menu():
    """Interactive menu for tremor simulation sequences"""
    print("\n" + "="*60)
    print("Tremor Simulation Menu")
    print("="*60)
    print("\nAvailable sequences:")
    print("  1. Rest-Dominant Tremor (4-6 Hz, 120s)")
    print("  2. Essential Tremor (8-10 Hz, 120s)")
    print("  3. Manual motor control")
    print("  4. Hardware test sequence")
    print("  q. Quit")
    print("="*60)

    while True:
        choice = input("\nSelect option (1-4, q): ").strip().lower()

        if choice == 'q':
            print("👋 Goodbye!")
            break
        elif choice == '1':
            print("\n🎯 Starting REST-DOMINANT tremor sequence...")
            print("⚠️  Make sure ESP32 is recording before starting!")
            input("Press Enter when ready to start...")
            run_tremor_sequence("rest")
            break
        elif choice == '2':
            print("\n🎯 Starting ESSENTIAL tremor sequence...")
            print("⚠️  Make sure ESP32 is recording before starting!")
            input("Press Enter when ready to start...")
            run_tremor_sequence("essential")
            break
        elif choice == '3':
            manual_control()
            break
        elif choice == '4':
            run_test_sequence()
            break
        else:
            print("❌ Invalid choice. Please select 1-4 or q.")


if __name__ == "__main__":
    import sys

    print("\n╔════════════════════════════════════╗")
    print("║ L298N Motor Controller             ║")
    print("║ Raspberry Pi 4                     ║")
    print("║ Tremor Simulation System           ║")
    print("╚════════════════════════════════════╝")

    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            run_test_sequence()
        elif sys.argv[1] == "rest":
            run_tremor_sequence("rest")
        elif sys.argv[1] == "essential":
            run_tremor_sequence("essential")
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Usage: python3 motor_control.py [test|rest|essential]")
    else:
        tremor_menu()
