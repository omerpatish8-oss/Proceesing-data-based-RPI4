# Code Reference - Parkinson's Rest Tremor Detection System

## esp32_usb_serial_safe_V3.ino
Runs on the ESP32 microcontroller using **dual-core FreeRTOS** architecture. Core 1 runs a dedicated high-priority sampler task that reads the MPU6050 at 100 Hz with drift-free `vTaskDelayUntil` timing and outputs CSV over USB Serial. Core 0 runs the main loop handling the FSM (IDLE/RECORDING/PAUSED/WAITING_NEXT/FINISHED), OLED display updates, LED blinking, and button input. This separation ensures that the ~23 ms OLED I2C transfer never blocks sensor sampling.
Safety features: stuck-sensor detection (15 identical reads), I2C read failure counting (5 max), I2C health check (every 500 ms, on Core 1 — no cross-core bus contention), `Wire.setTimeOut(10)` to prevent I2C hangs, and a 5-second hardware watchdog (WDT) that auto-reboots on any hang. Reports `MISSED,<count>` at cycle end for sample loss tracking.
Output: streams CSV lines (`Timestamp,Ax,Ay,Az`) and control events (`START_RECORDING`, `CYCLE,n`, `PAUSE_CYCLE`, `RESUME_CYCLE`, `END_RECORDING`, `ALL_COMPLETE`, `MISSED,n`, error flags) over USB Serial at 115200 baud.

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
Main components: DC offset removal (mean subtraction per axis), resultant vector calculation, Butterworth bandpass filter (2-8 Hz, order 4, zero-phase via filtfilt), Welch PSD estimation, FFT spectrum, Hilbert envelope, zero-crossing cycle counting, and metrics panel (peak SNR, dominant power ratio, frequency deviation from motor input).
Output: interactive matplotlib figures (filter Bode plots, time-domain signals, PSD, zoomed 5s windows with cycle markers, full-recording FFT) and a console summary of all computed metrics.

## sys_manager.py
Top-level orchestrator that ties all Raspberry Pi components together via a menu-based interface. Allows the user to start the motor, launch the recorder, and run the offline analyzer in the correct sequence.
Main components: menu loop (options 1-5 + quit), motor control integration (MotorController from motor_control.py), recorder thread (runs rpi_usb_recorder_v2.record_data in background), analyzer launcher (subprocess call to offline_analyzer_exp.py), and system status display.
Output: coordinates the full measurement workflow - motor spins at user-set duty cycle, recorder captures ESP32 data in parallel, and analyzer becomes available after recording completes.
