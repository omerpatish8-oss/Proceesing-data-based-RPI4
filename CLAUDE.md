# CLAUDE.md - AI Assistant Guide for Tremor Data Acquisition System

## Project Overview

This is a **Parkinson's disease tremor data acquisition and analysis system** using:
- **ESP32** microcontroller with MPU6050 IMU sensor for data collection
- **Raspberry Pi 4** for data recording and offline analysis
- **Python** signal processing tools for tremor classification

The system captures accelerometer/gyroscope data at 100 Hz, implements research-validated signal processing, and classifies tremors as Rest (Parkinsonian) or Essential (Postural).

## Quick Start Commands

```bash
# Data recording (on RPI4 with ESP32 connected)
python3 rpi_usb_recorder_v2.py

# Offline tremor analysis (GUI)
python3 offline_analyzer.py

# Validate data quality
python3 validate_data_quality.py

# Motor control (interactive)
python3 motor_control.py
```

## Codebase Structure

```
Proceesing-data-based-RPI4/
├── esp32_usb_serial_safe.ino   # ESP32 firmware (Arduino C++)
├── rpi_usb_recorder_v2.py      # RPI data recorder (Python)
├── offline_analyzer.py         # Tremor analysis GUI (Python)
├── validate_data_quality.py    # Data validation tool (Python)
├── motor_control.py            # L298N motor driver control (Python)
├── main_gui.py                 # Hebrew GUI framework (Python, stub)
├── tremor_cycle*.csv           # Sample tremor data files
├── README.md                   # Complete system documentation
├── SIGNAL_PROCESSING_CHAIN.md  # Signal processing details (Hebrew/English)
├── ANALYZER_IMPROVEMENTS.md    # Offline analyzer design doc
├── DATA_QUALITY_REPORT.md      # Validation report
└── TEST_RESULTS.md             # Test analysis results
```

## Key Components

### 1. ESP32 Firmware (`esp32_usb_serial_safe.ino`)

**Purpose:** Sample MPU6050 sensor at 100 Hz, transmit via USB Serial

**Key concepts:**
- **State machine:** IDLE → RECORDING → PAUSED → WAITING_NEXT → FINISHED
- **Stopwatch timing:** Accumulates time across pause/resume (timestamps stay continuous)
- **Sensor safety:** Detects frozen sensors (15 identical readings), auto-resets
- **Hardware filter:** MPU6050 built-in 21 Hz low-pass filter (anti-aliasing)

**Protocol messages:**
- `START_RECORDING`, `CYCLE,N`, `PAUSE_CYCLE`, `RESUME_CYCLE`, `END_RECORDING`
- `ERROR_SENSOR_STUCK`, `ERROR_SENSOR_LOST`, `SENSOR_RESET,N`

**Data format:** `Timestamp,Ax,Ay,Az,Gx,Gy,Gz` (ms, m/s², m/s², m/s², °/s, °/s, °/s)

### 2. RPI Recorder (`rpi_usb_recorder_v2.py`)

**Purpose:** Receive ESP32 data, validate, and save to CSV + log files

**Key features:**
- Parses protocol messages and sensor data
- Validates 7-column CSV format
- Detects connection timeouts (5 seconds)
- Creates per-cycle CSV and LOG files in `tremor_data/`

**Configuration:**
```python
DEFAULT_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
CONNECTION_TIMEOUT = 5.0
EXPECTED_COLUMNS = 7
```

### 3. Offline Analyzer (`offline_analyzer.py`)

**Purpose:** Research-based tremor analysis with GUI visualization

**Signal processing pipeline:**
1. Load CSV, extract Ax, Ay, Az (gyroscope ignored - motor artifact concerns)
2. Remove DC offset per axis (gravity removal): `ax_clean = ax - mean(ax)`
3. Calculate resultant vector: `sqrt(ax² + ay² + az²)`
4. Identify highest energy axis automatically
5. Apply Butterworth order 4 bandpass filters:
   - Combined: 3-12 Hz
   - Rest tremor: 3-7 Hz (Parkinsonian)
   - Essential tremor: 6-12 Hz (Postural)
