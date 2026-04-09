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
| `esp32_usb_serial_safe_V2.ino` | ESP32 | Samples MPU6050 at 100 Hz, transmits via USB Serial |
| `rpi_usb_recorder_v2.py` | RPI 4 | Receives UART data, validates, writes CSV files |
| `motor_control.py` | RPI 4 | Controls DC motor via L298N driver (PWM on GPIO18) |
| `offline_analyzer_exp.py` | PC/RPI 4 | Offline analyzer: bandpass per-axis, PSD, DPR, 7 figure tabs, no pass/fail |
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

### Power Budget Table

The system has two independent power domains: **5V USB** (RPI4 + ESP32 subsystem) and **12V external** (motor subsystem). Below is a per-component breakdown with voltage, current, and calculations derived from datasheets and circuit values.

#### Power Domain 1: 5V USB (Data Acquisition)

| # | Component | Role | Input Voltage | Operating Voltage | Current (Typical) | Current (Max) | Calculation / Notes |
|---|-----------|------|---------------|-------------------|-------------------|---------------|---------------------|
| 1 | **Raspberry Pi 4 Model B** | Host processor: DSP, file I/O, GUI, motor PWM | 5.1V USB-C | 5.1V (onboard regulators to 3.3V/1.8V) | ~600 mA | 1.2 A | Datasheet typical idle. Excludes USB peripherals. Powered by USB-C 5.1V/3A PSU |
| 2 | **ESP32 DevKit V1** | Sampling controller: I2C sensor read, UART transmit, state machine | 5V (USB from RPI4) | 3.3V (onboard AMS1117-3.3 LDO) | ~50 mA | ~80 mA | Active mode, Wi-Fi/BT disabled, dual-core 240 MHz. LDO dropout: V_in(5V) → V_out(3.3V), P_LDO = (5 - 3.3) × 0.05 = 85 mW. USB draw from RPI4: ~50 mA at 5V |
| 3 | **MPU6050** | 3-axis accelerometer (±2g, 16-bit ADC, I2C) | 3.3V (from ESP32) | 3.3V | 3.9 mA | 3.9 mA | Datasheet: all sensors active (accel + gyro), DLPF at 21 Hz. I2C @ 400 kHz Fast Mode. Gyro not used by FW but not explicitly disabled |
| 4 | **SSD1306 OLED 0.96"** | Status display: countdown timer, cycle number, state | 3.3V (from ESP32) | 3.3V | ~20 mA | ~20 mA | 128×64 pixels, I2C @ 400 kHz (Wire1, address 0x3C). Current depends on pixels lit; 20 mA is typical with mixed content |
| 5 | **Green LED** (GPIO 15) | Status: blink in IDLE (1s), fast blink in RECORDING (200ms), solid in FINISHED | 3.3V (ESP32 GPIO) | ~2.0V (V_fwd) | **5.9 mA** | 5.9 mA | I = (V_GPIO - V_fwd) / R = (3.3V - 2.0V) / 220Ω = **1.3V / 220Ω = 5.9 mA** |
| 6 | **Red LED** (GPIO 2) | Status: blink in PAUSED (800ms), blink in WAITING_NEXT (500ms), solid on error | 3.3V (ESP32 GPIO) | ~1.8V (V_fwd) | **6.8 mA** | 6.8 mA | I = (V_GPIO - V_fwd) / R = (3.3V - 1.8V) / 220Ω = **1.5V / 220Ω = 6.8 mA** |
| 7 | **Push Button** (GPIO 13) | User input: start/pause/resume recording | 3.3V pull-up | — | 0 mA (open) / **0.70 mA** (pressed) | 0.70 mA | External 4.7kΩ pull-up to 3.3V. When pressed (GPIO LOW): I = 3.3V / 4.7kΩ = **0.70 mA**. FW also enables internal pull-up (~45kΩ), parallel: 4.7k ∥ 45k ≈ 4.25kΩ → 0.78 mA. Momentary press only |

**ESP32 subsystem total (worst-case, all indicators ON simultaneously):**

