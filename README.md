# Tremor Data Acquisition System - RPI4 & ESP32

A robust data acquisition system for capturing and analyzing tremor/motion data using Raspberry Pi 4 and ESP32 with MPU6050 sensor. Designed for medical research and Parkinson's disease tremor analysis.

---

## 🎯 Project Overview

This system enables:
- **High-frequency data collection** at 100 Hz sampling rate
- **Real-time sensor monitoring** with automatic error detection
- **Cycle-based recording** with pause/resume capability
- **Data quality validation** and comprehensive error logging
- **USB Serial communication** between ESP32 and Raspberry Pi

---

## 🔧 Hardware Requirements

### Components
- **Raspberry Pi 4** (data recorder and processor)
- **ESP32 Development Board** (sensor interface)
- **MPU6050** IMU sensor (accelerometer + gyroscope)
- **SSD1306 OLED Display** (128x64, for ESP32 feedback)
- **Push Button** (for start/pause/resume control)
- **LEDs** (Green and Red for status indication)
- **USB Cable** (ESP32 to RPI4 connection)

### Wiring (ESP32)
```
MPU6050:
  - SDA → GPIO 21
  - SCL → GPIO 22
  - VCC → 3.3V
  - GND → GND

SSD1306 Display:
  - SDA → GPIO 18
  - SCL → GPIO 19
  - VCC → 3.3V
  - GND → GND

Control:
  - Button → GPIO 13 (with internal pull-up)
  - Green LED → GPIO 15
  - Red LED → GPIO 2
```

---

## 📊 System Architecture

### Data Pipeline

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   MPU6050   │──I²C──│    ESP32    │──USB──│   RPI4      │
│   Sensor    │       │  (Sampler)  │       │ (Recorder)  │
└─────────────┘       └─────────────┘       └─────────────┘
      │                      │                      │
   100 Hz              Preprocessing           Validation
   Reading             Error Detection         Error Logging
                      Freeze Detection         CSV Output
                      Auto-reset              Log Files
