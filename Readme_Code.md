# Code Reference - Parkinson's Rest Tremor Detection System

## esp32_usb_serial_safe_V2.ino
Runs on the ESP32 microcontroller. Reads MPU6050 accelerometer data at 100 Hz via polled `millis()` timing, manages recording cycles (start/pause/resume/stop) via a physical button and FSM (IDLE/RECORDING/PAUSED/WAITING_NEXT/FINISHED), and detects sensor faults with automatic reset.
Safety stack (4 layers): stuck-sensor detection (15 identical reads), I2C read failure counting (5 max), `Wire.setTimeOut(10)` to prevent I2C bus hangs, and a 5-second hardware watchdog (WDT) that auto-reboots on any hang. Periodic I2C health check was removed — redundant with read failure counting (if sensor disconnects, getEvent() fails within 50ms and triggers reset). SSD1306 OLED display updates every 4 seconds during recording (reduced from 1s to minimize the ~23ms blocking that disrupts 100Hz sampling). LED indicators for state feedback.
Output: streams CSV lines (`Timestamp,Ax,Ay,Az`) and control events (`START_RECORDING`, `CYCLE,n`, `PAUSE_CYCLE`, `RESUME_CYCLE`, `END_RECORDING`, `ALL_COMPLETE`, error flags) over USB Serial at 115200 baud.

## rpi_usb_recorder_v2.py
Runs on the Raspberry Pi. Listens on the USB serial port, parses the ESP32 event stream, and saves accelerometer data into per-cycle CSV files with metadata headers and per-cycle log files.
Main components: serial port auto-detection, CSV data validation (4-column format check), connection timeout monitoring, error/event logging, and cycle-aware file management (new file per cycle, same file across pause/resume).
Output: `tremor_data/tremor_cycleN_YYYYMMDD_HHMMSS.csv` (timestamped accelerometer data) and matching `.log` files (events, errors, sensor resets, session summary).

## motor_control.py
Drives the L298N motor controller from the Raspberry Pi via software PWM (RPi.GPIO library). Controls a 12V DC gearbox motor with an eccentric mass that generates controlled vibrations simulating rest tremor.
Main components: `MotorController` class (GPIO setup, PWM at 1 kHz carrier, direction control via IN1/IN2), `duty_cycle_to_rpm()` conversion (linear model: 0-100% maps to 0-625 RPM / 0-10.4 Hz), and standalone CLI mode for manual testing.
Output: PWM signal on GPIO18 that sets motor speed; the motor's physical vibration is picked up by the MPU6050 sensor on the ESP32.

## offline_analyzer_exp.py
Post-recording analysis tool with a Tkinter GUI. Loads a recorded CSV file, applies DSP processing, and produces 6 figure tabs for tremor characterization. Reports frequency and amplitude metrics without pass/fail judgment (experimental mode).
Main components: Butterworth bandpass filter (2-8 Hz, order 4, zero-phase via filtfilt) applied per axis independently (inherently removes DC/gravity), resultant vector from filtered axes (for RMS), Welch PSD per filtered axis, dominant axis selection (highest PSD peak in 2-8 Hz), FFT spectrum of the raw dominant axis (0-12 Hz), Hilbert envelope, zero-crossing cycle counting, and metrics panel (RMS, dominant power ratio, frequency deviation from motor input).
Key design decisions:
- Fig 2.1 displays the raw dominant axis signal without DC removal (preserving the true sensor output including gravity offset).
- Fig 3.1 Raw PSD comparison uses the raw dominant axis (DC-removed for PSD only) instead of the resultant vector, for a fair before/after comparison against the filtered PSD on the same axis.
- Fig 6 FFT operates on the raw (unfiltered) dominant axis to reveal the full spectrum including content the bandpass filter removes. Y-axis capped at 0-2 m/s² so the tremor band peaks remain visible above the DC bin.
- The previously included Fig 7 (STFT spectrogram) has been removed — the full-recording FFT and the per-window zoomed views already cover the frequency-stability question for a 2-minute motor-driven test.
Output: interactive matplotlib figures (filter Bode plots, time-domain signals, PSD, zoomed 5s windows with cycle markers, full-recording FFT) and a console summary of all computed metrics.