```
I_ESP32_total = I_ESP32 + I_MPU6050 + I_OLED + I_LED_green + I_LED_red + I_button
             = 50 + 3.9 + 20 + 5.9 + 6.8 + 0.7
             = 87.3 mA (at 3.3V rail)

USB current drawn from RPI4 (5V):
  I_USB = (3.3V × 87.3 mA) / (5V × η_LDO)     where η_LDO ≈ 3.3/5 = 66%
        ≈ 87.3 mA × (3.3/5) / (3.3/5) = 87.3 mA (LDO is linear, I_in ≈ I_out)
  P_USB = 5V × 87.3 mA = 436.5 mW
  P_LDO_waste = (5V - 3.3V) × 87.3 mA = 148.4 mW (dissipated as heat in AMS1117)
```

**RPI4 total power (including ESP32 USB peripheral):**

```
I_RPI4_PSU = I_RPI4 + I_ESP32_USB = 600 + 87.3 ≈ 687 mA (typical)
P_RPI4_total = 5.1V × 687 mA ≈ 3.5 W
```

#### Power Domain 2: 12V External (Motor Simulation)

| # | Component | Role | Input Voltage | Operating Voltage | Current (Typical) | Current (Max) | Calculation / Notes |
|---|-----------|------|---------------|-------------------|-------------------|---------------|---------------------|
| 8 | **12V DC Power Supply** | Powers motor driver and motor | 220V AC mains | 12V DC output | ~300 mA | 2+ A | Must supply motor stall current + L298N quiescent. Recommended: 12V/2A minimum |
| 9 | **L298N Motor Driver** | H-bridge: controls motor direction and speed via PWM | 12V (from PSU) | 12V motor / 5V logic (onboard 78M05 regulator) | ~36 mA (quiescent) | 2 A (per channel) | Saturation voltage drop: V_CE(sat) ≈ 1.0V per transistor × 2 (high + low side) = **~2V total drop**. Motor sees: V_motor = (12V - 2V) × Duty% = 10V × Duty%. Logic inputs (IN1, IN2, ENA) from RPI4 GPIO 3.3V — L298N threshold: V_IH = 2.3V, so 3.3V is valid HIGH |
| 10 | **DC Gearbox Motor (JGA25-370)** | Generates vibration via eccentric mass (40g) rotation | 12V (via L298N) | Effective: (12 - 2) × Duty% | ~40 mA (no-load) | 2 A (stall) | 625 RPM max at 12V. Typical running current with eccentric mass at mid-speed (~5 Hz, 50% duty): ~200-400 mA |
| 11 | **RPI4 GPIO → L298N** | Control signals: PWM (GPIO 18), Direction (GPIO 23, 24) | 3.3V (RPI4 GPIO) | 3.3V | < 1 mA total | ~2 mA | L298N input impedance is high (~40kΩ). I per pin ≈ 3.3V / 40kΩ ≈ 0.08 mA. Three pins total: ~0.25 mA. Well within RPI4 GPIO max (16 mA/pin) |

**Motor subsystem power at typical operating point (5 Hz tremor simulation, ~50% duty):**

```
V_motor_effective = (12V - 2V) × 50% = 5.0V average
I_motor ≈ 300 mA (estimated with 40g eccentric load)
P_motor = 12V × 300 mA = 3.6 W (from supply)
P_L298N_loss = 2V × 300 mA = 0.6 W (heat in H-bridge)
P_motor_mechanical = 5.0V × 300 mA = 1.5 W (delivered to motor)
P_L298N_quiescent = 12V × 36 mA = 0.43 W
```

#### System Power Summary

| Power Domain | Source | Voltage | Typical Current | Typical Power | Notes |
|-------------|--------|---------|----------------|--------------|-------|
| Data Acquisition | USB-C PSU → RPI4 | 5.1V | ~690 mA | ~3.5 W | RPI4 + ESP32 (USB) + all peripherals |
| Motor Simulation | External DC PSU | 12V | ~340 mA | ~4.1 W | L298N + motor at ~50% duty |
| **System Total** | **Two supplies** | — | — | **~7.6 W** | Excludes monitor/keyboard if attached to RPI4 |

