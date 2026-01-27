# CLAUDE.md - AI Assistant Guidelines

This file provides guidance for AI assistants working on this codebase.

## Project Overview

**Tremor Data Acquisition System** - A medical research system for capturing and analyzing Parkinson's disease tremor data using Raspberry Pi 4 and ESP32 with MPU6050 IMU sensor.

### Core Purpose
- High-frequency (100 Hz) sensor data collection for tremor analysis
- Clinical tremor classification (Rest tremor vs Essential tremor)
- Research-grade signal processing with validated methods

## Repository Structure

```
Proceesing-data-based-RPI4/
├── esp32_usb_serial_safe.ino   # ESP32 firmware (Arduino/C++)
├── rpi_usb_recorder_v2.py      # Raspberry Pi data recorder
├── offline_analyzer.py         # Tremor analysis tool (main analyzer)
├── offline_analyzer_withacce.py# Alternative accelerometer-focused analyzer
├── validate_data_quality.py    # Data validation script
├── tremor_analysis_assessment.py # Assessment utilities
├── main_gui.py                 # GUI dashboard (Hebrew interface)
├── motor_control.py            # Motor control module (stub)
├── README.md                   # Comprehensive documentation
├── SIGNAL_PROCESSING_CHAIN.md  # Signal processing documentation
├── ANALYZER_IMPROVEMENTS.md    # Analyzer design documentation
├── DATA_QUALITY_REPORT.md      # Data quality analysis
├── TEST_RESULTS.md             # Test results documentation
└── tremor_*.csv                # Sample data files
```

## Key Technical Specifications

### Hardware
- **Sensor:** MPU6050 (6-axis IMU: accelerometer + gyroscope)
- **MCU:** ESP32 (sensor interface)
- **Processor:** Raspberry Pi 4 (data recording)
- **Display:** SSD1306 OLED (128x64)
- **Communication:** USB Serial at 115200 baud

### Sampling & Data
- **Sample Rate:** 100 Hz (10ms intervals)
- **Recording Duration:** 120 seconds per cycle (configurable)
- **Cycles:** 2 cycles by default
- **Data Format:** CSV with columns: `Timestamp,Ax,Ay,Az,Gx,Gy,Gz`
- **Units:**
  - Timestamp: milliseconds
  - Acceleration (Ax,Ay,Az): m/s²
  - Gyroscope (Gx,Gy,Gz): °/s

### Signal Processing
- **Hardware Filter:** MPU6050 DLPF at 21 Hz (anti-aliasing)
- **Software Filters:** Butterworth order 4 bandpass
  - Combined tremor: 3-12 Hz
  - Rest tremor: 3-7 Hz
  - Essential tremor: 6-12 Hz
- **Method:** Zero-phase filtering with `filtfilt()`
- **PSD:** Welch's method (4-second window, 50% overlap)

### Tremor Classification
```python
power_ratio = rest_power / essential_power
if power_ratio > 2.0:    # Rest Tremor (Parkinsonian)
elif power_ratio < 0.5:  # Essential Tremor (Postural)
else:                    # Mixed Tremor
```

## Development Guidelines

### Python Code Style
- Use Python 3 with type hints where appropriate
- Follow PEP 8 conventions
- Use docstrings for classes and functions
- Configuration constants at top of file (ALL_CAPS naming)

### Key Dependencies (Python)
```bash
# Data acquisition
pip install pyserial

# Analysis
pip install numpy scipy matplotlib pandas
```

### Arduino/C++ Style (ESP32)
- Use `const` for configuration values
- State machine pattern for recording states
- Sensor safety: freeze detection (15 consecutive identical samples)
- Auto-reset on sensor failure

### Important Conventions

1. **Accelerometer-Focused Analysis**
   - Gyroscope data is collected but typically excluded from tremor analysis
   - Reason: Motor rotation artifacts contaminate gyroscope readings
   - Use resultant vector magnitude: `√(Ax² + Ay² + Az²)`

2. **Gravity Removal**
   - Remove DC offset before filtering: `signal_clean = signal - mean(signal)`
   - This removes the constant gravitational component

3. **Zero-Phase Filtering**
   - Always use `filtfilt()` not `filter()` for tremor analysis
   - Preserves timing of tremor events (critical for clinical analysis)

4. **Data Validation**
   - Always validate CSV format (7 columns)
   - Check for timestamp continuity
   - Detect sensor freeze events

## Common Tasks

