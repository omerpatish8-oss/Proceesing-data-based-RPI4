#!/usr/bin/env python3
"""
L298N Motor Driver Control for Raspberry Pi 4

PWM Speed Control - Classic Duty Cycle Method:
  Duty Cycle controls average voltage to motor.
  Higher duty cycle = higher voltage = higher RPM.

  Example (12V motor):
    20% duty cycle = 2.4V avg  -> ~125 RPM  -> ~2.1 Hz
    40% duty cycle = 4.8V avg  -> ~250 RPM  -> ~4.2 Hz
    60% duty cycle = 7.2V avg  -> ~375 RPM  -> ~6.3 Hz
    80% duty cycle = 9.6V avg  -> ~500 RPM  -> ~8.3 Hz
   100% duty cycle = 12V  avg  -> ~625 RPM  -> ~10.4 Hz

Hardware connections:
  ENA (PWM) -> GPIO18
  IN1       -> GPIO23
  IN2       -> GPIO24
  OUT1/OUT2 -> Motor terminals
  12V power -> L298N power input
"""

import RPi.GPIO as GPIO
import time

# GPIO Pin Configuration
ENA_PIN = 18  # PWM control (speed via duty cycle)
IN1_PIN = 23  # Direction control 1
IN2_PIN = 24  # Direction control 2

# PWM Configuration
PWM_FREQUENCY = 1000  # 1 kHz carrier frequency (not motor speed!)

# Motor Specifications (12V DC Gearbox Motor with eccentric mass)
MAX_RPM = 625           # Maximum RPM at 12V (100% duty cycle)
MAX_HZ = MAX_RPM / 60   # Maximum rotations per second = 10.42 Hz
ECCENTRIC_MASS_G = 38   # Eccentric mass in grams
MIN_DUTY_CYCLE = 15     # Minimum duty cycle for motor to start spinning


def duty_cycle_to_rpm(duty_cycle):
    """
    Convert duty cycle percentage to estimated RPM and Hz

    Duty Cycle -> Average Voltage -> RPM (linear approximation)
    RPM = (duty_cycle / 100) * MAX_RPM

    Args:
        duty_cycle: 0-100 (percentage)

    Returns:
        tuple: (rpm, hz)
    """
    rpm = (duty_cycle / 100.0) * MAX_RPM
    hz = rpm / 60.0
    return rpm, hz


def hz_to_duty_cycle(target_hz):
    """
    Convert target Hz to required duty cycle

    duty_cycle = (target_hz / MAX_HZ) * 100

    Args:
        target_hz: desired rotations per second

    Returns:
        duty_cycle percentage (clamped to valid range)
    """
    if target_hz <= 0:
        return 0
    if target_hz > MAX_HZ:
        print(f"Warning: {target_hz:.1f} Hz exceeds max {MAX_HZ:.1f} Hz, clamping")
        target_hz = MAX_HZ

    duty = (target_hz / MAX_HZ) * 100.0
    return max(0, min(100, duty))


