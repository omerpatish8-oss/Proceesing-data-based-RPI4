#!/usr/bin/env python3
"""
L298N Motor Driver Control for Raspberry Pi 4

Single mode: Duty Cycle Control
  - Set duty cycle -> motor runs at that speed
  - Change duty cycle anytime during operation
  - Motor keeps running until you stop it or quit

  Duty Cycle -> Average Voltage -> RPM (linear approximation):
    20% -> 2.4V  -> ~125 RPM  -> ~2.1 Hz
    40% -> 4.8V  -> ~250 RPM  -> ~4.2 Hz
    60% -> 7.2V  -> ~375 RPM  -> ~6.3 Hz
    80% -> 9.6V  -> ~500 RPM  -> ~8.3 Hz
   100% -> 12V   -> ~625 RPM  -> ~10.4 Hz

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
PWM_FREQUENCY = 100   # 100 Hz — reliable range for RPi.GPIO software PWM on RPi4
                      # (1 kHz was too fast: software PWM needs ~0.5ms toggle but Linux
                      #  scheduling jitter is 1-10ms, producing a distorted/absent signal)

# Motor Specifications (12V DC Gearbox Motor with eccentric mass)
MAX_RPM = 625           # Maximum RPM at 12V (100% duty cycle)
MAX_HZ = MAX_RPM / 60   # Maximum rotations per second = 10.42 Hz
ECCENTRIC_MASS_G = 40   # Eccentric mass in grams
MIN_DUTY_CYCLE = 15     # Minimum duty cycle for motor to start spinning


def duty_cycle_to_rpm(duty_cycle):
    """Convert duty cycle (0-100%) to RPM and Hz"""
    rpm = (duty_cycle / 100.0) * MAX_RPM
    hz = rpm / 60.0
    return rpm, hz


def hz_to_duty_cycle(target_hz):
    """Convert target Hz to required duty cycle (0-100%)"""
    if target_hz <= 0:
        return 0
    if target_hz > MAX_HZ:
        print(f"Warning: {target_hz:.1f} Hz exceeds max {MAX_HZ:.1f} Hz, clamping")
        target_hz = MAX_HZ
    return (target_hz / MAX_HZ) * 100.0


class MotorController:
    """L298N Motor Driver - duty cycle controls speed"""

    def __init__(self):
        self.pwm = None
        self.current_duty_cycle = 0

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(True)   # temporary: show all GPIO warnings to diagnose motor issue

        GPIO.setup(ENA_PIN, GPIO.OUT)
        GPIO.setup(IN1_PIN, GPIO.OUT)
        GPIO.setup(IN2_PIN, GPIO.OUT)

        # Initialize PWM
        self.pwm = GPIO.PWM(ENA_PIN, PWM_FREQUENCY)
        self.pwm.start(0)

        # Motor off
        GPIO.output(IN1_PIN, GPIO.LOW)
        GPIO.output(IN2_PIN, GPIO.LOW)

        print(f"Motor initialized (GPIO{ENA_PIN}, carrier {PWM_FREQUENCY} Hz)")
        print(f"Motor max: {MAX_RPM} RPM ({MAX_HZ:.1f} Hz)")

    def set_duty_cycle(self, duty_cycle):
        """Set duty cycle (0-100%). Direction must be set separately."""
        duty_cycle = max(0, min(100, duty_cycle))
        self.current_duty_cycle = duty_cycle
        if self.pwm:
            self.pwm.ChangeDutyCycle(duty_cycle)

    def start_forward(self):
        """Set direction to forward"""
        GPIO.output(IN1_PIN, GPIO.HIGH)
        GPIO.output(IN2_PIN, GPIO.LOW)

    def stop(self):
        """Stop motor"""
        GPIO.output(IN1_PIN, GPIO.LOW)
        GPIO.output(IN2_PIN, GPIO.LOW)
        self.set_duty_cycle(0)

    def cleanup(self):
        """Stop motor and release GPIO"""
        self.stop()
        if self.pwm:
            self.pwm.stop()
        GPIO.cleanup([ENA_PIN, IN1_PIN, IN2_PIN])
        print("Motor cleanup done")


def main():
    """
    Duty Cycle Control

    Run the script -> set a duty cycle -> motor runs.
    Change the duty cycle anytime, or leave it constant until done.
    """
    print("\n" + "=" * 60)
    print("  MOTOR CONTROL - Duty Cycle")
    print("=" * 60)
    print(f"\n  Motor: {MAX_RPM} RPM max ({MAX_HZ:.1f} Hz), {ECCENTRIC_MASS_G}g mass")
    print(f"\n  Duty%  Voltage  RPM    Hz")
    print(f"  ─────  ───────  ─────  ────")
    for d in [20, 30, 40, 50, 60, 70, 80, 90, 100]:
        rpm, hz = duty_cycle_to_rpm(d)
        print(f"  {d:3d}%   {d/100*12:5.1f}V   {rpm:5.0f}  {hz:4.1f}")
    print(f"\n  Commands:")
    print(f"    <number>    Set duty cycle %  (e.g. 50)")
    print(f"    hz <value>  Set by frequency  (e.g. hz 4)")
    print(f"    stop        Stop motor (duty cycle = 0)")
    print(f"    quit        Stop motor and exit")
    print("=" * 60)

    motor = MotorController()
    motor.start_forward()

    try:
        while True:
            try:
                cmd = input("\nDuty Cycle > ").strip().lower().split()
            except EOFError:
                break

            if not cmd:
                # Show current status
                rpm, hz = duty_cycle_to_rpm(motor.current_duty_cycle)
                print(f"  Current: {motor.current_duty_cycle:.1f}% "
                      f"-> {rpm:.0f} RPM ({hz:.1f} Hz)")
                continue

            if cmd[0] in ('q', 'quit', 'exit'):
                break

            elif cmd[0] in ('stop', 's'):
                motor.set_duty_cycle(0)
                print("  Motor stopped (0% duty cycle)")

            elif cmd[0] == 'hz':
                if len(cmd) < 2:
                    print("  Usage: hz <value>  (e.g. hz 4)")
                    continue
                try:
                    target_hz = float(cmd[1])
                    duty = hz_to_duty_cycle(target_hz)
                    motor.set_duty_cycle(duty)
                    rpm, actual_hz = duty_cycle_to_rpm(duty)
                    print(f"  Set: {duty:.1f}% -> {rpm:.0f} RPM ({actual_hz:.1f} Hz)")
                except ValueError:
                    print("  Invalid Hz value")

            else:
                try:
                    duty = float(cmd[0])
                    if duty < 0 or duty > 100:
                        print("  Duty cycle must be 0-100%")
                        continue
                    motor.set_duty_cycle(duty)
                    rpm, hz = duty_cycle_to_rpm(duty)
                    print(f"  Set: {duty:.1f}% -> {rpm:.0f} RPM ({hz:.1f} Hz)")
                except ValueError:
                    print("  Enter a number (0-100) or: hz, stop, quit")

    except KeyboardInterrupt:
        print("\n\nInterrupted")

    finally:
        motor.cleanup()


if __name__ == "__main__":
    main()
