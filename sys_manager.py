#!/usr/bin/env python3
"""
System Manager - Orchestrates motor control, data recording, and offline analysis.

Architecture:
  - Main thread: menu-based user interface
  - Motor: software PWM via RPi.GPIO library (MotorController)
  - Recorder thread: UART read loop (rpi_usb_recorder_v2.record_data)
  - Motor and recorder run in parallel (motor keeps spinning while recorder captures)
  - Offline analyzer: launched only after recording is finished

Usage:
  python3 sys_manager.py
"""

import threading
import time
import sys
import subprocess

from motor_control import MotorController, duty_cycle_to_rpm
from rpi_usb_recorder_v2 import record_data, find_port, create_output_folder


# ══════════════════════════════════════════════
# State shared between threads
# ══════════════════════════════════════════════
motor = None
recorder_done_event = threading.Event()
recorder_thread = None
recording_finished = False  # True after recorder completes at least once


def run_recorder(port):
    """Recorder thread: runs UART read loop until ESP32 signals ALL_COMPLETE."""
    global recording_finished
    try:
        record_data(port)
    except Exception as e:
        print(f"\n[Recorder] Error: {e}")
    finally:
        recording_finished = True
        recorder_done_event.set()


def start_motor():
    """Option 1: Start motor with user-specified duty cycle."""
    global motor

    if motor is not None:
        rpm, hz = duty_cycle_to_rpm(motor.current_duty_cycle)
        print(f"\n  Motor already running at {motor.current_duty_cycle:.1f}% "
              f"-> {rpm:.0f} RPM ({hz:.1f} Hz)")
        cmd = input("  Change duty cycle? Enter DC% (0-100) or 'back': ").strip().lower()
        if cmd == 'back':
            return
        try:
            duty = float(cmd)
            duty = max(0, min(100, duty))
            motor.set_duty_cycle(duty)
            rpm, hz = duty_cycle_to_rpm(duty)
            print(f"  Motor set: {duty:.1f}% -> {rpm:.0f} RPM ({hz:.1f} Hz)")
        except ValueError:
            print("  Invalid input.")
        return

    print("\n  Initializing motor...")
    motor = MotorController()
    motor.start_forward()

    while True:
        cmd = input("\n  Enter Duty Cycle (0-100%) or 'back': ").strip().lower()
        if cmd == 'back':
            motor.cleanup()
            motor = None
            print("  Motor stopped and released.")
            return
        try:
            duty = float(cmd)
            if duty < 0 or duty > 100:
                print("  Duty cycle must be 0-100%")
                continue
            motor.set_duty_cycle(duty)
            rpm, hz = duty_cycle_to_rpm(duty)
            print(f"  Motor set: {duty:.1f}% -> {rpm:.0f} RPM ({hz:.1f} Hz)")
            return
        except ValueError:
            print("  Invalid input. Enter a number 0-100.")


def start_recorder():
    """Option 2: Start the USB recorder in a background thread."""
    global recorder_thread

    if recorder_thread is not None and recorder_thread.is_alive():
        print("\n  Recorder is already running. Wait for ESP32 to finish.")
        return

    # Reset state for a new recording session
    recorder_done_event.clear()

    # Find serial port
    print("\n  Finding serial port...")
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = find_port()
        if not port:
            port = '/dev/ttyUSB0'

    print(f"  Using port: {port}")

    create_output_folder()

    recorder_thread = threading.Thread(
        target=run_recorder,
        args=(port,),
        daemon=True
    )
    recorder_thread.start()
    print("  Recorder started (waiting for ESP32 button press...)")
    print("  You can now return to the menu and use other options.\n")


def start_analyzer():
    """Option 3: Launch offline analyzer (only if recording is finished)."""
    if recorder_thread is not None and recorder_thread.is_alive():
        print("\n  Recording is still in progress!")
        print("  The analyzer can only run after recording is finished.")
        return

    print("\n  Starting offline_analyzer_exp.py...")
    subprocess.Popen([sys.executable, "offline_analyzer_exp.py"])
    print("  Analyzer launched.")


def stop_motor():
    """Stop and cleanup the motor."""
    global motor
    if motor is None:
        print("\n  Motor is not running.")
        return
    motor.cleanup()
    motor = None
    print("\n  Motor stopped and GPIO released.")


def show_status():
    """Show current system status."""
    print("\n  ── System Status ──")

    # Motor
    if motor is not None:
        rpm, hz = duty_cycle_to_rpm(motor.current_duty_cycle)
        print(f"  Motor:    ON  | {motor.current_duty_cycle:.1f}% -> {rpm:.0f} RPM ({hz:.1f} Hz)")
    else:
        print(f"  Motor:    OFF")

    # Recorder
    if recorder_thread is not None and recorder_thread.is_alive():
        print(f"  Recorder: RUNNING")
    elif recording_finished:
        print(f"  Recorder: FINISHED")
    else:
        print(f"  Recorder: NOT STARTED")

    # Analyzer availability
    can_analyze = recorder_thread is None or not recorder_thread.is_alive()
    print(f"  Analyzer: {'AVAILABLE' if can_analyze else 'BLOCKED (recording in progress)'}")


def main():
    global motor

    print("\n" + "=" * 60)
    print("  SYSTEM MANAGER")
    print("  Motor Control + Recording + Offline Analysis")
    print("=" * 60)

    try:
        while True:
            # Check if recorder finished in background
            if recorder_thread is not None and not recorder_thread.is_alive() and recorder_done_event.is_set():
                print("\n  [Recorder finished]")
                recorder_done_event.clear()

            rec_active = recorder_thread is not None and recorder_thread.is_alive()
            analyzer_blocked = " (blocked - recording active)" if rec_active else ""

            print(f"\n  ┌─────────────────────────────────┐")
            print(f"  │  1. Motor Control                │")
            print(f"  │  2. Start Recorder               │")
            print(f"  │  3. Offline Analyzer{analyzer_blocked:13s}│" if not rec_active
                  else f"  │  3. Offline Analyzer (blocked)   │")
            print(f"  │  4. Status                       │")
            print(f"  │  5. Stop Motor                   │")
            print(f"  │  q. Quit                         │")
            print(f"  └─────────────────────────────────┘")

            cmd = input("\n  Select option: ").strip().lower()

            if cmd == '1':
                start_motor()
            elif cmd == '2':
                start_recorder()
            elif cmd == '3':
                start_analyzer()
            elif cmd == '4':
                show_status()
            elif cmd == '5':
                stop_motor()
            elif cmd in ('q', 'quit', 'exit'):
                break
            else:
                print("  Invalid option. Enter 1-5 or q.")

    except KeyboardInterrupt:
        print("\n\n  Interrupted by user")

    # Cleanup
    print("\n" + "-" * 40)
    print("  Shutting down...")

    if motor is not None:
        motor.cleanup()
        motor = None
        print("  Motor stopped.")

    if recorder_thread is not None and recorder_thread.is_alive():
        print("  Waiting for recorder to finish...")
        recorder_thread.join(timeout=5)

    print("\n" + "=" * 60)
    print("  SESSION COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