6. Zero-phase filtering with `filtfilt()` (no phase distortion)
7. PSD analysis using Welch's method (4s window, 50% overlap)
8. Classify: power_ratio > 2.0 = Rest, < 0.5 = Essential, else Mixed

**Important constants:**
```python
FS = 100.0              # Sampling rate (Hz)
FILTER_ORDER = 4        # Butterworth filter order
FREQ_REST_LOW = 3.0     # Rest tremor: 3-7 Hz
FREQ_REST_HIGH = 7.0
FREQ_ESSENTIAL_LOW = 6.0  # Essential tremor: 6-12 Hz
FREQ_ESSENTIAL_HIGH = 12.0
```

### 4. Data Validator (`validate_data_quality.py`)

**Purpose:** Validate CSV files per README protocol

**Checks performed:**
- 7-column CSV format (Timestamp,Ax,Ay,Az,Gx,Gy,Gz)
- Positive integer timestamps
- Numeric sensor values
- Timestamp consistency (~10ms intervals)
- Sensor freeze detection (15 consecutive identical readings)
- Sample count (~12,000 for 120s @ 100Hz)

### 5. Motor Controller (`motor_control.py`)

**Purpose:** Control L298N motor driver for tremor simulation

**GPIO pins:**
- ENA (PWM): GPIO18
- IN1: GPIO23
- IN2: GPIO24

## Development Guidelines

### Python Code Style

- Use `#!/usr/bin/env python3` shebang
- Document functions with docstrings
- Use type hints where appropriate
- Constants in UPPER_CASE at module level
- Classes use CamelCase, functions use snake_case

### Signal Processing Conventions

1. **Always use `filtfilt()` for zero-phase filtering** - Critical for clinical accuracy
2. **Remove DC offset before filtering** - `signal_clean = signal - np.mean(signal)`
3. **Use Butterworth order 4** - Research-validated, flat passband
4. **PSD with Welch's method** - 4-second window, 50% overlap for tremor analysis
5. **Accelerometer focus** - Gyroscope data excluded due to motor artifact concerns

### ESP32 Firmware Guidelines

- Maintain 100 Hz sampling rate (10ms intervals)
- Use stopwatch-style timing for pause/resume continuity
- Reset sensor on freeze detection (15 identical readings)
- Send protocol messages for all state transitions
- Hardware filter: MPU6050_BAND_21_HZ (anti-aliasing)

### Data File Conventions

**CSV format:**
```csv
# Cycle: 1
# Start Time: 2026-01-21 14:15:23
# Sample Rate: 100 Hz
Timestamp,Ax,Ay,Az,Gx,Gy,Gz
0,0.580,-0.200,-1.230,22.360,5.810,0.170
10,0.582,-0.198,-1.228,22.358,5.808,0.168
```

**Timestamps:** Milliseconds since cycle start, continuous across pause/resume

**Units:**
- Ax, Ay, Az: m/s² (acceleration, includes gravity)
- Gx, Gy, Gz: °/s (angular velocity)

## Common Tasks

### Adding a New Filter Band

In `offline_analyzer.py`:
```python
# Create filter (example: 4-8 Hz)
FREQ_NEW_LOW = 4.0
FREQ_NEW_HIGH = 8.0
b_new, a_new = butter(FILTER_ORDER,
                      [FREQ_NEW_LOW/nyquist, FREQ_NEW_HIGH/nyquist],
                      btype='band')
# Apply with zero-phase
signal_filtered = filtfilt(b_new, a_new, signal_clean)
```

### Modifying Sampling Rate

1. **ESP32:** Change `SAMPLE_RATE_HZ` and `SAMPLE_INTERVAL_MS`
2. **RPI Recorder:** Update metadata comments (optional)
3. **Offline Analyzer:** Update `FS` constant

### Adding New Protocol Messages