```

### Software Components

#### 1. **ESP32 Firmware** (`esp32_usb_serial_safe.ino`)
**Responsibilities:**
- Sample MPU6050 at 100 Hz (10ms intervals)
- Apply calibration offsets
- Detect sensor freeze (15 consecutive identical readings)
- Auto-reset sensor on failures
- Manage recording state machine (IDLE → RECORDING → PAUSED → FINISHED)
- Transmit data via USB Serial at 115200 baud

**Key Features:**
- **Stopwatch-style timing**: Accumulates recording time across pause/resume
- **Sensor health monitoring**: Detects stuck sensor, read failures, connection loss
- **Automatic recovery**: Resets sensor on error with up to 3 retry attempts
- **User control**: Single button for start/pause/resume

**Protocol Messages:**
| Message | Direction | Purpose |
|---------|-----------|---------|
| `START_RECORDING` | ESP32 → RPI | Recording started |
| `CYCLE,<N>` | ESP32 → RPI | Cycle number N started |
| `PAUSE_CYCLE` | ESP32 → RPI | Recording paused |
| `RESUME_CYCLE` | ESP32 → RPI | Recording resumed |
| `END_RECORDING` | ESP32 → RPI | Cycle complete |
| `ALL_COMPLETE` | ESP32 → RPI | All cycles finished |
| `ERROR_SENSOR_STUCK` | ESP32 → RPI | 15 constant samples detected |
| `ERROR_SENSOR_LOST` | ESP32 → RPI | Sensor connection lost |
| `ERROR_READ_FAILED` | ESP32 → RPI | Sensor read failed |
| `SENSOR_RESET,<N>` | ESP32 → RPI | Sensor reset #N occurred |
| `SENSOR_RESET_OK` | ESP32 → RPI | Reset successful |
| `SENSOR_RESET_FAILED` | ESP32 → RPI | Reset failed |
| `RESETS,<N>` | ESP32 → RPI | Total resets summary |

**Data Format (CSV over Serial):**
```
Timestamp,Ax,Ay,Az,Gx,Gy,Gz
0,0.580,-0.200,-1.230,22.360,5.810,0.170
10,0.582,-0.198,-1.228,22.358,5.808,0.168
...
```
- **Timestamp**: Milliseconds since cycle start (continuous across pause/resume)
- **Ax, Ay, Az**: Acceleration (m/s²) with calibration applied
- **Gx, Gy, Gz**: Gyroscope (°/s) with calibration applied

---

#### 2. **RPI Python Recorder** (`rpi_usb_recorder_v2.py` v3)

**Responsibilities:**
- Receive data from ESP32 via USB Serial
- Parse protocol messages and sensor data
- Validate data format (7 columns, numeric values)
- Detect connection timeouts (5s no-data warning)
- Create CSV files (one per cycle)
- Generate detailed event logs
- Track data quality metrics

**Key Features (v3):**
- ✅ **ESP32 Error Handling**: Parses and logs 8 error event types
- ✅ **Connection Monitoring**: 5-second timeout detection
- ✅ **Data Validation**: Format checking (7 columns, numeric types)
- ✅ **Error Logging**: Timestamped event log per cycle
- ✅ **Metadata Tracking**: Sensor resets, error counts, validation issues
- ✅ **Quality Reporting**: Comprehensive cycle summaries

**Configuration:**
```python
DEFAULT_PORT = '/dev/ttyUSB0'     # USB serial port
BAUD_RATE = 115200                 # Must match ESP32
OUTPUT_FOLDER = 'tremor_data'      # Output directory
CONNECTION_TIMEOUT = 5.0           # Seconds before warning
EXPECTED_COLUMNS = 7               # CSV format validation
```

**Core Functions:**

**`record_data(port)`**
- Main recording loop
- Handles serial communication
- Processes protocol messages
- Validates and writes data
- Manages file I/O

**`log_event(log_file, event_type, message)`**
- Writes timestamped events to log file
- Format: `[YYYY-MM-DD HH:MM:SS] TYPE: message`

**`validate_data_line(line)`**
- Validates CSV format
- Checks column count (7 expected)
- Verifies timestamp is positive integer
- Ensures all sensor values are numeric
- Returns `(True, None)` or `(False, error_message)`

**Error Handling:**
```python
# Connection timeout
if elapsed_since_data > CONNECTION_TIMEOUT:
    log_event(log_file, "WARNING", "Connection timeout")

# Data validation
is_valid, error_msg = validate_data_line(line)
if not is_valid:
    log_event(log_file, "VALIDATION_ERROR", error_msg)
    csv_file.write(f"# INVALID: {line}\n")

# ESP32 errors
if "ERROR_SENSOR_STUCK" in line:
    log_event(log_file, "ERROR", "Sensor stuck - 15 constant samples")
```

---

#### 3. **GUI Dashboard** (`main_gui.py`)

**Responsibilities:**
- Provide Hebrew language interface
- Launch motor control module
- Trigger ESP32 communication
- Initiate data analysis

**Status:** Framework implemented, requires module integration:
- `motor_control.py` (stub)
- `esp32_comm.py` (not yet created)
- `data_processor.py` (not yet created)

---

## 📂 Output Files

### File Structure
Each recording cycle generates two files:
```
tremor_data/
├── tremor_cycle1_20260119_183000.csv    # Sensor data
├── tremor_cycle1_20260119_183000.log    # Event log
├── tremor_cycle2_20260119_183215.csv    # Next cycle data
└── tremor_cycle2_20260119_183215.log    # Next cycle log
```

### CSV File Format
```csv
# Cycle: 1
# Start Time: 2026-01-19 18:30:00
# Sample Rate: 100 Hz
# Format: Timestamp(ms),Ax(m/s²),Ay,Az,Gx(°/s),Gy,Gz
Timestamp,Ax,Ay,Az,Gx,Gy,Gz
0,0.580,-0.200,-1.230,22.360,5.810,0.170
10,0.582,-0.198,-1.228,22.358,5.808,0.168
20,0.584,-0.196,-1.226,22.356,5.806,0.166
...
```

**CSV Features:**
- Metadata header with cycle info
- Continuous timestamps (gaps removed from pause/resume)
- Calibrated sensor values
- Invalid data flagged with `# INVALID:` prefix