### Running the Data Recorder
```bash
python3 rpi_usb_recorder_v2.py
# Or specify port:
python3 rpi_usb_recorder_v2.py /dev/ttyUSB0
```

### Running the Tremor Analyzer
```bash
python3 offline_analyzer.py
# GUI will open - click "Load CSV Data" to analyze
```

### Validating Data Quality
```bash
python3 validate_data_quality.py tremor_data/tremor_cycle1_*.csv
```

### USB Permissions (if needed)
```bash
sudo chmod 666 /dev/ttyUSB0
# Or permanently: sudo usermod -a -G dialout $USER
```

## Protocol Messages (ESP32 ↔ RPI)

| Message | Direction | Meaning |
|---------|-----------|---------|
| `START_RECORDING` | ESP32 → RPI | Recording started |
| `CYCLE,N` | ESP32 → RPI | Cycle N started |
| `PAUSE_CYCLE` | ESP32 → RPI | Recording paused |
| `RESUME_CYCLE` | ESP32 → RPI | Recording resumed |
| `END_RECORDING` | ESP32 → RPI | Cycle complete |
| `ALL_COMPLETE` | ESP32 → RPI | All cycles finished |
| `ERROR_SENSOR_STUCK` | ESP32 → RPI | Sensor freeze detected |
| `SENSOR_RESET,N` | ESP32 → RPI | Sensor reset #N |

## Testing & Validation

### Expected Results
- ~12,000 samples per 2-minute cycle
- Timestamp intervals ~10ms (±5ms tolerance)
- No sensor freeze events in normal operation
- Rest tremor: typically 4-6 Hz, RMS > 0.1 m/s²
- Essential tremor: typically 6-12 Hz

### Validation Checks
1. Column count (expect 7)
2. Timestamp monotonicity
3. Numeric value parsing
4. Sample rate consistency
5. Sensor freeze detection (15 identical samples)

## File Output Structure

```
tremor_data/
├── tremor_cycle1_YYYYMMDD_HHMMSS.csv  # Sensor data
├── tremor_cycle1_YYYYMMDD_HHMMSS.log  # Event log
├── tremor_cycle2_YYYYMMDD_HHMMSS.csv
└── tremor_cycle2_YYYYMMDD_HHMMSS.log
```

## Research References

This system is validated against peer-reviewed research:
1. [MDPI Clinical Medicine 2073](https://www.mdpi.com/2077-0383/14/6/2073) - MPU6050 tremor classification
2. [MDPI Sensors 2763 (ELENA Project)](https://www.mdpi.com/1424-8220/25/9/2763) - ESP32 + MPU6050 validation

## Gotchas & Common Issues

1. **Serial Port Permissions**
   - Error: "Permission denied /dev/ttyUSB0"
   - Fix: `sudo chmod 666 /dev/ttyUSB0` or add user to dialout group

2. **ESP32 Hardware Filter**
   - The 21 Hz DLPF is applied IN HARDWARE before data reaches Python
   - Cannot analyze frequencies above ~21 Hz

3. **Calibration Offsets**
   - Hardcoded in ESP32 firmware (lines 76-77)
   - Must recalibrate if using different sensor unit

4. **Pause/Resume Timestamps**
   - Timestamps are continuous across pause/resume
   - No gaps in timestamp sequence

5. **GUI Dependency**
   - `offline_analyzer.py` requires tkinter (usually pre-installed)
   - On headless systems, use matplotlib's Agg backend

## Architecture Decisions

### Why USB Serial (not GPIO UART)?
- Simpler wiring
- No voltage level conversion needed
- More reliable for high-speed data

### Why 100 Hz Sample Rate?
- Adequate for tremor analysis (3-12 Hz)
- Meets Nyquist criterion with margin
- Matches research paper methodology

### Why Butterworth Order 4?
- Flat passband (no ripple)
- Standard in clinical research
- Good balance of sharpness vs phase distortion

### Why Dual Analysis (Axis + Resultant)?
- Axis-specific: Shows tremor directionality
- Resultant: Direction-independent severity measure
- Together: Complete clinical picture

## Version History

- **v3.1** (Current): Research-based analyzer with accelerometer focus
- **v3**: Error handling, validation, connection timeout detection
- **v2**: One CSV per cycle, continuous timestamps
- **v1**: Initial implementation

## Contact & Support

GitHub Issues: https://github.com/omerpatish8-oss/Proceesing-data-based-RPI4/issues
