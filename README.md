# Parkinson's Rest Tremor Detection System

A complete data acquisition and signal processing pipeline for detecting and validating rest tremor (2-8 Hz) using Raspberry Pi 4, ESP32, and MPU6050 accelerometer. Designed for Parkinson's disease research and input-output validation against a known vibration source.

---

## System Overview

```
┌──────────────┐    I2C     ┌──────────────┐   USB UART   ┌──────────────┐
│   MPU6050    │──────────→ │    ESP32     │────────────→ │    RPI 4     │
│  (Sensor)    │  400 kHz   │  (Sampler)   │  115200 baud │  (Recorder)  │
│  +/-2G       │  SDA/SCL   │  100 Hz      │  ~30 B/line  │  CSV output  │
└──────────────┘            └──────────────┘              └──────┬───────┘
                                                                 │
                            ┌──────────────┐              ┌──────┴───────┐
                            │  DC Motor    │◄─────────────│  Motor PWM   │
                            │  + Eccentric │   GPIO 18    │  (L298N)     │
                            │    Mass      │   1 kHz PWM  │  Open loop   │
                            └──────────────┘              └──────────────┘
                                                                 │
                                                          ┌──────┴───────┐
                                                          │   Offline    │
                                                          │  Analyzer    │
                                                          │  (Tkinter)   │
                                                          └──────────────┘
```

### Scripts

| Script | Runs On | Role |
|--------|---------|------|
| `esp32_usb_serial_safe.ino` | ESP32 | Samples MPU6050 at 100 Hz, transmits via USB Serial |
| `rpi_usb_recorder_v2.py` | RPI 4 | Receives UART data, validates, writes CSV files |
| `motor_control.py` | RPI 4 | Controls DC motor via L298N driver (PWM on GPIO18) |
| `offline_analyzer.py` | PC/RPI 4 | Signal processing, PSD analysis, input-output validation |
| `sys_manager.py` | RPI 4 | Orchestrates motor + recorder in parallel using threading |

---

## Hardware

### Components

**Data Acquisition:**
- Raspberry Pi 4
- ESP32 Development Board
- MPU6050 IMU (accelerometer only, +/-2G range)
- SSD1306 OLED Display (128x64)
- Push Button (GPIO 13)
- LEDs: Green (GPIO 15), Red (GPIO 2)
- USB Micro cable (ESP32 to RPI4)

**Vibration Source (for validation):**
- L298N Motor Driver (H-bridge)
- 12V DC Gearbox Motor with eccentric mass (40g)
- 12V Power Supply

### Wiring

```
ESP32 Side:
  MPU6050:  SDA → GPIO 21, SCL → GPIO 22, VCC → 3.3V, GND → GND
  SSD1306:  SDA → GPIO 18, SCL → GPIO 19, VCC → 3.3V, GND → GND
  Button:   GPIO 13 (internal pull-up)
  LEDs:     Green → GPIO 15, Red → GPIO 2

RPI 4 Side (L298N Motor Driver):
  ENA (PWM) → GPIO 18
  IN1       → GPIO 23
  IN2       → GPIO 24
  12V       → External power supply
  Motor     → OUT1/OUT2
```

---

## Pipeline Walkthrough

### Stage 1: Sensor Acquisition (`esp32_usb_serial_safe.ino`)

#### Sampling

The ESP32 samples the MPU6050 accelerometer at **100 Hz** (every 10 ms):

```
Sample interval = 1000 ms / 100 Hz = 10 ms
```

This satisfies the Nyquist criterion for rest tremor analysis:

```
Nyquist frequency = 100 Hz / 2 = 50 Hz
Tremor band       = 2-8 Hz
50 Hz >> 8 Hz     → No aliasing in the tremor band
```

The MPU6050 internal DLPF (Digital Low-Pass Filter) is set to **21 Hz bandwidth**, which attenuates frequencies above ~21 Hz before the signal reaches the ESP32. This acts as a hardware anti-aliasing filter.

#### Accelerometer Configuration

| Parameter | Value | Detail |
|-----------|-------|--------|
| Range | +/-2G | 16384 LSB/g resolution |
| DLPF Bandwidth | 21 Hz | Hardware anti-alias filter |
| I2C Clock | 400 kHz | Fast Mode |
| Output | m/s^2 | Adafruit library converts raw LSB to SI units |

#### Calibration

Static calibration offsets are subtracted from each axis at the sensor level (before transmission):