#### LED Resistor Calculation Detail

```
Green LED (GPIO 15, R = 220Ω):
  V_GPIO = 3.3V (ESP32 output HIGH)
  V_fwd  = 2.0V (typical green LED forward voltage)
  I_LED  = (3.3 - 2.0) / 220 = 5.9 mA
  P_R    = I² × R = (5.9 mA)² × 220Ω = 7.7 mW
  P_LED  = I × V_fwd = 5.9 mA × 2.0V = 11.8 mW

Red LED (GPIO 2, R = 220Ω):
  V_GPIO = 3.3V (ESP32 output HIGH)
  V_fwd  = 1.8V (typical red LED forward voltage)
  I_LED  = (3.3 - 1.8) / 220 = 6.8 mA
  P_R    = I² × R = (6.8 mA)² × 220Ω = 10.2 mW
  P_LED  = I × V_fwd = 6.8 mA × 1.8V = 12.2 mW
```

Both LEDs operate well within the ESP32 GPIO maximum source current of 40 mA per pin, and well within typical LED ratings (20 mA max).

#### Button Pull-Up Calculation Detail

```
External pull-up resistor: R = 4.7kΩ to 3.3V
FW also enables internal pull-up: R_int ≈ 45kΩ (ESP32 typical)
Parallel combination: R_eff = (4.7k × 45k) / (4.7k + 45k) = 4.26kΩ

Button released (GPIO reads HIGH):
  No current flows through pull-up (no path to GND)
  GPIO reads 3.3V → digitalRead = HIGH → no action

Button pressed (GPIO reads LOW):
  Pull-up connects 3.3V through R to GND via button
  I = 3.3V / 4.26kΩ = 0.78 mA
  P = 3.3V × 0.78 mA = 2.6 mW (momentary, only while pressed)

Debounce: FW uses 500 ms software debounce (lastDebounceTime check)
```

---

## Pipeline Walkthrough

### Stage 1: Sensor Acquisition (`esp32_usb_serial_safe_V2.ino`)

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

These offsets are in **m/s^2** — the Adafruit MPU6050 library converts raw LSB register values to SI units internally, so `a.acceleration.z` is already in m/s^2 before the firmware applies calibration.

**What the Z offset means physically:** At rest on a flat surface (Z axis pointing up), the sensor reports ~10.86 m/s^2 on Z — this is the sum of true gravitational acceleration (~9.81 m/s^2) plus the sensor's intrinsic bias (~1.05 m/s^2). The calibration offset `aZ_off = 1.046231` removes only the sensor bias, bringing the stationary Z reading back to ~9.81 m/s^2 (gravity). It does **not** remove gravity — that is handled later by the offline analyzer's bandpass filter (2-8 Hz), which inherently rejects DC (0 Hz) including gravity. The X and Y offsets (~0.30 and ~0.02 m/s^2) similarly remove small biases on the horizontal axes, where the true stationary value should be 0 m/s^2.

#### Sensor Safety

The firmware monitors sensor health continuously and has two system-level safety nets:

| Check | Interval | Threshold | Action |
|-------|----------|-----------|--------|
| Stuck detection | Every sample | 15 identical readings (delta < 0.001 m/s^2) | Auto-reset sensor |
| Read failure | Every sample | 5 consecutive failures | Auto-reset sensor |
| Connection loss | Every 500 ms | I2C ACK missing or 2s since last read | Auto-reset sensor |
| **I2C bus timeout** | **Every I2C transaction** | **10 ms** | **Unblocks Wire library, returns error** |
| **Hardware watchdog (WDT)** | **Every loop() iteration** | **5 seconds** | **Auto-reboots ESP32** |

##### I2C Bus Timeout (Wire.setTimeOut)

The ESP32 `Wire` library can hang indefinitely if the I2C bus is disrupted mid-transaction (e.g., SDA or SCL wire disconnects while the MPU6050 is transmitting). In this scenario, `mpu.getEvent()` never returns, and all software-level safety checks (stuck detection, read failure counting, health checks) become unreachable.

