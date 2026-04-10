#!/usr/bin/env python3
"""
System Manager - Orchestrates motor control, data recording, and offline analysis.

Concurrency model (three components, three mechanisms):
  - Motor PWM: kernel-side PWM thread inside RPi.GPIO. No user-space thread
    needed — once set_duty_cycle() is called, the pulse train is generated
    autonomously by the GPIO library.
  - Recorder: daemon threading.Thread running record_data(port). The recorder
    is I/O-bound (blocked on ser.readline()), so it releases the CPython GIL
    while waiting, leaving the main menu thread fully responsive. A thread
    (not a process) is preferred because the recorder and the menu need to
    share a cheap in-process boolean — is_actively_recording — to decide
    whether the analyzer can be launched right now.
  - Offline analyzer: separate OS process via subprocess.Popen. Tkinter is
    not thread-safe and supports only one mainloop() per interpreter, so the
    analyzer must live in its own interpreter. A subprocess also gives it
    its own crash domain — a matplotlib/NumPy exception in the analyzer
    cannot take down the recorder thread.

Analyzer-between-cycles: the analyzer can be launched as soon as any cycle
completes, not only after ALL cycles are done. The recorder module exposes
`is_actively_recording` which is True only while samples are flowing. Between
cycles the thread is alive but that flag is False, so the analyzer launch is
allowed — the CSV from the just-finished cycle is closed and safe to read.

Usage:
  python3 sys_manager.py
"""

import threading
import time
import sys
import subprocess

from motor_control import MotorController, duty_cycle_to_rpm
import rpi_usb_recorder_v2
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
    """Option 3: Launch offline analyzer.

    Allowed whenever a cycle is NOT actively being recorded. This includes:
      - before any cycle has started (nothing to analyze, but the GUI still
        opens so the user can load an older file)
      - between cycles (recorder thread alive, waiting for next button press)
      - after all cycles complete

    Blocked only while is_actively_recording is True (samples mid-flight).
    """
    if rpi_usb_recorder_v2.is_actively_recording:
        print("\n  A recording cycle is currently in progress!")
        print("  Wait for the cycle to finish (END_RECORDING) before")
        print("  launching the analyzer — the CSV is still being written.")
        return

    # Hint the user at the most recent cycle file if we have one
    last_file = rpi_usb_recorder_v2.last_completed_cycle_file
    if last_file:
        print(f"\n  Last completed cycle file: {last_file}")

    print("\n  Starting offline_analyzer_exp.py...")
    subprocess.Popen([sys.executable, "offline_analyzer_exp.py"])
    print("  Analyzer launched (in its own subprocess).")


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
        if rpi_usb_recorder_v2.is_actively_recording:
            print(f"  Recorder: RECORDING (cycle in progress)")
        else:
            print(f"  Recorder: IDLE (waiting for next cycle)")
    elif recording_finished:
        print(f"  Recorder: FINISHED")
    else:
        print(f"  Recorder: NOT STARTED")

    # Analyzer availability
    can_analyze = not rpi_usb_recorder_v2.is_actively_recording
    if can_analyze:
        print(f"  Analyzer: AVAILABLE")
    else:
        print(f"  Analyzer: BLOCKED (cycle in progress — CSV still being written)")

    # Last completed cycle file (useful for the between-cycles workflow)
    last_file = rpi_usb_recorder_v2.last_completed_cycle_file
    if last_file:
        print(f"  Last file: {last_file}")


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

            # Analyzer is blocked only while a cycle is mid-capture, NOT
            # merely while the recorder thread is alive between cycles.
            analyzer_blocked = rpi_usb_recorder_v2.is_actively_recording

            print(f"\n  ┌─────────────────────────────────┐")
            print(f"  │  1. Motor Control                │")
            print(f"  │  2. Start Recorder               │")
            if analyzer_blocked:
                print(f"  │  3. Offline Analyzer (blocked)   │")
            else:
                print(f"  │  3. Offline Analyzer             │")
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