class MotorController:
    """
    L298N Motor Driver Controller

    Speed control via PWM duty cycle:
      duty_cycle = 0%   -> motor off
      duty_cycle = 50%  -> motor at half speed (~312 RPM)
      duty_cycle = 100% -> motor at full speed (~625 RPM)
    """

    def __init__(self, ena_pin=ENA_PIN, in1_pin=IN1_PIN, in2_pin=IN2_PIN,
                 pwm_freq=PWM_FREQUENCY):
        self.ena_pin = ena_pin
        self.in1_pin = in1_pin
        self.in2_pin = in2_pin
        self.pwm_freq = pwm_freq
        self.pwm = None
        self.current_duty_cycle = 0
        self.current_direction = "STOPPED"

        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        GPIO.setup(self.ena_pin, GPIO.OUT)
        GPIO.setup(self.in1_pin, GPIO.OUT)
        GPIO.setup(self.in2_pin, GPIO.OUT)

        # Initialize PWM on ENA pin
        self.pwm = GPIO.PWM(self.ena_pin, self.pwm_freq)
        self.pwm.start(0)  # Start with 0% duty cycle (motor off)

        self.stop()

        print(f"Motor controller initialized")
        print(f"  ENA (PWM): GPIO{self.ena_pin}")
        print(f"  IN1: GPIO{self.in1_pin}, IN2: GPIO{self.in2_pin}")
        print(f"  PWM carrier: {self.pwm_freq} Hz")
        print(f"  Motor max: {MAX_RPM} RPM ({MAX_HZ:.1f} Hz)")

    def set_duty_cycle(self, duty_cycle):
        """
        Set motor speed by duty cycle (0-100%)

        This is the core control method:
          duty_cycle% of the time -> signal HIGH (voltage ON)
          remaining% of the time  -> signal LOW (voltage OFF)
          Motor sees average voltage = duty_cycle% * 12V

        Args:
            duty_cycle: 0-100 (percentage)
        """
        duty_cycle = max(0, min(100, duty_cycle))
        self.current_duty_cycle = duty_cycle

        if self.pwm:
            self.pwm.ChangeDutyCycle(duty_cycle)

    def forward(self, duty_cycle=50):
        """Run motor forward at given duty cycle"""
        GPIO.output(self.in1_pin, GPIO.HIGH)
        GPIO.output(self.in2_pin, GPIO.LOW)
        self.set_duty_cycle(duty_cycle)
        self.current_direction = "FORWARD"
        rpm, hz = duty_cycle_to_rpm(duty_cycle)
        print(f"  Motor FORWARD: {duty_cycle}% duty cycle -> {rpm:.0f} RPM ({hz:.1f} Hz)")

    def reverse(self, duty_cycle=50):
        """Run motor in reverse at given duty cycle"""
        GPIO.output(self.in1_pin, GPIO.LOW)
        GPIO.output(self.in2_pin, GPIO.HIGH)
        self.set_duty_cycle(duty_cycle)
        self.current_direction = "REVERSE"
        rpm, hz = duty_cycle_to_rpm(duty_cycle)
        print(f"  Motor REVERSE: {duty_cycle}% duty cycle -> {rpm:.0f} RPM ({hz:.1f} Hz)")

    def stop(self):
        """Stop motor (coast to stop)"""
        GPIO.output(self.in1_pin, GPIO.LOW)
        GPIO.output(self.in2_pin, GPIO.LOW)
        self.set_duty_cycle(0)
        self.current_direction = "STOPPED"

    def brake(self):
        """Active brake (quick stop)"""
        GPIO.output(self.in1_pin, GPIO.HIGH)
        GPIO.output(self.in2_pin, GPIO.HIGH)
        self.set_duty_cycle(100)
        self.current_direction = "BRAKING"

    def get_status(self):
        """Get current motor status"""
        rpm, hz = duty_cycle_to_rpm(self.current_duty_cycle)
        return {
            'direction': self.current_direction,
            'duty_cycle': self.current_duty_cycle,
            'rpm': rpm,
            'hz': hz
        }

    def cleanup(self):
        """Cleanup GPIO and stop motor"""
        self.stop()
        if self.pwm:
            self.pwm.stop()
        GPIO.cleanup([self.ena_pin, self.in1_pin, self.in2_pin])
        print("Motor controller cleanup complete")


# ============================================================
# Interactive Control Functions
# ============================================================