`Wire.setTimeOut(10)` sets a 10 ms hardware timeout on every I2C transaction. If any I2C read/write does not complete within 10 ms, the Wire library returns an error instead of blocking forever. This allows `mpu.getEvent()` to fail gracefully, which then triggers the existing `failedReads` counter and `resetSensor()` flow.

**Why 10 ms:** A full MPU6050 I2C read at 400 kHz takes ~0.5 ms. 10 ms provides 20× headroom while staying under the 10 ms sample interval. The timeout is re-applied in `resetSensor()` after I2C bus reinitialization.

##### Hardware Watchdog Timer (WDT)

The ESP-IDF task watchdog provides a last line of defense against **any** hang — known or unknown. It is initialized in `setup()` with a 5-second timeout and the main task is registered. Every `loop()` iteration calls `esp_task_wdt_reset()` to "pet" the watchdog. If `loop()` fails to pet the watchdog for 5 consecutive seconds (due to any cause — I2C hang, USB buffer deadlock, memory corruption), the ESP32 automatically reboots and returns to `setup()`.

**Why 5 seconds:** Long enough to accommodate worst-case normal operation (I2C timeout + sensor reset + display update ≈ 0.5s), short enough to limit data loss to at most 500 samples (5s × 100 Hz).

##### Stuck Detection — Rationale and Relationship to Sensor Noise Floor

The stuck detection logic compares each new reading against the previous one on all three axes:

```cpp
bool stuck = (abs(ax - lastAx) < STUCK_THRESHOLD &&   // 0.001 m/s^2
              abs(ay - lastAy) < STUCK_THRESHOLD &&
              abs(az - lastAz) < STUCK_THRESHOLD);
```

If all three axes change by less than `STUCK_THRESHOLD = 0.001 m/s^2` for `MAX_STUCK = 15` consecutive samples, the firmware declares the sensor stuck and triggers a hardware reset (I2C bus close → 150 ms wait → reinitialize).

**Why 0.001 m/s^2 works — the sensor's noise floor guarantees variation:**

The MPU6050 at ±2g range has:
- **ADC resolution:** 16384 LSB/g → 1 LSB ≈ 0.000598 m/s^2 (~2 LSB ≈ 0.001 m/s^2)
- **Output noise (datasheet):** ~0.01g RMS ≈ **0.098 m/s^2 RMS** — this is the total RMS noise at the accelerometer output as specified by InvenSense

The stuck threshold (0.001 m/s^2) is roughly **98× smaller** than the sensor's output noise floor (0.098 m/s^2). This is the key insight: a properly functioning MPU6050 will **always** produce sample-to-sample fluctuations well above 0.001 m/s^2, even when perfectly stationary on a table. The noise is an inherent property of the MEMS sensing element and the internal ADC — it physically cannot produce identical readings on consecutive samples.

To put it concretely: the stuck threshold sits at ~2 LSB, while the sensor's natural noise spans ~160 LSB RMS. These two values occupy completely different orders of magnitude, which is why the stuck detector has zero false-positive risk on a healthy sensor.

Therefore, if readings are truly identical (delta < 0.001 m/s^2 on all axes) for 15 consecutive samples at 100 Hz (150 ms), the ADC has almost certainly locked up — a known failure mode of MEMS accelerometers where the I2C data registers return stale (frozen) values. This can occur due to I2C bus glitches, power supply transients, or internal sensor state corruption. The 15-sample threshold provides an additional safety margin: even if a single sample happened to coincidentally match the previous one, 15 consecutive matches across all three axes simultaneously is physically implausible for a functioning sensor.

**Relationship to the ±2g range:** The ±2g range (±19.6 m/s^2) provides the highest ADC resolution (16384 LSB/g), which maximizes sensitivity for small tremor amplitudes (typical Parkinsonian tremor: 0.1–2.0 m/s^2). The tradeoff is that the ±2g range also has the lowest output noise in absolute terms (~0.098 m/s^2), but this is still nearly 100× above the stuck threshold — so the detection remains reliable. At wider ranges (±4g, ±8g, ±16g) the noise floor increases further, making stuck detection even easier, but at the cost of reduced tremor sensitivity.