```cpp
float aX_off = 0.301009;   // m/s^2
float aY_off = 0.016101;   // m/s^2
float aZ_off = 1.046231;   // m/s^2 (includes ~1g gravity on Z)

ax = a.acceleration.x - aX_off;
ay = a.acceleration.y - aY_off;
az = a.acceleration.z - aZ_off;
```

These offsets were measured with the sensor stationary on a flat surface. The Z offset (~1.046 m/s^2) partially compensates for gravity but does not fully remove it — full DC removal happens later in the offline analyzer.

#### Sensor Safety

The firmware monitors sensor health continuously:

| Check | Interval | Threshold | Action |
|-------|----------|-----------|--------|
| Stuck detection | Every sample | 15 identical readings (delta < 0.001 m/s^2) | Auto-reset sensor |
| Read failure | Every sample | 5 consecutive failures | Auto-reset sensor |
| Connection loss | Every 500 ms | I2C ACK missing or 2s since last read | Auto-reset sensor |

Reset procedure: close I2C bus, wait 150 ms, reinitialize I2C at 400 kHz, reinitialize MPU6050.

#### State Machine

```
IDLE ──[button]──→ RECORDING ──[button]──→ PAUSED ──[button]──→ RECORDING
                       │                                            │
                       └──────[120s elapsed]──→ WAITING_NEXT ──[button]──→ RECORDING
                                                     │
                                              [all cycles done]
                                                     │
                                                     ▼
                                                  FINISHED
```

- **Recording duration**: 120 seconds per cycle (configurable via `TARGET_DURATION`)
- **Max cycles**: 2 (configurable via `MAX_CYCLES`)
- **Stopwatch timing**: accumulated time is preserved across pause/resume so timestamps in the CSV remain continuous with no gaps

### Stage 2: UART Transmission (ESP32 → RPI)

#### Physical Layer

```
ESP32 USB Micro → USB cable → RPI 4 USB port → /dev/ttyUSB0
```

The ESP32 native USB-to-UART bridge (CP2102 or CH340) converts Serial.print() output to USB packets. On the RPI side, the Linux kernel presents this as a virtual serial port `/dev/ttyUSB0`.

#### Protocol

| Parameter | Value |
|-----------|-------|
| Baud rate | 115200 bps |
| Data bits | 8 |
| Stop bits | 1 |
| Parity | None |
| Flow control | None |

#### Data Format

Each sample is one CSV line transmitted over UART:

```
<timestamp_ms>,<Ax>,<Ay>,<Az>\n
```

Example: `10,0.582,-0.198,-1.228\n`

#### Transmission Rate Calculation

Each data line contains approximately 25-30 characters:

```
Timestamp (1-6 chars) + comma + Ax (6 chars) + comma + Ay (6 chars) + comma + Az (6 chars) + newline
Typical: "10500,-0.198,-1.228,9.432\n" = ~28 characters = 28 bytes
```

At 100 Hz:

```
Data throughput  = 28 bytes × 10 bits/byte × 100 Hz = 28,000 bps
Available        = 115,200 bps
Utilization      = 28,000 / 115,200 = ~24%
```

The 10 bits/byte accounts for 8 data bits + 1 start bit + 1 stop bit (UART framing). At 24% utilization, there is substantial margin for the control messages (START_RECORDING, PAUSE_CYCLE, etc.) that are interleaved with data.

#### Control Protocol Messages

The ESP32 sends text-based control messages alongside data. The recorder parses these to manage state:

| Message | Meaning |
|---------|---------|
| `START_RECORDING` | Recording cycle started |
| `CYCLE,<N>` | Cycle number N began |
| `PAUSE_CYCLE` | User paused recording |
| `RESUME_CYCLE` | User resumed recording |
| `END_RECORDING` | Cycle complete (120s elapsed) |
| `ALL_COMPLETE` | All cycles finished |
| `ERROR_SENSOR_STUCK` | 15 identical readings detected |
| `ERROR_SENSOR_LOST` | I2C connection lost |
| `ERROR_READ_FAILED` | 5 consecutive read failures |
| `SENSOR_RESET,<N>` | Sensor reset #N occurred |
| `SENSOR_RESET_OK` | Reset successful |
| `SENSOR_RESET_FAILED` | Reset failed |

The recorder distinguishes data lines from control messages by checking if the line starts with a digit and contains a comma.

### Stage 3: Data Recording (`rpi_usb_recorder_v2.py`)

The recorder runs on the RPI 4 and listens on the USB serial port.

#### Recording Pipeline