### Log File Format
```
[2026-01-19 18:30:00] INFO: Cycle 1 started
[2026-01-19 18:30:15] INFO: Recording paused at 1500 samples
[2026-01-19 18:30:20] INFO: Recording resumed at 1500 samples
[2026-01-19 18:30:45] ERROR: Sensor stuck - 15 constant samples detected
[2026-01-19 18:30:45] RESET: Sensor reset #1
[2026-01-19 18:30:46] INFO: Sensor reset successful
[2026-01-19 18:32:00] INFO: Recording complete - 12000 samples
[2026-01-19 18:32:00] SUMMARY: Duration: 120.0s
[2026-01-19 18:32:00] SUMMARY: Sensor resets: 1
[2026-01-19 18:32:00] SUMMARY: Errors: 1
[2026-01-19 18:32:00] SUMMARY: Validation errors: 0
```

**Log Event Types:**
- `INFO`: Normal operations (start, pause, resume, complete)
- `WARNING`: Connection timeouts, minor issues
- `ERROR`: Sensor errors, read failures
- `VALIDATION_ERROR`: Data format issues
- `RESET`: Sensor reset events
- `CRITICAL`: Unrecoverable errors
- `SUMMARY`: Final statistics

---

## 🚀 Usage

### Setup

1. **Flash ESP32:**
   ```bash
   # Using Arduino IDE:
   # - Install libraries: Adafruit_MPU6050, Adafruit_SSD1306, Adafruit_GFX
   # - Select board: ESP32 Dev Module
   # - Upload esp32_usb_serial_safe.ino
   ```

2. **Connect Hardware:**
   - Wire MPU6050 and SSD1306 to ESP32
   - Connect button to GPIO 13
   - Connect ESP32 to RPI4 via USB

3. **Verify USB Connection:**
   ```bash
   # Check available ports
   ls /dev/ttyUSB*
   # Should show: /dev/ttyUSB0 (or similar)

   # If permission denied:
   sudo chmod 666 /dev/ttyUSB0
   ```

### Running a Recording Session

1. **Start Python Recorder:**
   ```bash
   cd /path/to/Proceesing-data-based-RPI4
   python3 rpi_usb_recorder_v2.py
   ```

   Or specify port:
   ```bash
   python3 rpi_usb_recorder_v2.py /dev/ttyUSB0
   ```

2. **Start Recording on ESP32:**
   - Press button on ESP32
   - Display shows: "Recording 1"
   - Green LED blinks rapidly
   - RPI console shows: "Recording to: tremor_data/tremor_cycle1_*.csv"

3. **Pause/Resume (Optional):**
   - Press button during recording
   - Display shows: "PAUSED"
   - Red LED blinks
   - Press again to resume
   - **Timestamps remain continuous!**

4. **Complete Cycle:**
   - Wait for 2 minutes (auto-complete)
   - Or press button to end early
   - Console shows cycle summary

5. **Multiple Cycles:**
   - Press button to start next cycle
   - System configured for 2 cycles by default
   - Each cycle creates separate CSV + log files

### Console Output Example
```
╔════════════════════════════════════╗
║ ESP32 USB Recorder v3              ║
║ + Error handling & validation     ║
╚════════════════════════════════════╝

📁 Created folder: tremor_data/
📍 Using port: /dev/ttyUSB0
📡 Connecting to /dev/ttyUSB0...
✅ Connected!
🎬 Waiting for ESP32 to start recording...

📝 Recording to: tremor_data/tremor_cycle1_20260119_183000.csv
📄 Log file: tremor_data/tremor_cycle1_20260119_183000.log
   Cycle: 1 | Rate: 100 Hz
   (Pause/Resume will use SAME file)

   📊   100 samples |    1.0s
   📊   200 samples |    2.0s
   ...
   📊 12000 samples |  120.0s

✅ Cycle 1 Complete!
   Total samples: 12000
   Duration: 120.0s
   Sensor resets: 0
   Errors: 0
   Validation errors: 0
   CSV: tremor_data/tremor_cycle1_20260119_183000.csv
   Log: tremor_data/tremor_cycle1_20260119_183000.log
============================================================
```