Reset procedure: close I2C bus, wait 150 ms, reinitialize I2C at 400 kHz with 10 ms timeout, wait 50 ms, reinitialize MPU6050.

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
  → subprocess.Popen(["python3", "offline_analyzer_exp.py"])
```

### Stage 6: Offline Signal Processing (`offline_analyzer_exp.py`)

The offline analyzer is a Tkinter GUI application that loads a recorded CSV file and performs the full signal processing chain. It reports all metrics as informational values (no pass/fail judgment), uses independent per-axis filtering, and produces 7 figure tabs for tremor characterization.

#### Signal Processing Pipeline

The analyzer applies the bandpass filter directly to each raw axis — the bandpass inherently removes DC (gravity) since it has zero gain at 0 Hz. No prior mean subtraction is needed. Below is every step with the mathematical formulation and rationale.

##### Step 1: CSV Parsing

Raw data is loaded from the CSV file produced by the recorder:

```
Input:  Timestamp(ms), Ax(m/s^2), Ay(m/s^2), Az(m/s^2)
Output: t[n], Ax[n], Ay[n], Az[n]   (N samples at 100 Hz)
```

Timestamps are converted from milliseconds to seconds: `t[n] = Timestamp[n] / 1000`.

##### Step 2: Butterworth Bandpass Filter (2-8 Hz) — Per Axis

**What:** Apply a 4th-order Butterworth bandpass filter to **each raw axis independently** using zero-phase forward-backward filtering (filtfilt). No prior DC removal (mean subtraction) is needed — the bandpass has zero gain at 0 Hz, so it inherently removes gravity and any sensor bias.

**Math (filter design):**

```
Filter type:      Butterworth (maximally flat magnitude in passband)
Order:            4 (per single pass)
Passband:         [2 Hz, 8 Hz]
Normalized cutoffs: [2/50, 8/50] = [0.04, 0.16]   (Nyquist = Fs/2 = 50 Hz)

Ax_filt[n] = filtfilt(b, a, Ax[n])    # Filter raw Ax directly
Ay_filt[n] = filtfilt(b, a, Ay[n])    # Filter raw Ay directly
Az_filt[n] = filtfilt(b, a, Az[n])    # Filter raw Az directly
```

This single step accomplishes three things simultaneously:
1. **Removes DC (gravity):** The bandpass has no gain at 0 Hz, so the constant gravity component is eliminated automatically
2. **Removes high-frequency noise:** Everything above 8 Hz is attenuated
3. **Handles wrist rotation correctly:** Slow orientation changes (< 2 Hz) are rejected by the filter, unlike mean subtraction which assumes constant gravity projection

**filtfilt (zero-phase filtering):**

```
y[n] = filtfilt(b, a, x[n])
     = reverse( filter(b, a, reverse( filter(b, a, x[n]) ) ) )