```
Serial port (/dev/ttyUSB0, 115200 baud)
  │
  ▼
ser.readline()          ← blocks until \n received
  │
  ▼
Parse line type:
  ├── Control message → update state machine (recording/paused/done)
  ├── CSV header ("Timestamp,...") → write to file
  └── Data line ("12345,0.1,0.2,0.3") → validate → write to CSV
```

#### Data Validation

Every data line is validated before writing (line 38-58):

```python
def validate_data_line(line):
    parts = line.split(',')
    if len(parts) != 4:           # Must have exactly 4 columns
        return False
    int(parts[0])                  # Timestamp must be integer >= 0
    for i in range(1, 4):
        float(parts[i])           # Ax, Ay, Az must be numeric
```

Invalid lines are written as comments (`# INVALID: ...`) so they are preserved but excluded from analysis.

#### Output Files

For each recording cycle, two files are created:

```
tremor_data/
  tremor_cycle1_20260304_143000.csv    ← Sensor data
  tremor_cycle1_20260304_143000.log    ← Events and errors
```

CSV file structure:

```csv
# Cycle: 1
# Start Time: 2026-03-04 14:30:00
# Sample Rate: 100 Hz
# Format: Timestamp(ms),Ax(m/s^2),Ay(m/s^2),Az(m/s^2)
Timestamp,Ax,Ay,Az
0,0.582,-0.198,-1.228
10,0.580,-0.200,-1.230
20,0.583,-0.197,-1.227
...
```

#### Connection Monitoring

If no data is received for 5 seconds during active recording, the recorder logs a timeout warning. This detects USB disconnections or ESP32 hangs without crashing the recorder.

#### Expected Data Volume

```
Samples per cycle  = 100 Hz × 120 s = 12,000 samples
Bytes per line     = ~28 bytes
File size per cycle = 12,000 × 28 = ~336 KB
With metadata      = ~340 KB per CSV file
```

### Stage 4: Motor Control (`motor_control.py`)

The DC motor with an eccentric mass generates controlled vibrations at a known frequency. This serves as the system's input signal for input-output validation.

#### PWM Configuration

```
PWM pin:           GPIO 18 (via L298N ENA)
Carrier frequency: 1000 Hz (electrical switching frequency)
Direction pins:    IN1 = GPIO 23, IN2 = GPIO 24
```

The 1 kHz PWM carrier is the switching frequency of the L298N H-bridge — it is NOT the motor rotation frequency. The motor rotation frequency depends on the duty cycle:

#### Duty Cycle to Rotation Frequency (Open Loop)

```
Motor max: 625 RPM at 12V (100% duty cycle)
Max Hz:    625 / 60 = 10.42 Hz

Mapping (linear approximation):
  Duty%   Voltage   RPM     Hz
  20%     2.4V      125     2.1
  30%     3.6V      188     3.1
  40%     4.8V      250     4.2
  50%     6.0V      313     5.2
  60%     7.2V      375     6.3
  70%     8.4V      438     7.3
  80%     9.6V      500     8.3
```

Note: This is an open-loop approximation. Actual motor speed varies with load, friction, and supply voltage. The duty-to-Hz mapping assumes a linear relationship which is approximate.

#### Control Interface

The `MotorController` class provides:

```python
motor = MotorController()     # Initialize GPIO + PWM
motor.start_forward()          # Set direction (IN1=HIGH, IN2=LOW)
motor.set_duty_cycle(40)       # Set speed (0-100%)
motor.stop()                   # Set duty to 0%
motor.cleanup()                # Stop + release GPIO
```

When running standalone (`python3 motor_control.py`), an interactive CLI allows changing speed in real-time using duty cycle values or target Hz.

### Stage 5: System Orchestration (`sys_manager.py`)

The system manager coordinates motor control and data recording using Python threading.

#### Architecture

```
┌─────────────────────────────────────────────────┐
│                  sys_manager.py                  │
│                                                  │
│  Main Thread              Recorder Thread        │
│  ────────────             ───────────────        │
│  1. Init motor            record_data(port)      │
│  2. Set duty cycle          │                    │
│  3. Start recorder ─────→ while True:            │
│     thread                    ser.readline()     │
│  4. Accept motor              validate + write   │
│     commands while            ...                │
│     recording               ALL_COMPLETE         │
│  5. done_event.wait() ◄─── done_event.set()     │
│  6. motor.cleanup()                              │
│  7. Launch analyzer                              │
└─────────────────────────────────────────────────┘
```

#### Threading Model

