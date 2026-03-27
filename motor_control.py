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

    Physics: F = m*ω²*r (centrifugal force)
    - ω (angular velocity) proportional to motor RPM
    - RPM controlled by PWM duty cycle
    - Higher PWM → Higher RPM → Higher centrifugal force → Higher amplitude
    - We modulate PWM at the desired frequency to create oscillating tremor

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
        # Set motor direction to forward (constant)
        GPIO.output(motor.in1_pin, GPIO.HIGH)
        GPIO.output(motor.in2_pin, GPIO.LOW)

        for i, (freq, amplitude, duration) in enumerate(segments, 1):
            period = 1.0 / freq
            half_period = period / 2.0

            # PWM modulation range: from minimum speed to target amplitude
            min_pwm = 15  # Minimum to keep motor spinning
            max_pwm = amplitude

            print(f"\n📍 Segment {i}/{len(segments)}")
            print(f"   Frequency: {freq} Hz")
            print(f"   Amplitude: {max_pwm}% PWM (Force ∝ PWM²)")
            print(f"   Duration: {duration}s")
            print(f"   Period: {period:.3f}s ({half_period:.3f}s per half-cycle)")

            # Run PWM oscillation for specified duration
            end_time = time.time() + duration
            cycles = 0

            while time.time() < end_time:
                # Increase PWM to max (high centrifugal force)
                motor.set_speed(max_pwm)
                time.sleep(half_period)

                # Decrease PWM to min (low centrifugal force)
                motor.set_speed(min_pwm)
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