```

The signal is filtered forward, then the result is reversed and filtered again. This:
- **Doubles the effective order** (4 -> 8), giving steeper roll-off
- **Cancels all phase distortion**, preserving exact timing of waveform features
- **Squares the magnitude response**: |H_eff(f)|^2 = |H(f)|^4

**Why 2-8 Hz instead of clinical 3-7 Hz?** The Butterworth filter has gradual roll-off at the cutoff frequencies. At the -3 dB points (2 and 8 Hz), the signal is attenuated by ~29%. With filtfilt the attenuation at cutoff doubles to -6 dB (~50%). By placing the filter edges at 2 and 8 Hz, the clinical tremor band of 3-7 Hz falls well within the passband where attenuation is negligible (< 0.1 dB).

##### Step 3: Resultant Vector from Filtered Axes

**What:** Combine the three **filtered** axes into a single scalar representing total vibration intensity.

**Math:**

```
result_filtered[n] = sqrt( Ax_filt[n]^2 + Ay_filt[n]^2 + Az_filt[n]^2 )
```

**Why after filtering (not before)?** The sqrt(x^2 + y^2 + z^2) operation is **nonlinear**. If applied to unfiltered data (which contains a large DC gravity offset), the nonlinearity distorts the signal and creates spurious frequency content. By filtering first, each axis is a clean zero-mean tremor oscillation, and the magnitude faithfully represents the 3D tremor envelope.

**Note:** The resultant vector is used only for the time-domain RMS metric. All frequency-domain analysis (PSD, FFT) operates on individual filtered axes.

##### Step 4: Welch PSD on Each Filtered Axis + Dominant Axis Selection

**What:** Estimate the power spectrum of **each filtered axis independently** using Welch's method (averaged periodograms of overlapping segments), then select the **dominant axis** — whichever has the highest PSD peak in the 2-8 Hz band.

**Math:**

```
# PSD on each filtered axis independently
f, PSD_Ax = welch(Ax_filt, Fs, nperseg=L, noverlap=L/2)
_, PSD_Ay = welch(Ay_filt, Fs, nperseg=L, noverlap=L/2)
_, PSD_Az = welch(Az_filt, Fs, nperseg=L, noverlap=L/2)