- **Main thread**: sets motor speed, then enters a loop where it accepts motor commands (change Hz, stop, status) while monitoring the `done_event`
- **Recorder thread** (daemon): runs `record_data(port)` which blocks in the UART read loop. When ESP32 sends `ALL_COMPLETE`, the function returns and signals `done_event`
- **Motor PWM**: runs in hardware on GPIO18 — no thread needed. Once `set_duty_cycle()` is called, the PWM signal continues autonomously

#### Synchronization

A `threading.Event` object coordinates the two threads:

```python
done_event = threading.Event()

# Recorder thread (on finish):
done_event.set()

# Main thread (monitoring):
done_event.wait(timeout=0.1)   # Non-blocking check
```

When the recorder signals completion, the main thread exits its command loop, stops the motor, and optionally launches the offline analyzer.

#### Execution Flow

```
$ python3 sys_manager.py

[Step 1] Motor Setup
  → User enters: "hz 5" (sets motor to ~5 Hz vibration)
  → MotorController sets duty cycle, motor starts spinning

[Step 2] Serial Port
  → Auto-detects /dev/ttyUSB0

[Step 3] Start Recorder Thread
  → recorder_thread.start()
  → UART read loop begins in background

[Step 4] Recording in Progress
  → Main thread accepts commands: hz, stop, status
  → Motor spins while recorder captures data
  → ESP32 records for 120s per cycle

[Step 5] Recording Complete
  → ESP32 sends ALL_COMPLETE → done_event fires
  → motor.cleanup() stops PWM and releases GPIO

[Step 6] Launch Offline Analyzer
  → subprocess.Popen(["python3", "offline_analyzer.py"])
```

### Stage 6: Offline Signal Processing (`offline_analyzer.py`)

The offline analyzer is a Tkinter GUI application that loads a recorded CSV file and performs the full signal processing chain.

#### Signal Processing Chain

```
CSV File (Timestamp, Ax, Ay, Az)
  │
  │ Step 1: Parse CSV
  ▼
Raw axes: Ax[n], Ay[n], Az[n]  (N samples, 100 Hz)
  │
  │ Step 2: DC Offset Removal (gravity removal)
  │   Ax_clean[n] = Ax[n] - mean(Ax)
  │   Ay_clean[n] = Ay[n] - mean(Ay)
  │   Az_clean[n] = Az[n] - mean(Az)
  ▼
Zero-mean axes
  │
  │ Step 3: Resultant Vector Magnitude
  │   accel_mag[n] = sqrt(Ax_clean[n]^2 + Ay_clean[n]^2 + Az_clean[n]^2)
  ▼
Resultant vector: 1 signal, N samples
  │
  ├──────────────────────────────────────┐
  │                                      │
  ▼ RAW PATH                             ▼ FILTERED PATH
  │                                      │
  │ Step 4a: Welch PSD                   │ Step 4b: Butterworth Bandpass
  │   psd_raw(f)                         │   2-8 Hz, Order 4, filtfilt
  │                                      │   (zero-phase, effective Order 8)
  │                                      ▼
  │                               Filtered resultant
  │                                      │
  │                                      │ Step 5: Welch PSD
  │                                      │   psd_filt(f)
  │                                      │
  │                                      │ Step 6: Peak Detection (2-8 Hz)
  │                                      │   argmax(psd_filt) in band
  │                                      │
  │                                      │ Step 7: Metrics Extraction
  │                                      │   RMS, Band Power, Peak PSD
  │                                      │
  │                                      │ Step 8: Input-Output Validation
  │                                      │   |peak_freq - PWM_freq| <= 0.5 Hz
  │                                      │   AND SNR >= 6 dB
  ▼                                      ▼
                Step 9: Visualization (4 Figures, 10 subplots)
```

#### Step 2: DC Offset Removal

The accelerometer measures gravity as a constant ~9.8 m/s^2 on the axis pointing down. Subtracting the mean per axis removes this DC component:

```python
ax_clean = ax - np.mean(ax)     # Removes gravity + sensor bias
ay_clean = ay - np.mean(ay)
az_clean = az - np.mean(az)
```

After this step, each axis oscillates around zero. Only dynamic acceleration (vibration/tremor) remains.

#### Step 3: Resultant Vector Magnitude

Combines three axes into a single scalar signal representing total vibration intensity at each time sample:

```python
accel_mag[n] = sqrt(ax_clean[n]^2 + ay_clean[n]^2 + az_clean[n]^2)
```

This makes the analysis orientation-independent — tremor is detected regardless of how the sensor is mounted.