def run_tremor_with_validation():
    """
    Run tremor simulation and validate with PSD analysis

    Flow:
    1. Ask user for frequency range (rest: 4-6 Hz or essential: 8-10 Hz)
    2. Run motor simulation
    3. Ask user for sensor data CSV file
    4. Perform PSD analysis
    5. Check if power density peaks fall within expected frequency range
    6. Display results with pass/fail and deviation if failed
    """
    import csv
    import numpy as np
    import matplotlib.pyplot as plt
    from scipy import signal
    import os

    print("\n" + "="*70)
    print("TREMOR SIMULATION WITH DATA VALIDATION")
    print("="*70)

    # Step 1: Select frequency range
    print("\nSelect tremor type to simulate:")
    print("  1. REST tremor (4-6 Hz)")
    print("  2. ESSENTIAL tremor (8-10 Hz)")
    print("  3. CUSTOM range")

    choice = input("\nEnter choice (1-3): ").strip()

    if choice == '1':
        freq_min, freq_max = 4.0, 6.0
        tremor_type = "REST"
        # Use middle frequency for simulation
        target_freq = 5.0
        pwm_amplitude = 45
    elif choice == '2':
        freq_min, freq_max = 8.0, 10.0
        tremor_type = "ESSENTIAL"
        target_freq = 9.0
        pwm_amplitude = 50
    elif choice == '3':
        freq_min = float(input("Enter minimum frequency (Hz): "))
        freq_max = float(input("Enter maximum frequency (Hz): "))
        tremor_type = "CUSTOM"
        target_freq = (freq_min + freq_max) / 2
        pwm_amplitude = 50
    else:
        print("❌ Invalid choice")
        return

    print(f"\n✅ Selected: {tremor_type} tremor ({freq_min}-{freq_max} Hz)")
    print(f"   Target frequency: {target_freq} Hz")
    print(f"   PWM amplitude: {pwm_amplitude}%")

    # Step 2: Run motor
    print("\n⚠️  Make sure ESP32 is recording BEFORE starting!")
    input("Press Enter when ready to start motor...")

    duration = 120  # seconds
    motor = MotorController()

    try:
        # Set motor direction to forward (constant)
        GPIO.output(motor.in1_pin, GPIO.HIGH)
        GPIO.output(motor.in2_pin, GPIO.LOW)

        period = 1.0 / target_freq
        half_period = period / 2.0
        min_pwm = 15
        max_pwm = pwm_amplitude

        print(f"\n▶️  Running motor at {target_freq} Hz for {duration}s...")
        print(f"   PWM range: {min_pwm}-{max_pwm}%")

        end_time = time.time() + duration
        cycles = 0

        while time.time() < end_time:
            motor.set_speed(max_pwm)
            time.sleep(half_period)
            motor.set_speed(min_pwm)
            time.sleep(half_period)
            cycles += 1

        actual_freq = cycles / duration
        print(f"✅ Motor run complete: {cycles} cycles ({actual_freq:.2f} Hz actual)")
        motor.stop()

    except KeyboardInterrupt:
        print("\n⏹️  Motor run interrupted")
        motor.stop()
        return
    finally:
        motor.cleanup()

    # Step 3: Load sensor data
    print("\n" + "="*70)
    print("DATA ANALYSIS")
    print("="*70)

    csv_file = input("\nEnter sensor data CSV filename: ").strip()

    if not os.path.exists(csv_file):
        print(f"❌ File not found: {csv_file}")
        return

    # Load CSV data
    print(f"📂 Loading {csv_file}...")
    timestamps = []
    accel_x = []

    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Timestamp', '').startswith('#'):
                    continue
                try:
                    timestamps.append(int(row['Timestamp']))
                    accel_x.append(float(row['Ax']))
                except (ValueError, KeyError):
                    continue

        print(f"✅ Loaded {len(accel_x)} samples")

    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return

    if len(accel_x) < 100:
        print("❌ Not enough data for analysis")
        return

    # Step 4: PSD Analysis
    print("\n📊 Performing Power Spectral Density (PSD) analysis...")

    # Convert to numpy array
    signal_data = np.array(accel_x)

    # Remove DC component
    signal_data = signal_data - np.mean(signal_data)

    # Sampling rate (from README: 100 Hz)
    fs = 100  # Hz

    # Compute PSD using Welch's method
    freqs, psd = signal.welch(signal_data, fs=fs, nperseg=1024)

    # Find frequency range of interest (0-15 Hz for tremor)
    freq_mask = (freqs >= 0) & (freqs <= 15)
    freqs_tremor = freqs[freq_mask]
    psd_tremor = psd[freq_mask]

    # Find peak frequency in the expected range
    range_mask = (freqs >= freq_min) & (freqs <= freq_max)
    freqs_in_range = freqs[range_mask]
    psd_in_range = psd[range_mask]

    # Find global peak in tremor range (0-15 Hz)
    peak_idx_global = np.argmax(psd_tremor)
    peak_freq_global = freqs_tremor[peak_idx_global]
    peak_power_global = psd_tremor[peak_idx_global]

    # Find peak in expected range
    if len(psd_in_range) > 0:
        peak_idx_in_range = np.argmax(psd_in_range)
        peak_freq_in_range = freqs_in_range[peak_idx_in_range]
        peak_power_in_range = psd_in_range[peak_idx_in_range]
    else:
        peak_freq_in_range = None
        peak_power_in_range = 0

    # Step 5: Validation
    print("\n" + "="*70)
    print("VALIDATION RESULTS")
    print("="*70)

    print(f"\nExpected range: {freq_min}-{freq_max} Hz")
    print(f"Global peak: {peak_freq_global:.2f} Hz (power: {peak_power_global:.2e})")

    # Check if global peak is in range
    in_range = (peak_freq_global >= freq_min) and (peak_freq_global <= freq_max)

    if in_range:
        print(f"\n✅ SUCCESS - Peak frequency {peak_freq_global:.2f} Hz is within range!")
        deviation = 0
    else:
        if peak_freq_global < freq_min:
            deviation = freq_min - peak_freq_global
            print(f"\n❌ FAILURE - Peak frequency {peak_freq_global:.2f} Hz is BELOW range")
            print(f"   Deviation: -{deviation:.2f} Hz (too low)")
        else:
            deviation = peak_freq_global - freq_max
            print(f"\n❌ FAILURE - Peak frequency {peak_freq_global:.2f} Hz is ABOVE range")
            print(f"   Deviation: +{deviation:.2f} Hz (too high)")

    # Step 6: Plot PSD
    print("\n📊 Generating PSD plot...")

    plt.figure(figsize=(12, 6))

    # Plot PSD
    plt.plot(freqs_tremor, psd_tremor, 'b-', linewidth=1.5, label='PSD')

    # Mark expected range
    plt.axvspan(freq_min, freq_max, alpha=0.3, color='green' if in_range else 'red',
                label=f'Expected range ({freq_min}-{freq_max} Hz)')

    # Mark peak
    plt.plot(peak_freq_global, peak_power_global, 'ro', markersize=10,
             label=f'Peak: {peak_freq_global:.2f} Hz')

    plt.xlabel('Frequency (Hz)', fontsize=12)
    plt.ylabel('Power Spectral Density', fontsize=12)
    plt.title(f'Tremor Validation - {tremor_type} ({freq_min}-{freq_max} Hz)\n' +
              ('✅ PASS' if in_range else f'❌ FAIL (deviation: {abs(deviation):.2f} Hz)'),
              fontsize=14, fontweight='bold')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xlim(0, 15)

    # Save plot
    plot_filename = f"tremor_validation_{tremor_type.lower()}.png"
    plt.savefig(plot_filename, dpi=150, bbox_inches='tight')
    print(f"✅ Plot saved: {plot_filename}")

    plt.show()

    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)


def tremor_menu():
    """Interactive menu for tremor simulation sequences"""
    print("\n" + "="*60)
    print("Tremor Simulation Menu")
    print("="*60)
    print("\nAvailable options:")
    print("  1. Rest-Dominant Tremor (4-6 Hz, 120s)")
    print("  2. Essential Tremor (8-10 Hz, 120s)")
    print("  3. Tremor with PSD Validation (recommended)")
    print("  4. Manual motor control")
    print("  5. Hardware test sequence")
    print("  q. Quit")
    print("="*60)

    while True:
        choice = input("\nSelect option (1-5, q): ").strip().lower()

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
            run_tremor_with_validation()
            break
        elif choice == '4':
            manual_control()
            break
        elif choice == '5':
            run_test_sequence()
            break
        else:
            print("❌ Invalid choice. Please select 1-5 or q.")


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
        elif sys.argv[1] == "validate":
            run_tremor_with_validation()
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Usage: python3 motor_control.py [test|rest|essential|validate]")
    else:
        tremor_menu()