# Select dominant axis: whichever has the absolute max PSD peak in 2-8 Hz
rest_mask = (f >= 2.0) AND (f <= 8.0)
peaks = { X: max(PSD_Ax[rest_mask]), Y: max(PSD_Ay[rest_mask]), Z: max(PSD_Az[rest_mask]) }
dominant_axis = argmax(peaks)          # e.g., 'Y'
PSD_dominant = PSD_{dominant_axis}     # Use this axis for all freq-domain metrics
```

**Parameters:**

```
Segment length (L):     400 samples (4 seconds at 100 Hz)
Overlap:                50% = 200 samples
Window:                 Hann (scipy default)
Frequency resolution:   df = Fs / L = 100 / 400 = 0.25 Hz
Number of segments (K): (12000 - 400) / 200 + 1 = 59 (for 120s recording)
```

**Why PSD on individual axes (not on resultant)?** The resultant vector R = sqrt(x^2 + y^2 + z^2) is a **nonlinear** operation. Taking the PSD of R would introduce **frequency doubling artifacts** — spurious harmonics at 2x the true tremor frequency. By computing PSD on each linear (filtered) axis, we get a clean spectrum without mathematical distortion.

**Why select one dominant axis?** The axis with the strongest PSD peak carries the clearest tremor signal. Using its PSD exclusively for frequency-domain metrics (dominant freq, DPR, peak PSD) ensures these metrics are not diluted by noise from weaker axes.

**Output units:** (m/s^2)^2/Hz (power spectral density). Displayed in dB: `PSD_dB = 10 * log10(PSD)`.

##### Step 5: Peak Detection in 2-8 Hz Band

**What:** Find the dominant tremor frequency by locating the PSD maximum of the **dominant axis** within the analysis band.

**Math:**

```
rest_mask = (freq >= 2.0 Hz) AND (freq <= 8.0 Hz)
peak_idx  = argmax( PSD_dominant[rest_mask] )
f_dominant = freq[rest_mask][peak_idx]
PSD_peak   = PSD_dominant[rest_mask][peak_idx]
```

##### Step 6: Dominant Power Ratio (DPR)

**What:** The fraction of total in-band power that is concentrated in a small window around the dominant frequency (+/-1 bin = +/-0.25 Hz, i.e. 3 bins / 0.75 Hz wide).

**Math:**

```
peak_power = trapz( PSD[peak-1 .. peak+1], freq[peak-1 .. peak+1] )
band_power = trapz( PSD[2-8 Hz],           freq[2-8 Hz]           )
DPR        = peak_power / band_power
```

Both numerator and denominator use trapezoidal integration (`np.trapz`), so both are in consistent units of (m/s^2)^2 (integrated power). The ratio is dimensionless.

**Why:** DPR answers: "What percentage of the tremor-band energy is concentrated at the dominant frequency?"

- **DPR close to 1.0 (100%)**: Nearly all energy is concentrated at a single frequency — strong, clean periodic signal
- **DPR close to 0**: Energy is spread evenly across the band — no dominant frequency, noise-like signal

##### Step 7: FFT Magnitude Spectrum (Full Recording)

**What:** Compute the discrete Fourier transform of the **raw dominant axis** (unfiltered) over the full recording and plot the magnitude spectrum. This reveals the full spectral content of the sensor signal, including components that the bandpass filter removes.

**Math:**

```
X[k] = SUM( x[n] * e^(-j*2*pi*k*n/N), n=0..N-1 )    (DFT)
|X[k]|_norm = |X[k]| / N                               (normalized magnitude)
f[k] = k * Fs / N                                       (frequency axis)
```

For a 120s recording at 100 Hz: N = 12,000 samples, giving frequency resolution:

```
df = Fs / N = 100 / 12000 = 0.00833 Hz
```

**Why FFT on the raw signal (not filtered)?** The Welch PSD (Step 4) and the filtered time-domain plots (Fig 2.2, Fig 4, Fig 5) already show the in-band content after filtering. The FFT on the raw signal serves a different purpose: it shows the full spectrum including DC offset, low-frequency drift, harmonics above 8 Hz, and any other out-of-band artifacts. This provides a complete before/after view when compared with the filtered PSD.

**Why include FFT in addition to Welch PSD?** The Welch PSD averages over segments, which smooths the spectrum and reduces variance but limits frequency resolution to 0.25 Hz (with 4s segments). The full-recording FFT provides 120x finer resolution (0.0083 Hz), revealing fine spectral structure like exact motor frequency, harmonics, and narrow sidebands that Welch averaging would blur together. The trade-off is higher variance (no averaging), but for a clean motor signal the peak is prominent enough.

**Note:** Only the one-sided spectrum (0 to Nyquist = 50 Hz) is computed using `np.fft.rfft` for real-valued input. The plot is zoomed to 0-12 Hz to show DC through the tremor band and its near harmonics.

##### Step 9: Spectrogram — Time-Frequency Analysis (STFT)

**What:** Compute a Short-Time Fourier Transform (STFT) spectrogram of the **raw dominant axis** (unfiltered) and display it as a heatmap showing how spectral content evolves over time.

**Math:**

```
STFT{x[n]}(m, k) = SUM( x[n] * w[n - mR] * e^(-j*2*pi*k*n/L), n )
Spectrogram(m, k) = |STFT(m, k)|^2    (power)
```

Where `w[n]` is a Hann window of length L, R is the hop size (L - overlap), and m is the time frame index.

**Parameters:**

```
Window length:      256 samples (2.56 seconds)
Overlap:            224 samples (87.5%)
Frequency range:    0-12 Hz
Color scale:        Power (dB)
```

**Why a spectrogram?** The PSD and FFT provide frequency information averaged over the entire recording. The spectrogram adds the time dimension, showing whether the dominant frequency is stable or drifting. For motor-driven vibration, the frequency should appear as a steady horizontal band. For real Parkinsonian tremor, the spectrogram would reveal intermittency (tremor appearing and disappearing) and frequency drift — clinically relevant characteristics that time-averaged methods cannot capture.

##### Step 8: Zoomed Time-Domain Analysis (Consecutive 5-Second Windows)

**What:** Extract two consecutive 5-second windows from the middle of the recording and analyze the **dominant axis** signal in each.

**Window placement:**

```
t_mid = t[N/2]                          (midpoint of recording)
Window A: [t_mid - 5s,  t_mid]          (Fig 4)
Window B: [t_mid,       t_mid + 5s]     (Fig 5)
```

**Cycle counting via rising zero-crossings:**

For each window, rising zero-crossings of the filtered signal are detected:

```
For each sample i where filt[i-1] < 0 AND filt[i] >= 0:
    frac = -filt[i-1] / (filt[i] - filt[i-1])          (linear interpolation)
    t_cross = t[i-1] + frac * (t[i] - t[i-1])          (precise crossing time)
    cycle_count += 1