def duty_cycle_control():
    """
    Classic duty cycle control mode

    User sets duty cycle directly -> controls motor RPM
    """
    print("\n" + "="*60)
    print("Duty Cycle Control Mode")
    print("="*60)
    print(f"\nMotor: {MAX_RPM} RPM max, {ECCENTRIC_MASS_G}g eccentric mass")
    print(f"\nDuty cycle controls average voltage to motor:")
    print(f"  0%   -> 0V    -> motor off")
    print(f"  25%  -> 3.0V  -> ~{MAX_RPM*0.25:.0f} RPM ({MAX_HZ*0.25:.1f} Hz)")
    print(f"  50%  -> 6.0V  -> ~{MAX_RPM*0.50:.0f} RPM ({MAX_HZ*0.50:.1f} Hz)")
    print(f"  75%  -> 9.0V  -> ~{MAX_RPM*0.75:.0f} RPM ({MAX_HZ*0.75:.1f} Hz)")
    print(f"  100% -> 12.0V -> ~{MAX_RPM} RPM ({MAX_HZ:.1f} Hz)")
    print(f"\nCommands:")
    print(f"  <number>     - Set duty cycle (e.g. '38' for 38%)")
    print(f"  hz <value>   - Set by target Hz (e.g. 'hz 4')")
    print(f"  stop         - Stop motor")
    print(f"  quit         - Exit")
    print("="*60)

    motor = MotorController()

    try:
        # Set direction forward
        GPIO.output(motor.in1_pin, GPIO.HIGH)
        GPIO.output(motor.in2_pin, GPIO.LOW)

        while True:
            cmd = input("\nDuty Cycle > ").strip().lower().split()

            if not cmd:
                continue

            if cmd[0] in ['q', 'quit', 'exit']:
                break

            elif cmd[0] in ['stop', 's']:
                motor.stop()
                print("  Motor stopped")

            elif cmd[0] == 'hz':
                if len(cmd) < 2:
                    print("Usage: hz <value>")
                    continue
                target_hz = float(cmd[1])
                duty = hz_to_duty_cycle(target_hz)
                motor.set_duty_cycle(duty)
                rpm, actual_hz = duty_cycle_to_rpm(duty)
                print(f"  Target: {target_hz} Hz")
                print(f"  Duty Cycle: {duty:.1f}%")
                print(f"  Avg Voltage: {duty/100*12:.1f}V")
                print(f"  Expected: {rpm:.0f} RPM ({actual_hz:.1f} Hz)")

            else:
                try:
                    duty = float(cmd[0])
                    if duty < 0 or duty > 100:
                        print("  Duty cycle must be 0-100%")
                        continue
                    motor.set_duty_cycle(duty)
                    rpm, hz = duty_cycle_to_rpm(duty)
                    print(f"  Duty Cycle: {duty:.1f}%")
                    print(f"  Avg Voltage: {duty/100*12:.1f}V")
                    print(f"  Expected: {rpm:.0f} RPM ({hz:.1f} Hz)")
                except ValueError:
                    print("  Enter a number (0-100) or command (hz, stop, quit)")

    except KeyboardInterrupt:
        print("\n\nInterrupted")

    finally:
        motor.cleanup()


def custom_sequence():
    """
    Run a custom sequence of duty cycles

    User defines steps: duty_cycle, duration_seconds
    Motor runs at each duty cycle for the specified duration
    """
    print("\n" + "="*60)
    print("Custom Duty Cycle Sequence")
    print("="*60)
    print(f"\nMotor: {MAX_RPM} RPM max ({MAX_HZ:.1f} Hz)")
    print(f"\nReference table:")
    print(f"  Duty%  Voltage  RPM   Hz")
    print(f"  ─────  ───────  ────  ────")
    for d in [20, 30, 40, 50, 60, 70, 80, 90, 100]:
        rpm, hz = duty_cycle_to_rpm(d)
        print(f"  {d:3d}%   {d/100*12:5.1f}V   {rpm:4.0f}  {hz:4.1f}")
    print(f"\nEnter steps as: duty_cycle,seconds")
    print(f"Example:")
    print(f"  38,50    <- 38% duty cycle for 50 seconds (4 Hz)")
    print(f"  58,60    <- 58% duty cycle for 60 seconds (6 Hz)")
    print(f"  48,10    <- 48% duty cycle for 10 seconds (5 Hz)")
    print(f"\nCommands: 'show', 'clear', 'run', 'quit'")
    print("="*60)

    sequence = []

    while True:
        line = input("\n> ").strip().lower()

        if line == 'quit':
            return

        if line == 'run':
            if not sequence:
                print("No sequence defined!")
                continue
            break

        if line == 'clear':
            sequence = []
            print("Sequence cleared")
            continue

        if line == 'show':
            if sequence:
                total_time = sum(dur for _, dur in sequence)
                print(f"\nCurrent sequence ({total_time}s total):")
                for i, (duty, dur) in enumerate(sequence, 1):
                    rpm, hz = duty_cycle_to_rpm(duty)
                    print(f"  {i}. {duty}% duty -> {rpm:.0f} RPM ({hz:.1f} Hz) for {dur}s")
            else:
                print("Sequence is empty")
            continue

        try:
            parts = line.split(',')
            duty = float(parts[0])
            duration = float(parts[1]) if len(parts) > 1 else 10

            if duty < 0 or duty > 100:
                print("Duty cycle must be 0-100%")
                continue

            sequence.append((duty, duration))
            rpm, hz = duty_cycle_to_rpm(duty)
            print(f"  Added: {duty}% duty cycle ({rpm:.0f} RPM, {hz:.1f} Hz) for {duration}s")

        except (ValueError, IndexError):
            print("Invalid format. Use: duty_cycle,seconds (e.g., 38,50)")

    # Run the sequence
    total_time = sum(dur for _, dur in sequence)
    print("\n" + "="*60)
    print(f"Running sequence ({total_time}s total)...")
    print("="*60)

    motor = MotorController()

    try:
        GPIO.output(motor.in1_pin, GPIO.HIGH)
        GPIO.output(motor.in2_pin, GPIO.LOW)

        for i, (duty, duration) in enumerate(sequence, 1):
            rpm, hz = duty_cycle_to_rpm(duty)
            voltage = duty / 100.0 * 12

            print(f"\nStep {i}/{len(sequence)}")
            print(f"  Duty Cycle: {duty}%")
            print(f"  Voltage:    {voltage:.1f}V")
            print(f"  Speed:      {rpm:.0f} RPM ({hz:.1f} Hz)")
            print(f"  Duration:   {duration}s")

            motor.set_duty_cycle(duty)
            time.sleep(duration)

        motor.stop()
        print("\n" + "="*60)
        print("Sequence complete!")
        print("="*60)

    except KeyboardInterrupt:
        print("\n\nSequence interrupted")

    finally:
        motor.stop()
        motor.cleanup()