---

## 🔍 Data Analysis

### Quick Verification

**Check CSV:**
```bash
# View metadata header
head -10 tremor_data/tremor_cycle1_*.csv

# Count samples (should be ~12,000 for 2 minutes at 100Hz)
grep -v "^#" tremor_data/tremor_cycle1_*.csv | wc -l
```

**Check Log:**
```bash
# View complete event log
cat tremor_data/tremor_cycle1_*.log

# Check for errors
grep "ERROR" tremor_data/tremor_cycle1_*.log
```

**Check Data Quality:**
```bash
# View cycle summary
tail -10 tremor_data/tremor_cycle1_*.log
```

### Python Analysis (Example)
```python
import pandas as pd

# Load data (skip comment lines)
df = pd.read_csv('tremor_data/tremor_cycle1_20260119_183000.csv',
                 comment='#')

# Basic statistics
print(df.describe())

# Check sample rate consistency
df['dt'] = df['Timestamp'].diff()
print(f"Mean interval: {df['dt'].mean():.2f} ms (expected: 10 ms)")

# Plot acceleration
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.plot(df['Timestamp']/1000, df['Ax'], label='Ax')
plt.plot(df['Timestamp']/1000, df['Ay'], label='Ay')
plt.plot(df['Timestamp']/1000, df['Az'], label='Az')
plt.xlabel('Time (s)')
plt.ylabel('Acceleration (m/s²)')
plt.legend()
plt.grid(True)
plt.show()
```

---

## 🛡️ Error Handling & Reliability

### Sensor Freeze Detection
**Problem:** Sensor may "freeze" and return identical values
**Solution:**
- ESP32 monitors last 15 samples
- Detects constant values (threshold: 0.001 m/s²)
- Auto-resets sensor when freeze detected
- RPI logs event: `ERROR: Sensor stuck - 15 constant samples`

### Connection Timeout
**Problem:** USB connection may drop or ESP32 may stop transmitting
**Solution:**
- RPI monitors data reception
- Alerts after 5 seconds of no data
- Logs warning: `WARNING: Connection timeout - no data for 5.3s`
- Resets timeout counter on resume

### Data Validation
**Problem:** Serial data may be corrupted or malformed
**Solution:**
- Validates 7-column format
- Checks timestamp is positive integer
- Verifies all values are numeric
- Flags invalid data with `# INVALID:` prefix
- Logs validation errors with original line

### Sensor Reset Tracking
**Problem:** Need visibility into sensor reliability
**Solution:**
- ESP32 sends `SENSOR_RESET,<N>` on each reset
- RPI tracks cumulative reset count
- Displays in cycle summary
- Logs all reset events with timestamps

### Graceful Shutdown
**Problem:** Data loss on unexpected termination
**Solution:**
- Catches `KeyboardInterrupt` (Ctrl+C)
- Flushes CSV data on every write
- Closes files properly in `finally` block
- Saves current state before exit

---

## ⚙️ Configuration

### ESP32 Settings
Edit `esp32_usb_serial_safe.ino`:
```cpp
const long TARGET_DURATION = 120000; // Recording duration (ms)
const int SAMPLE_RATE_HZ = 100;      // Sampling frequency
const int MAX_CYCLES = 2;            // Number of cycles
const int MAX_STUCK = 15;            // Freeze detection threshold

// Calibration offsets (from sensor calibration)
float gX_off = 22.36, gY_off = 5.81, gZ_off = 0.17;
float aX_off = 0.58, aY_off = -0.20, aZ_off = -1.23;
```

### RPI Settings
Edit `rpi_usb_recorder_v2.py`:
```python
DEFAULT_PORT = '/dev/ttyUSB0'     # Change if using different port
BAUD_RATE = 115200                # Must match ESP32
OUTPUT_FOLDER = 'tremor_data'     # Output directory
CONNECTION_TIMEOUT = 5.0          # Timeout warning (seconds)
EXPECTED_COLUMNS = 7              # CSV validation
```