```

The measured frequency from zero-crossing count:

```
f_measured = cycle_count / window_duration
```

This provides an independent time-domain frequency estimate that can be compared against the PSD peak frequency.

**Hilbert envelope:**

The analytic signal is computed via the Hilbert transform:

```
x_analytic[n] = x[n] + j * H{x[n]}
envelope[n]   = |x_analytic[n]|
```

The envelope traces the instantaneous amplitude of the oscillation, showing amplitude modulation over time. This reveals whether the tremor amplitude is steady or fluctuating within the 5-second window.

**Why two consecutive windows?** Comparing Window A and Window B (back-to-back) shows whether the tremor is stationary (stable frequency and amplitude) or non-stationary (drifting). For a motor-driven signal, both windows should show nearly identical cycle counts and envelope shapes. For real tremor, differences between windows may indicate tremor intermittency.

#### Visualization (7 Figures)

**Figure 1 — Filter Characteristics (2 subplots):**
- Fig 1.1: Bode Magnitude — filter gain vs frequency for single-pass and filtfilt
- Fig 1.2: Bode Phase — demonstrates filtfilt achieves zero phase

**Figure 2 — Dominant Axis Time Domain (2 broader subplots, 40-80s view):**
- Fig 2.1: Dominant axis raw signal (no DC removal — shows true sensor output including gravity offset)
- Fig 2.2: Dominant axis filtered (2-8 Hz) with Hilbert envelope

**Figure 3 — Frequency Domain Analysis (3 subplots, enlarged metrics):**
- Fig 3.1: PSD full range (0-20 Hz) — raw dominant axis (DC-removed for PSD only) vs filtered dominant axis, with peak marker
- Fig 3.2: PSD zoomed (1-12 Hz) — filtered PSD with PWM reference and deviation band
- Fig 3.3: Enlarged metrics panel — frequency info, DPR, amplitude metrics

**Figure 4 — Zoomed 5s Window A (2 subplots):**
- Fig 4.1: Dominant axis filtered signal with Hilbert envelope, numbered cycle markers, frequency from zero-crossing count
- Fig 4.2: Dominant axis raw vs filtered overlay on the same window

**Figure 5 — Zoomed 5s Window B (2 subplots):**
- Fig 5.1: Same as 4.1 but for the next consecutive 5 seconds
- Fig 5.2: Same as 4.2 but for the next consecutive 5 seconds

**Figure 6 — FFT Analysis (single full-width plot):**
- FFT magnitude of the raw (unfiltered) dominant axis, zoomed to 0-12 Hz, computed over the full 120s recording, with PWM reference line and peak annotation. Shows the full spectrum including out-of-band content

**Figure 7 — Spectrogram (single full-width plot):**
- STFT spectrogram of the raw (unfiltered) dominant axis, 0-12 Hz, showing time-frequency evolution across the full recording. Reveals whether the dominant frequency is stable or drifting over time

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
python3 offline_analyzer_exp.py
```

### Option C: Running Each Script Standalone

```bash
# Motor control (interactive CLI)
python3 motor_control.py
# Commands: "hz 5", "40" (duty%), "stop", "quit"

# Recorder (auto-detects serial port)
python3 rpi_usb_recorder_v2.py
# Or specify port: python3 rpi_usb_recorder_v2.py /dev/ttyUSB0

# Offline analyzer (GUI — informational metrics, no pass/fail)
python3 offline_analyzer_exp.py
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
(raw LSB)              Convert to m/s^2        Validate 4 cols       Bandpass 2-8 Hz per axis
                       Subtract offsets         Write to CSV          Resultant from filtered
                       Stuck detection                                PSD per axis (Welch)
                       Format CSV line                                Dominant axis selection
                       Serial.printf()  ──UART──→                    Metrics + FFT + Spectrogram
                       (100 Hz, 115200 baud)                          7 Figure Tabs
```