1. **ESP32:** Add `Serial.println("NEW_MESSAGE")` in appropriate state
2. **RPI Recorder:** Add handler in main loop:
```python
if "NEW_MESSAGE" in line:
    # Handle message
    if log_file:
        log_event(log_file, "INFO", "New message received")
    continue
```

### Extending Validation

In `validate_data_quality.py`, add check in `validate()` method:
```python
# Example: Check acceleration range
if abs(ax) > 40 or abs(ay) > 40 or abs(az) > 40:
    self.log_warning(f"Line {line_num}: Acceleration out of ±4g range")
```

## Hardware Architecture

### ESP32 Connections
```
MPU6050:        I2C Bus 0 (Wire)
  - SDA → GPIO 21
  - SCL → GPIO 22
  - Address: 0x68

SSD1306 OLED:   I2C Bus 1 (Wire1)
  - SDA → GPIO 18
  - SCL → GPIO 19
  - Address: 0x3C

Controls:
  - Button → GPIO 13 (INPUT_PULLUP)
  - Green LED → GPIO 15
  - Red LED → GPIO 2
```

### Raspberry Pi Connections
```
ESP32 USB → /dev/ttyUSB0 (115200 baud)
L298N Motor Driver:
  - ENA → GPIO 18 (PWM)
  - IN1 → GPIO 23
  - IN2 → GPIO 24
```

## Dependencies

### Python (RPI)
```bash
pip3 install pyserial numpy scipy matplotlib pandas mplcursors
```

- `pyserial` - USB serial communication
- `numpy` - Numerical computing
- `scipy` - Signal processing (butter, filtfilt, welch, hilbert)
- `matplotlib` - Visualization
- `pandas` - CSV handling (optional)
- `mplcursors` - Interactive plot cursors
- `tkinter` - GUI (usually pre-installed)

### Arduino (ESP32)
- Adafruit_MPU6050
- Adafruit_Sensor
- Adafruit_GFX
- Adafruit_SSD1306
- Wire.h

## Testing

### Validate Data Quality
```bash
python3 validate_data_quality.py
```

### Check Sample Rate
```bash
# Count samples (expect ~12,000 for 120s)
grep -v "^#" tremor_data/tremor_cycle1_*.csv | wc -l

# View first 10 lines
head -10 tremor_data/tremor_cycle1_*.csv
```

### Serial Port Troubleshooting
```bash
# List ports
ls /dev/ttyUSB*

# Fix permissions
sudo chmod 666 /dev/ttyUSB0

# Permanent fix
sudo usermod -a -G dialout $USER
```

## Research References

This implementation is based on peer-reviewed research:

1. **MDPI Clinical Medicine 2073** - MPU6050 tremor classification methodology
   - https://www.mdpi.com/2077-0383/14/6/2073

2. **MDPI Sensors 2763 (ELENA Project)** - ESP32 + MPU6050 clinical validation
   - https://www.mdpi.com/1424-8220/25/9/2763

## Important Notes for AI Assistants

1. **Never modify gyroscope processing** - Deliberately excluded due to motor artifacts
2. **Preserve zero-phase filtering** - Use `filtfilt()`, not `lfilter()` for clinical accuracy
3. **Keep 100 Hz sampling rate** - Research-validated, matches filter design
4. **Maintain Butterworth order 4** - Standard in tremor research literature
5. **Don't change frequency bands** without clinical justification:
   - Rest tremor: 3-7 Hz (Parkinsonian)
   - Essential tremor: 6-12 Hz (Postural)
6. **Timestamps must be continuous** - Pause/resume preserves time continuity
7. **Hebrew comments exist** - SIGNAL_PROCESSING_CHAIN.md has Hebrew explanations

## Version Info

- **System Version:** 3.1
- **Offline Analyzer:** v3.1 (accelerometer-focused, dual-view)
- **RPI Recorder:** v3 (error handling, validation, logging)
- **Last Updated:** 2026-01-27
