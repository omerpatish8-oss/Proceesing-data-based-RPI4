#!/usr/bin/env python3
"""
System Manager - Orchestrates motor control, data recording, and offline analysis.

Architecture:
  - Main thread: user interface (set motor speed, start/stop)
  - Recorder thread: UART read loop (rpi_usb_recorder_v2.record_data)
  - Motor: hardware PWM via MotorController (no thread needed, PWM runs in HW)
  - Offline analyzer: launched after recording completes

Usage:
  python3 sys_manager.py
"""

import threading
import time
import sys
import subprocess

from motor_control import MotorController, hz_to_duty_cycle, duty_cycle_to_rpm
from rpi_usb_recorder_v2 import record_data, find_port


def run_recorder(port, done_event):
    """Recorder thread: runs UART read loop until ESP32 signals ALL_COMPLETE."""
    try:
        record_data(port)
    except Exception as e:
        print(f"\n[Recorder] Error: {e}")
    finally:
        done_event.set()


def main():
    print("\n" + "=" * 60)
    print("  SYSTEM MANAGER")
    print("  Motor Control + Recording + Offline Analysis")
    print("=" * 60)

    # ──────────────────────────────────────────────
    # Step 1: Setup motor
    # ──────────────────────────────────────────────
    print("\n[Step 1] Motor Setup")
    print("-" * 40)

    motor = MotorController()
    motor.start_forward()

    while True:
        cmd = input("\nSet motor speed (e.g. 'hz 5' or duty 0-100, 'skip' to skip): ").strip().lower()
        if cmd == 'skip':
            print("  Motor skipped (0% duty cycle)")
            break
        try:
            parts = cmd.split()
            if parts[0] == 'hz':
                target_hz = float(parts[1])
                duty = hz_to_duty_cycle(target_hz)
            else:
                duty = float(parts[0])

            motor.set_duty_cycle(duty)
            rpm, hz = duty_cycle_to_rpm(duty)
            print(f"  Motor set: {duty:.1f}% -> {rpm:.0f} RPM ({hz:.1f} Hz)")
            break
        except (ValueError, IndexError):
            print("  Invalid input. Examples: 'hz 5', '40', 'skip'")

    # ──────────────────────────────────────────────
    # Step 2: Find serial port
    # ──────────────────────────────────────────────
    print("\n[Step 2] Serial Port")
    print("-" * 40)

    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = find_port()
        if not port:
            port = '/dev/ttyUSB0'

    print(f"  Using port: {port}")

    # ──────────────────────────────────────────────
    # Step 3: Start recorder in separate thread
    # ──────────────────────────────────────────────
    print("\n[Step 3] Starting Recorder")
    print("-" * 40)

    done_event = threading.Event()

    recorder_thread = threading.Thread(
        target=run_recorder,
        args=(port, done_event),
        daemon=True
    )
    recorder_thread.start()
    print("  Recorder thread started (waiting for ESP32...)")

    # ──────────────────────────────────────────────
    # Step 4: Main thread — monitor + motor control
    # ──────────────────────────────────────────────
    print("\n[Step 4] Recording in progress")
    print("-" * 40)
    print("  Commands while recording:")
    print("    hz <value>   Change motor speed")
    print("    <number>     Set duty cycle %")
    print("    stop         Stop motor (keep recording)")
    print("    status       Show motor status")
    print("  Recording stops when ESP32 sends ALL_COMPLETE or Ctrl+C\n")

    try:
        while not done_event.is_set():
            # Check if recorder finished (non-blocking with timeout)
            if done_event.wait(timeout=0.1):
                break

            # Check for user input (non-blocking via select)
            import select
            if select.select([sys.stdin], [], [], 0.1)[0]:
                cmd = sys.stdin.readline().strip().lower().split()
                if not cmd:
                    continue

                if cmd[0] == 'status':
                    rpm, hz = duty_cycle_to_rpm(motor.current_duty_cycle)
                    print(f"  Motor: {motor.current_duty_cycle:.1f}% -> {rpm:.0f} RPM ({hz:.1f} Hz)")

                elif cmd[0] == 'stop':
                    motor.set_duty_cycle(0)
                    print("  Motor stopped (recording continues)")

                elif cmd[0] == 'hz' and len(cmd) >= 2:
                    try:
                        target_hz = float(cmd[1])
                        duty = hz_to_duty_cycle(target_hz)
                        motor.set_duty_cycle(duty)
                        rpm, hz = duty_cycle_to_rpm(duty)
                        print(f"  Motor set: {duty:.1f}% -> {rpm:.0f} RPM ({hz:.1f} Hz)")
                    except ValueError:
                        print("  Invalid Hz value")

                else:
                    try:
                        duty = float(cmd[0])
                        motor.set_duty_cycle(max(0, min(100, duty)))
                        rpm, hz = duty_cycle_to_rpm(duty)
                        print(f"  Motor set: {duty:.1f}% -> {rpm:.0f} RPM ({hz:.1f} Hz)")
                    except ValueError:
                        print("  Unknown command. Try: hz <val>, <duty%>, stop, status")

    except KeyboardInterrupt:
        print("\n\n  Interrupted by user")

    # ──────────────────────────────────────────────
    # Step 5: Cleanup motor
    # ──────────────────────────────────────────────
    print("\n[Step 5] Stopping Motor")
    print("-" * 40)
    motor.cleanup()

    # Wait for recorder thread to fully finish
    recorder_thread.join(timeout=5)
    print("  Recorder thread finished")

    # ──────────────────────────────────────────────
    # Step 6: Launch offline analyzer
    # ──────────────────────────────────────────────
    print("\n[Step 6] Launching Offline Analyzer")
    print("-" * 40)

    launch = input("  Open offline analyzer? (y/n): ").strip().lower()
    if launch in ('y', 'yes', ''):
        print("  Starting offline_analyzer_exp.py...")
        subprocess.Popen([sys.executable, "offline_analyzer_exp.py"])
        print("  Analyzer launched. System manager done.")
    else:
        print("  Skipped. Run manually: python3 offline_analyzer_exp.py")

    print("\n" + "=" * 60)
    print("  SESSION COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