---

## 🐛 Troubleshooting

### No Serial Port Found
```bash
# Check USB connection
lsusb
# Should show ESP32 device

# Check permissions
ls -l /dev/ttyUSB0
sudo chmod 666 /dev/ttyUSB0

# Add user to dialout group (permanent fix)
sudo usermod -a -G dialout $USER
# Log out and back in
```

### Connection Timeout Errors
**Symptoms:** Frequent "No data received for 5.0s" warnings
**Causes:**
- Poor USB cable
- Power supply issues
- ESP32 buffer overflow

**Solutions:**
- Use high-quality USB cable
- Use powered USB hub
- Check ESP32 power supply (5V/500mA minimum)

### Sensor Resets
**Symptoms:** Multiple `SENSOR_RESET` messages
**Causes:**
- Loose I²C connections
- Electromagnetic interference
- Sensor overheating

**Solutions:**
- Check MPU6050 wiring
- Use shielded cables
- Add bypass capacitors (0.1µF near sensor VCC)
- Ensure adequate ventilation

### Invalid Data Errors
**Symptoms:** `VALIDATION_ERROR` in logs
**Causes:**
- Serial buffer corruption
- Baud rate mismatch
- Electromagnetic interference

**Solutions:**
- Verify BAUD_RATE matches on both sides (115200)
- Use shorter/better USB cable
- Check for ground loops

---

## 📦 Dependencies

### ESP32 (Arduino)
- `Adafruit_MPU6050`
- `Adafruit_Sensor`
- `Adafruit_GFX`
- `Adafruit_SSD1306`
- `Wire.h` (I²C)

### Raspberry Pi (Python 3)
- `pyserial` - USB serial communication
- Standard library: `datetime`, `os`, `sys`, `time`

**Installation:**
```bash
pip3 install pyserial
```

---

## 📈 Performance Specifications

| Metric | Specification |
|--------|--------------|
| Sampling Rate | 100 Hz (10ms intervals) |
| Data Throughput | ~7 KB/s per channel |
| Recording Duration | 120 seconds per cycle (configurable) |
| Cycle Count | 2 cycles (configurable) |
| Total Samples | ~12,000 per cycle |
| CSV Size | ~500 KB per cycle |
| Timestamp Precision | 1 millisecond |
| Connection Timeout | 5 seconds detection |
| Freeze Detection | 15 consecutive identical samples |

---

## 🔐 Data Integrity Features

✅ **Continuous Timestamps**: Pause/resume doesn't create time gaps
✅ **One CSV Per Cycle**: Clean data segmentation
✅ **Metadata Headers**: Self-documenting CSV files
✅ **Event Logging**: Complete audit trail
✅ **Data Validation**: Format checking on every line
✅ **Error Tracking**: Quality metrics per cycle
✅ **Graceful Shutdown**: No data loss on interruption
✅ **Flush on Write**: Immediate disk persistence

---

## 📝 Version History

### v3 (Current)
- Added ESP32 error event parsing
- Implemented connection timeout detection
- Added CSV data validation (7-column format)
- Created per-cycle error logging system
- Added metadata tracking (resets, errors, validation)
- Enhanced cycle summaries with quality metrics

### v2
- Fixed one CSV per cycle (pause/resume bug)
- Implemented continuous timestamps
- Added cycle number tracking

### v1
- Initial implementation
- Basic serial communication
- Simple CSV output

---

## 🎓 Educational Use

This system is designed for:
- **Medical Research**: Parkinson's disease tremor analysis
- **Biomechanics Studies**: Motion capture and analysis
- **Engineering Education**: Embedded systems, data acquisition
- **Sensor Fusion**: IMU data processing

---

## 📧 Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/omerpatish8-oss/Proceesing-data-based-RPI4/issues

---

## 📄 License

[Add your license information here]

---

## 🙏 Acknowledgments

- Adafruit for excellent sensor libraries
- ESP32 community for robust hardware platform
- Raspberry Pi Foundation for accessible computing

---

**Last Updated:** 2026-01-19
**Version:** 3.0
**Status:** Production Ready ✅