Note: the magnitude is always >= 0 (it is a Euclidean norm). The raw resultant is NOT symmetric around zero. Symmetry is restored after bandpass filtering (Step 4b) which removes the DC component introduced by the norm operation.

#### Step 4b: Butterworth Bandpass Filter

```
Filter type:     Butterworth (maximally flat passband)
Order:           4 (per pass)
Passband:        2-8 Hz
Application:     scipy.signal.filtfilt (forward-backward)
Effective order: 8 (filtfilt doubles the order)
Phase shift:     Zero (filtfilt cancels phase distortion)
```

Why 2-8 Hz instead of the clinical 3-7 Hz? The Butterworth filter has gradual roll-off. At the -3 dB cutoff frequencies, the signal is attenuated by ~30%. By setting the filter edges at 2 and 8 Hz, the clinical band of 3-7 Hz falls well within the passband where attenuation is negligible.

#### Step 5: Welch PSD (Power Spectral Density)

Welch's method estimates the power spectrum by averaging periodograms of overlapping windowed segments:

```
Window length:       4 seconds = 400 samples (at 100 Hz)
Overlap:             50% = 200 samples
Window function:     Hann (scipy default)
Frequency resolution: 1 / 4s = 0.25 Hz
```

Frequency resolution calculation:

```
df = fs / N_window = 100 Hz / 400 samples = 0.25 Hz
```

This means the PSD has a data point every 0.25 Hz: 0, 0.25, 0.50, ..., 49.75, 50.0 Hz.

Number of segments for a 120-second recording:

```
Total samples:  12,000
Segment length: 400
Hop size:       200 (50% overlap)
Segments:       (12,000 - 400) / 200 + 1 = 59 segments
```

Averaging 59 segments reduces the variance of the PSD estimate.

**Output units:**
- PSD: (m/s^2)^2/Hz — power spectral density
- Plots display PSD in dB: Power_dB = 10 * log10(PSD_linear)

#### Step 6: Peak Detection

The dominant frequency is found by locating the maximum of the filtered PSD within the 2-8 Hz analysis band:

```python
rest_mask = (freq >= 2.0) & (freq <= 8.0)
peak_idx = np.argmax(psd_filt[rest_mask])
dominant_freq = freq[rest_mask][peak_idx]
peak_psd = psd_filt[rest_mask][peak_idx]
```

Since log10 is monotonically increasing, the peak in linear PSD and the peak in dB PSD occur at the same frequency.

#### Step 7: Metrics

| Metric | Formula | Units | Meaning |
|--------|---------|-------|---------|
| RMS Amplitude | sqrt(mean(x_filt^2)) | m/s^2 | Overall vibration intensity in tremor band |
| Mean Amplitude | mean(\|x_filt\|) | m/s^2 | Average absolute vibration |
| Max Amplitude | max(\|x_filt\|) | m/s^2 | Peak instantaneous vibration |
| Dominant Freq | argmax(PSD) in 2-8 Hz | Hz | Strongest frequency component |
| Peak PSD | max(PSD) in 2-8 Hz | (m/s^2)^2/Hz | Power density at dominant frequency |
| Band Power | integral(PSD, 2-8 Hz) | (m/s^2)^2 | Total power in tremor band |
| Peak SNR | 10*log10(peak/noise_floor) | dB | Peak prominence above in-band noise |
| Noise Floor | mean(PSD excl. peak +/-1 bin) | (m/s^2)^2/Hz | Average noise level in tremor band |

**RMS vs Resultant Vector:**
- Resultant vector: spatial combination (3 axes → 1 value per sample)
- RMS: temporal summary (N samples → 1 scalar value)

```
Ax, Ay, Az  →  sqrt(Ax^2 + Ay^2 + Az^2)  →  N values  →  sqrt(mean(x^2))  →  1 value
              (per sample)                                 (across all samples)
```

**Band Power** is computed by integrating the PSD over 2-8 Hz using the trapezoidal rule:

```python
band_power = np.trapz(psd_filt[rest_mask], freq[rest_mask])
```

This gives the total signal power within the tremor band in (m/s^2)^2.

#### Step 8: Input-Output Validation

The user enters the motor's PWM frequency (the expected vibration frequency). The system validates two conditions:

**Condition 1 — Frequency Match:**

```
|dominant_freq - PWM_freq| <= 0.5 Hz
```

The tolerance of 0.5 Hz equals 2x the frequency resolution (2 x 0.25 Hz). This is a double-sided tolerance band centered on the PWM frequency.