## sys_manager.py
Top-level orchestrator that ties all Raspberry Pi components together via a menu-based interface. Allows the user to start the motor, launch the recorder, and run the offline analyzer in the correct sequence — including launching the analyzer on any already-completed cycle while the recorder is still waiting for the next cycle.
Main components: menu loop (options 1-5 + quit), motor control integration (MotorController from motor_control.py), recorder thread (runs rpi_usb_recorder_v2.record_data in background), analyzer launcher (subprocess call to offline_analyzer_exp.py), and system status display.

### Concurrency model — three components, three different mechanisms
The three long-running components (motor PWM, USB recorder, offline analyzer) do not use the same concurrency primitive. Each one is placed on the lightest mechanism that meets its requirements:

| Component | Runs on | Why |
|-----------|---------|-----|
| Motor PWM | Kernel-level hardware PWM (via `RPi.GPIO` software PWM thread) | Once `set_duty_cycle()` is called, the pulse train is generated autonomously by the library's kernel-side timer. The Python main thread does not need to loop or sleep to keep the motor spinning, so no user-space thread is needed for the motor at all. |
| USB recorder | Background daemon `threading.Thread` running `record_data(port)` | The recorder is a tight `ser.readline()` loop — I/O-bound, blocked on the kernel read syscall. While blocked, the CPython GIL is released, so the main thread (menu) keeps responding to keystrokes with zero contention. A thread (not a process) is preferred because both threads need to share in-process state: the recorder updates the `is_actively_recording` / `recording_finished` module-level flags that the main thread reads when drawing the menu and deciding whether the analyzer can be launched. Sharing that state across a process boundary would require pipes or `multiprocessing.Manager`, which is a lot of plumbing for a boolean. |
| Offline analyzer | Separate OS process via `subprocess.Popen([sys.executable, "offline_analyzer_exp.py"])` | The analyzer owns its own Tkinter main loop — and Tk is famously not thread-safe; you cannot spawn two Tk `mainloop()` instances in the same interpreter. A subprocess gives the analyzer its own interpreter, its own Tk root, and its own GUI event loop that lives and dies independently of `sys_manager.py`. It also means a crash in the analyzer (matplotlib, Tk, NumPy) cannot take down the recorder thread. |

**Why not use `multiprocessing` instead of `threading` for the recorder?** `multiprocessing` is the right answer when the child needs real CPU parallelism on multiple cores despite the GIL. The recorder does ~20 µs of Python work per sample (at 100 Hz → 0.2% CPU) and spends the rest blocked on serial I/O — the GIL is not a bottleneck. Spawning a process would add fork/spawn overhead, serialize every shared-state update through a pipe or `Manager`, and break the simple "recorder writes a flag, main thread reads it" pattern. `threading` is strictly cheaper here and is the standard Python idiom for I/O-bound background work.

**Why not run the analyzer as a thread inside `sys_manager.py`?** Tk requires its `mainloop()` to run on the thread that created the root window, and having two Tk roots in one process is unsupported. Even if it worked, any unhandled exception in matplotlib or Tk would crash the menu as well. A subprocess is the cleanest isolation.

### Running the analyzer between cycles (not just at the very end)
Historically the analyzer was blocked until the recorder thread fully exited (`recorder_thread.is_alive()` == False), i.e. only after ALL cycles finished. That was needlessly strict — between two cycles the recorder thread is alive but idle (just polling for the next `START_RECORDING` from the ESP32), and the CSV file from the previous cycle is already closed, flushed, and safe to analyze.

The recorder (`rpi_usb_recorder_v2.py`) now exposes a module-level flag `is_actively_recording` that is `True` only between `START_RECORDING`/`RESUME_CYCLE` and the corresponding `PAUSE_CYCLE`/`END_RECORDING`. `sys_manager.start_analyzer()` checks this flag instead of `thread.is_alive()`, so the analyzer can be launched as soon as one cycle completes — the user can look at cycle 1 while cycle 2 is still ahead of them. If the user tries to launch the analyzer mid-cycle (while samples are actively being written), the launch is rejected with an informative message.

Output: coordinates the full measurement workflow - motor spins at user-set duty cycle, recorder captures ESP32 data in parallel, and the analyzer can be launched on any completed cycle (either between cycles or after all cycles are done).