def run_test_sequence():
    """Run a basic test to verify motor operation"""
    print("\n" + "="*60)
    print("Motor Test Sequence")
    print("="*60)

    motor = MotorController()

    try:
        print("\n1. Forward 30% duty cycle (2s)...")
        motor.forward(30)
        time.sleep(2)

        print("\n2. Forward 60% duty cycle (2s)...")
        motor.set_duty_cycle(60)
        time.sleep(2)

        print("\n3. Forward 100% duty cycle (2s)...")
        motor.forward(100)
        time.sleep(2)

        print("\n4. Brake (1s)...")
        motor.brake()
        time.sleep(1)

        print("\n5. Stop")
        motor.stop()
        time.sleep(1)

        print("\nTest complete!")

    except KeyboardInterrupt:
        print("\n\nTest interrupted")

    finally:
        motor.cleanup()


def run_tremor_with_validation():
    """
    Run tremor simulation using constant duty cycle and validate with PSD

    Flow:
    1. User selects target frequency or duty cycle
    2. Motor runs at constant duty cycle (= constant RPM)
    3. Load recorded CSV data
    4. PSD analysis to verify peak matches expected frequency
    """
    import numpy as np
    import matplotlib.pyplot as plt
    from scipy import signal
    import os

    print("\n" + "="*70)
    print("TREMOR SIMULATION WITH VALIDATION")
    print("="*70)

    print(f"\nMotor: {MAX_RPM} RPM max ({MAX_HZ:.1f} Hz)")
    print(f"\nSelect input method:")
    print(f"  1. Enter target Hz (auto-calculate duty cycle)")
    print(f"  2. Enter duty cycle directly")

    method = input("\nChoice (1-2): ").strip()

    if method == '1':
        target_hz = float(input("Enter target Hz: "))
        duty = hz_to_duty_cycle(target_hz)
        freq_min = target_hz * 0.8
        freq_max = target_hz * 1.2
    elif method == '2':
        duty = float(input("Enter duty cycle (0-100%): "))
        _, target_hz = duty_cycle_to_rpm(duty)
        freq_min = target_hz * 0.8
        freq_max = target_hz * 1.2
    else:
        print("Invalid choice")
        return

    rpm, hz = duty_cycle_to_rpm(duty)
    print(f"\nSettings:")
    print(f"  Duty Cycle:  {duty:.1f}%")
    print(f"  Avg Voltage: {duty/100*12:.1f}V")
    print(f"  Expected:    {rpm:.0f} RPM ({hz:.1f} Hz)")
    print(f"  Valid range: {freq_min:.1f}-{freq_max:.1f} Hz")

    duration = int(input("\nDuration in seconds (default 120): ").strip() or "120")

    print("\nMake sure ESP32 is recording BEFORE starting!")
    input("Press Enter when ready to start motor...")

    # Run motor at constant duty cycle
    motor = MotorController()

    try:
        GPIO.output(motor.in1_pin, GPIO.HIGH)
        GPIO.output(motor.in2_pin, GPIO.LOW)

        print(f"\nRunning motor at {duty:.1f}% duty cycle for {duration}s...")
        motor.set_duty_cycle(duty)
        time.sleep(duration)

        motor.stop()
        print(f"Motor run complete")

    except KeyboardInterrupt:
        print("\nMotor run interrupted")
        motor.stop()
        return
    finally:
        motor.cleanup()

    # Load and analyze sensor data
    print("\n" + "="*70)
    print("DATA ANALYSIS")
    print("="*70)

    csv_file = input("\nEnter sensor data CSV filename: ").strip()

    if not os.path.exists(csv_file):
        print(f"File not found: {csv_file}")
        return

    print(f"Loading {csv_file}...")
    accel_x = []

    try:
        with open(csv_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('Timestamp'):
                    continue
                parts = line.split(',')
                if len(parts) >= 2:
                    accel_x.append(float(parts[1]))

        print(f"Loaded {len(accel_x)} samples")
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return

    if len(accel_x) < 100:
        print("Not enough data for analysis")
        return

    # PSD Analysis
    signal_data = np.array(accel_x)
    signal_data = signal_data - np.mean(signal_data)

    fs = 100  # Sample rate (Hz)
    freqs, psd = signal.welch(signal_data, fs=fs, nperseg=min(len(signal_data), 1024))

    # Find peak in tremor range
    tremor_mask = (freqs >= 1) & (freqs <= 15)
    peak_idx = np.argmax(psd[tremor_mask])
    peak_freq = freqs[tremor_mask][peak_idx]
    peak_power = psd[tremor_mask][peak_idx]

    # Validation
    in_range = freq_min <= peak_freq <= freq_max

    print(f"\n" + "="*70)
    print("VALIDATION RESULTS")
    print("="*70)
    print(f"\n  Input (Motor):")
    print(f"    Duty Cycle:     {duty:.1f}%")
    print(f"    Expected Freq:  {hz:.1f} Hz ({rpm:.0f} RPM)")
    print(f"    Valid Range:    {freq_min:.1f}-{freq_max:.1f} Hz")
    print(f"\n  Output (Sensor):")
    print(f"    Measured Freq:  {peak_freq:.2f} Hz")
    print(f"    Peak Power:     {peak_power:.2e}")
    print(f"\n  Result: {'PASS' if in_range else 'FAIL'}")
    if not in_range:
        if peak_freq < freq_min:
            print(f"    Deviation: {freq_min - peak_freq:.2f} Hz below range")
        else:
            print(f"    Deviation: {peak_freq - freq_max:.2f} Hz above range")
    print("="*70)

    # Plot
    plt.figure(figsize=(12, 6))
    plt.plot(freqs[tremor_mask], 10*np.log10(psd[tremor_mask] + 1e-12),
             'b-', linewidth=1.5)
    plt.axvspan(freq_min, freq_max, alpha=0.3,
                color='green' if in_range else 'red',
                label=f'Expected ({freq_min:.1f}-{freq_max:.1f} Hz)')
    plt.plot(peak_freq, 10*np.log10(peak_power + 1e-12), 'ro',
             markersize=10, label=f'Measured: {peak_freq:.2f} Hz')
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Power (dB)')
    plt.title(f'Validation: {duty:.0f}% duty cycle -> {hz:.1f} Hz expected | '
              f'{"PASS" if in_range else "FAIL"}')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(f"validation_{duty:.0f}pct.png", dpi=150, bbox_inches='tight')
    print(f"\nPlot saved: validation_{duty:.0f}pct.png")
    plt.show()


# ============================================================
# Main Menu
# ============================================================

def main_menu():
    """Interactive menu"""
    print("\n" + "="*60)
    print("Motor Controller")
    print("="*60)
    print(f"\nMotor: {MAX_RPM} RPM max ({MAX_HZ:.1f} Hz), {ECCENTRIC_MASS_G}g mass")
    print(f"\nDuty Cycle -> Speed Reference:")
    print(f"  38% -> ~4 Hz    58% -> ~6 Hz    77% -> ~8 Hz    96% -> ~10 Hz")
    print(f"\nOptions:")
    print(f"  1. Duty Cycle Control (interactive)")
    print(f"  2. Custom Sequence (multi-step)")
    print(f"  3. Tremor Simulation + Validation")
    print(f"  4. Motor Test")
    print(f"  q. Quit")
    print("="*60)

    while True:
        choice = input("\nSelect (1-4, q): ").strip().lower()

        if choice == 'q':
            print("Goodbye!")
            break
        elif choice == '1':
            duty_cycle_control()
            break
        elif choice == '2':
            custom_sequence()
            break
        elif choice == '3':
            run_tremor_with_validation()
            break
        elif choice == '4':
            run_test_sequence()
            break
        else:
            print("Invalid choice. Select 1-4 or q.")


if __name__ == "__main__":
    main_menu()