**Condition 2 — In-Band SNR (Peak Quality):**

```
SNR = 10 * log10(peak_PSD / noise_floor) >= 6 dB
```

The in-band SNR measures whether the detected peak is a real signal or just the tallest point in a flat noise spectrum. The noise floor is computed as the mean PSD across all bins in the 2-8 Hz band, excluding the peak bin and its immediate neighbors (+/-1 bin, to account for spectral leakage). A threshold of 6 dB means the peak must be at least 4x stronger than the average noise level in the band.

**Combined Validation:**

```
PASS:  frequency match AND SNR >= 6 dB
FAIL:  either condition not met
```

When validation fails, the system reports the specific reason:
- `freq mismatch` — peak is at the wrong frequency
- `weak peak` — peak is at the right frequency but not prominent enough
- `freq + weak peak` — both conditions failed

#### Step 9: Visualization

The analyzer produces 4 figures with 10 subplots across separate tabs:

**Figure 1 — Filter Characteristics (2 subplots):**
- Fig 1.1: Bode Magnitude — shows filter gain vs frequency for both single-pass and filtfilt
- Fig 1.2: Bode Phase — shows filtfilt achieves zero phase across all frequencies

**Figure 2 — Time Domain Analysis (3 subplots):**
- Fig 2.1: Raw resultant vector magnitude with RMS value
- Fig 2.2: Filtered resultant (2-8 Hz) with Hilbert envelope and RMS value
- Fig 2.3: Overlay of raw vs filtered for visual comparison

**Figure 3 — Frequency Domain Analysis (3 subplots):**
- Fig 3.1: PSD full range (0-20 Hz) — raw and filtered, with peak marker
- Fig 3.2: PSD zoomed (1-12 Hz) — filtered PSD with PWM frequency line and +/-0.5 Hz tolerance band
- Fig 3.3: Metrics and validation summary table (text) — includes SNR, noise floor, and fail reason

**Figure 4 — Zoomed Time Domain (2 subplots):**
- Fig 4.1: Filtered signal zoomed to a 3-second window from mid-recording, with Hilbert envelope, numbered rising zero-crossing markers, and cycle count — displays "Cycles: N | N/3s = X.XX Hz (PSD: Y.YY Hz)" for direct visual verification of the detected frequency
- Fig 4.2: Raw vs filtered overlay on the same 3-second window — shows how the bandpass filter extracts the motor vibration from the raw signal

---

## Quick Start

### Option A: Using System Manager (recommended)

```bash
# On RPI 4 — runs motor + recorder together, then analyzer
python3 sys_manager.py
```

### Option B: Running Scripts Individually

```bash
# Terminal 1: Start motor
python3 motor_control.py

# Terminal 2: Start recorder
python3 rpi_usb_recorder_v2.py

# After recording completes — on PC or RPI:
python3 offline_analyzer.py
```

### Option C: Running Each Script Standalone

```bash
# Motor control (interactive CLI)
python3 motor_control.py
# Commands: "hz 5", "40" (duty%), "stop", "quit"

# Recorder (auto-detects serial port)
python3 rpi_usb_recorder_v2.py
# Or specify port: python3 rpi_usb_recorder_v2.py /dev/ttyUSB0

# Offline analyzer (GUI)
python3 offline_analyzer.py
# Load CSV → Enter PWM frequency → Click "Load CSV Data"
```

---

## Dependencies

### RPI 4 / PC (Python 3)

```
numpy
scipy
matplotlib
mplcursors
tkinter (usually included with Python)
RPi.GPIO (RPI only — for motor_control.py)
pyserial (for rpi_usb_recorder_v2.py)
```

### ESP32 (Arduino)

```
Adafruit MPU6050
Adafruit Unified Sensor
Adafruit SSD1306
Adafruit GFX
Wire (built-in)
```

---

## Data Flow Summary

```
MPU6050                ESP32                    RPI Recorder           Offline Analyzer
───────                ─────                    ────────────           ────────────────
Accel X,Y,Z  ──I2C──→ Read registers    ──→   ser.readline()   ──→  Load CSV
(raw LSB)              Convert to m/s^2        Validate 4 cols       DC offset removal
                       Subtract offsets         Write to CSV          Resultant vector
                       Stuck detection                                Bandpass 2-8 Hz
                       Format CSV line                                Welch PSD
                       Serial.printf()  ──UART──→                    Peak detection
                       (100 Hz, 115200 baud)                          Validation
                                                                      Plot results
```
