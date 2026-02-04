# Tremor Data Acquisition System - RPI4 & ESP32

A data acquisition system for capturing and analyzing rest tremor (3-7 Hz) data using Raspberry Pi 4 and ESP32 with MPU6050 sensor. Designed for Parkinson's disease rest tremor detection and validation.

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

**Data Acquisition System:**
- **Raspberry Pi 4** (data recorder and processor)
- **ESP32 Development Board** (sensor interface)
- **MPU6050** IMU sensor (accelerometer + gyroscope)
- **SSD1306 OLED Display** (128x64, for ESP32 feedback)
- **Push Button** (for start/pause/resume control)
- **LEDs** (Green and Red for status indication)
- **USB Cable** (ESP32 to RPI4 connection)

**Tremor Simulation System (Optional - for validation):**
- **L298N Motor Driver** (H-bridge motor controller)
- **DC Motor** (12V, for generating controlled oscillations)
- **12V Power Supply** (for motor driver)
- **Wiring:** GPIO connections from RPI4 to L298N

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

L298N Motor Driver (Optional - Raspberry Pi 4):
  - ENA (PWM) → GPIO 18
  - IN1 → GPIO 23
  - IN2 → GPIO 24
  - 12V supply → External power
  - Motor → OUT1/OUT2
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

### ESP32 Internal Architecture

#### State Machine Implementation

The ESP32 firmware implements a **finite state machine** with 5 states:

```
┌──────────────────────────────────────────────────────────────┐
│                     ESP32 STATE MACHINE                       │
└──────────────────────────────────────────────────────────────┘

    ┌─────────┐
    │  IDLE   │◄──────────────┐
    └────┬────┘               │
         │ Button Press       │
         ▼                    │ All Cycles Complete
    ┌──────────┐              │
    │RECORDING │              │
    └────┬─────┘              │
         │ Button Press       │
         ▼                    │
    ┌─────────┐               │
    │ PAUSED  │               │
    └────┬────┘               │
         │ Button Press       │
         ▼ (Resume)           │
    ┌──────────┐              │
    │RECORDING │              │
    └────┬─────┘              │
         │ Duration Complete  │
         ▼                    │
    ┌────────────┐            │
    │WAITING_NEXT│────────────┤
    └─────┬──────┘            │
          │ Button Press      │
          └──►Back to IDLE    │
              or RECORDING    │
                              │
    ┌─────────┐               │
    │FINISHED │───────────────┘
    └─────────┘
```

**State Definitions:**

| State | Behavior | LED | Display | Next State Trigger |
|-------|----------|-----|---------|-------------------|
| **IDLE** | Waiting to start | Green (slow blink, 1s) | "READY\nPress button" | Button → RECORDING |
| **RECORDING** | Active sampling at 100Hz | Green (fast blink, 200ms) | "Recording N\n<time>" | Button → PAUSED or Duration complete → WAITING_NEXT |
| **PAUSED** | Timer frozen, no sampling | Red (blink, 800ms) | "PAUSED N\n<time>" | Button → RECORDING (resume) |
| **WAITING_NEXT** | Cycle complete, ready for next | Red (fast blink, 500ms) | "DONE\nPress for Next" | Button → RECORDING (next cycle) or Max cycles → FINISHED |
| **FINISHED** | All cycles complete | Green (solid) | "FINISHED\nAll cycles done" | None (terminal state) |

**State Variables:**
```cpp
enum State { IDLE, RECORDING, PAUSED, WAITING_NEXT, FINISHED };
State currentState = IDLE;

int currentCycle = 0;              // Current cycle number
const int MAX_CYCLES = 2;          // Total cycles to record

unsigned long segmentStartTime;    // When current segment started
unsigned long accumulatedTime;     // Total recording time so far
unsigned long currentTotalTime;    // Real-time total (accumulated + current segment)
```

**Stopwatch Timing Logic:**
```cpp
// On START_RECORDING:
segmentStartTime = millis();       // Mark start of this segment
accumulatedTime = 0;               // Reset accumulated time
currentTotalTime = 0;              // Reset total

// During RECORDING (every loop):
currentTotalTime = accumulatedTime + (millis() - segmentStartTime);

// On PAUSE:
accumulatedTime += (millis() - segmentStartTime);  // Save elapsed time
currentTotalTime = accumulatedTime;                 // Freeze at current total

// On RESUME:
segmentStartTime = millis();       // Start new segment
// accumulatedTime stays the same - preserves previous time
// currentTotalTime continues from accumulated value
```

**Example Timing Scenario:**
```
Action          | segmentStartTime | accumulatedTime | currentTotalTime
----------------|------------------|-----------------|------------------
START           | 1000             | 0               | 0
Recording (5s)  | 1000             | 0               | 5000
PAUSE at 5s     | 1000             | 5000            | 5000 (frozen)
Wait 10s...     | 1000             | 5000            | 5000 (still frozen)
RESUME          | 16000            | 5000            | 5000 (continues)
Recording (3s)  | 16000            | 5000            | 8000
END at 8s       | 16000            | 5000            | 8000

Result: 8 seconds of actual recording time, timestamps 0-8000ms continuous
```

---

#### I²C Hardware Communication Protocol

The ESP32 communicates with two I²C devices on separate buses:

**I²C Bus 1 (Wire)** - MPU6050 Sensor
- **SDA:** GPIO 21
- **SCL:** GPIO 22
- **Speed:** 400 kHz (Fast Mode)
- **Address:** 0x68 (MPU6050 default)

**I²C Bus 2 (Wire1)** - SSD1306 Display
- **SDA:** GPIO 18
- **SCL:** GPIO 19
- **Speed:** 400 kHz (Fast Mode)
- **Address:** 0x3C (SSD1306 default)

**MPU6050 Communication Sequence:**

```cpp
// 1. Initialization (setup)
Wire.begin(21, 22);                    // Initialize I²C on GPIO 21/22
Wire.setClock(400000);                 // Set 400kHz speed

mpu.begin();                           // Initialize MPU6050
mpu.setAccelerometerRange(MPU6050_RANGE_4_G);   // ±4g range
mpu.setGyroRange(MPU6050_RANGE_500_DEG);        // ±500°/s range
mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);     // 21Hz low-pass filter

// 2. Health Check (every 500ms during recording)
Wire.beginTransmission(0x68);          // Start I²C transaction to MPU6050
bool connected = (Wire.endTransmission() == 0);  // 0 = ACK received

// 3. Data Reading (every 10ms during recording)
sensors_event_t a, g, temp;
bool success = mpu.getEvent(&a, &g, &temp);     // Read all sensor data
// Internally sends I²C commands:
//   - Read register 0x3B-0x40 (14 bytes): accel + temp + gyro

// 4. Sensor Reset (on error)
Wire.end();                            // Close I²C bus
delay(150);                            // Wait for sensor to power down
Wire.begin(21, 22);                    // Reinitialize I²C
Wire.setClock(400000);
mpu.begin();                           // Reinitialize MPU6050
```

**I²C Transaction Example (Reading Acceleration):**
```
Master (ESP32)          Slave (MPU6050)
-------------------------------------------------
START condition      →
Device Address 0x68  → ACK
Register 0x3B (ACCEL_XOUT_H) → ACK
RESTART condition    →
Device Address 0x68  → ACK
                     ← ACCEL_XOUT_H data (8 bits)
ACK                  →
                     ← ACCEL_XOUT_L data (8 bits)
ACK                  →
                     ← ACCEL_YOUT_H data (8 bits)
... (6 bytes total for X, Y, Z)
STOP condition       →
```

**SSD1306 Display Communication:**
```cpp
// Initialization
Wire1.begin(18, 19);                   // Initialize I²C on GPIO 18/19
Wire1.setClock(400000);
display.begin(SSD1306_SWITCHCAPVCC, 0x3C);  // Initialize display at address 0x3C

// Update Display (every 1s)
display.clearDisplay();                // Clear frame buffer
display.setCursor(0, 0);
display.print("Recording 1");          // Write to buffer
display.display();                     // Send buffer to display via I²C
// Internally sends ~1KB of data to refresh entire 128x64 pixel screen
```

---

#### Recording Sequence - Complete Flow

Here's the detailed step-by-step sequence from power-on to data recording:

##### **Phase 1: System Initialization** (0-5 seconds)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ESP32 Boot                                                    │
└─────────────────────────────────────────────────────────────────┘
[0ms] Power applied to ESP32
[100ms] ESP32 bootloader starts
[500ms] Arduino setup() begins
[500ms] Serial.begin(115200) - USB serial initialized
[500ms] Print banner to serial:
         ╔════════════════════════════════════╗
         ║ Parkinson's System - USB Serial ║
         ╚════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────┐
│ 2. GPIO Initialization                                           │
└─────────────────────────────────────────────────────────────────┘
[600ms] pinMode(PIN_GREEN, OUTPUT)    - GPIO 15 as output
[600ms] pinMode(PIN_RED, OUTPUT)      - GPIO 2 as output
[600ms] pinMode(PIN_BUTTON, INPUT_PULLUP) - GPIO 13 with pull-up

┌─────────────────────────────────────────────────────────────────┐
│ 3. Display Initialization (I²C Bus 2)                           │
└─────────────────────────────────────────────────────────────────┘
[700ms] Wire1.begin(18, 19)           - Initialize I²C1
[700ms] Wire1.setClock(400000)        - Set 400kHz
[750ms] display.begin(0x3C)           - Initialize SSD1306
[750ms]   ├─ I²C: Send initialization commands
[750ms]   ├─ I²C: Set contrast, charge pump, etc.
[800ms]   └─ I²C: Clear display memory
[800ms] Serial: "[OK] Display ready"
[850ms] display.clearDisplay()
[850ms] display.print("READY")
[900ms] display.display()             - I²C: Send framebuffer to screen

┌─────────────────────────────────────────────────────────────────┐
│ 4. MPU6050 Initialization (I²C Bus 1)                           │
└─────────────────────────────────────────────────────────────────┘
[1000ms] Wire.begin(21, 22)           - Initialize I²C0
[1000ms] Wire.setClock(400000)        - Set 400kHz
[1050ms] mpu.begin()                  - Initialize MPU6050
[1050ms]   ├─ I²C: Detect device at 0x68
[1100ms]   ├─ I²C: Read WHO_AM_I register (should be 0x68)
[1150ms]   ├─ I²C: Wake up sensor (PWR_MGMT_1 = 0x00)
[1200ms]   └─ I²C: Configure registers
[1250ms] mpu.setAccelerometerRange(MPU6050_RANGE_4_G)
[1250ms]   └─ I²C: Write to ACCEL_CONFIG register
[1300ms] mpu.setGyroRange(MPU6050_RANGE_500_DEG)
[1300ms]   └─ I²C: Write to GYRO_CONFIG register
[1350ms] mpu.setFilterBandwidth(MPU6050_BAND_21_HZ)
[1350ms]   └─ I²C: Write to CONFIG register
[1400ms] Serial: "[OK] Sensor ready"

┌─────────────────────────────────────────────────────────────────┐
│ 5. Ready State                                                   │
└─────────────────────────────────────────────────────────────────┘
[1500ms] currentState = IDLE
[1500ms] Serial: "SYSTEM_READY"
[1500ms] Serial: "[READY] Press button to start"
[1500ms] Green LED: Start blinking (1Hz)
[1500ms] Display shows: "READY\nPress button\nto start"
[1500ms] RPI Python script connects and shows:
         ✅ Connected!
         🎬 Waiting for ESP32 to start recording...
```

---

##### **Phase 2: Recording Start** (User presses button)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Button Press Detection                                        │
└─────────────────────────────────────────────────────────────────┘
[T+0ms] loop() detects: digitalRead(PIN_BUTTON) == LOW
[T+0ms] Debounce check: millis() - lastDebounceTime > 500ms ✓
[T+0ms] currentState == IDLE ✓
[T+0ms] Call startRecording()

┌─────────────────────────────────────────────────────────────────┐
│ 2. State Transition: IDLE → RECORDING                           │
└─────────────────────────────────────────────────────────────────┘
[T+0ms] currentCycle++                    (now = 1)
[T+0ms] currentState = RECORDING
[T+0ms] segmentStartTime = millis()      (e.g., 10000ms)
[T+0ms] accumulatedTime = 0
[T+0ms] currentTotalTime = 0

┌─────────────────────────────────────────────────────────────────┐
│ 3. Protocol Messages to RPI                                     │
└─────────────────────────────────────────────────────────────────┘
[T+1ms] Serial.println("START_RECORDING")
[T+2ms] Serial.printf("CYCLE,%d\n", 1)
[T+3ms] Serial.println("Timestamp,Ax,Ay,Az,Gx,Gy,Gz")  // CSV header

RPI receives:
├─ Detects "START_RECORDING" → sets recording=True
├─ Detects "CYCLE,1" → Creates CSV file:
│    tremor_data/tremor_cycle1_20260119_183000.csv
│    tremor_data/tremor_cycle1_20260119_183000.log
└─ Writes CSV header with metadata:
     # Cycle: 1
     # Start Time: 2026-01-19 18:30:00
     # Sample Rate: 100 Hz
     Timestamp,Ax,Ay,Az,Gx,Gy,Gz

┌─────────────────────────────────────────────────────────────────┐
│ 4. Visual Feedback                                               │
└─────────────────────────────────────────────────────────────────┘
[T+5ms] Green LED: Fast blink (200ms interval)
[T+10ms] Display update:
          ┌──────────────┐
          │ Recording 1  │
          │  100Hz       │
          │              │
          │     120s     │  ← Countdown timer
          └──────────────┘
```

---

##### **Phase 3: Active Recording Loop** (Every 10ms for 120s)

```
┌─────────────────────────────────────────────────────────────────┐
│ Main Loop Iteration (Runs every ~10ms)                          │
└─────────────────────────────────────────────────────────────────┘

[T+10ms] Calculate current time:
         currentTotalTime = accumulatedTime + (millis() - segmentStartTime)
         currentTotalTime = 0 + (10010 - 10000) = 10ms

┌─────────────────────────────────────────────────────────────────┐
│ Sample Sensor (if 10ms elapsed since last sample)               │
└─────────────────────────────────────────────────────────────────┘
[T+10ms] Check: millis() - lastSampleTime >= 10ms ✓
[T+10ms] lastSampleTime = millis()
[T+10ms] Call sampleSensor()

  ┌─────────────────────────────────────────────────────────────┐
  │ sampleSensor() Function                                      │
  └─────────────────────────────────────────────────────────────┘
  [T+10ms] sensors_event_t a, g, temp;
  [T+11ms] I²C Transaction: mpu.getEvent(&a, &g, &temp)
           ├─ I²C: Read 0x3B (ACCEL_XOUT_H)
           ├─ I²C: Read 6 bytes (accel X, Y, Z)
           ├─ I²C: Read 2 bytes (temperature)
           └─ I²C: Read 6 bytes (gyro X, Y, Z)
  [T+12ms] Check if read successful
  [T+12ms] failedReads = 0 (success)
  [T+12ms] lastSuccessfulRead = millis()

  [T+13ms] Apply calibration offsets:
           ax = a.acceleration.x - aX_off
           ay = a.acceleration.y - aY_off
           az = a.acceleration.z - aZ_off
           gx = (g.gyro.x * 57.296) - gX_off  // Convert rad/s to deg/s
           gy = (g.gyro.y * 57.296) - gY_off
           gz = (g.gyro.z * 57.296) - gZ_off

  [T+14ms] Freeze Detection:
           stuck = (|ax - lastAx| < 0.001 &&
                    |ay - lastAy| < 0.001 &&
                    |az - lastAz| < 0.001)
           If stuck: stuckCount++
           If stuckCount >= 15:
             └─ Serial.println("ERROR_SENSOR_STUCK")
             └─ Call resetSensor()
           Else: stuckCount = 0

  [T+15ms] Update last values:
           lastAx = ax, lastAy = ay, lastAz = az

  [T+15ms] Transmit to RPI via USB Serial:
           Serial.printf("%lu,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\n",
                         currentTotalTime, ax, ay, az, gx, gy, gz)
           Example: "10,0.582,-0.198,-1.228,22.358,5.808,0.168"

┌─────────────────────────────────────────────────────────────────┐
│ RPI Receives Data                                                │
└─────────────────────────────────────────────────────────────────┘
[T+16ms] RPI: readline() receives: "10,0.582,-0.198,-1.228,22.358,5.808,0.168"
[T+16ms] RPI: Validate format (7 columns, numeric) ✓
[T+16ms] RPI: csv_file.write(line + '\n')
[T+16ms] RPI: csv_file.flush()
[T+16ms] RPI: data_count++ (now = 1)
[T+16ms] RPI: last_data_time = time.time()  // Reset timeout

┌─────────────────────────────────────────────────────────────────┐
│ Sensor Health Check (Every 500ms)                               │
└─────────────────────────────────────────────────────────────────┘
[T+500ms] Check: millis() - lastSensorCheck >= 500ms ✓
[T+500ms] lastSensorCheck = millis()
[T+500ms] Wire.beginTransmission(0x68)
[T+501ms] I²C: Send START + Address 0x68
[T+502ms] I²C: Receive ACK from MPU6050 ✓
[T+502ms] connected = (Wire.endTransmission() == 0) = true
[T+502ms] Check: millis() - lastSuccessfulRead < 2000ms ✓
[T+502ms] Sensor is healthy ✓

┌─────────────────────────────────────────────────────────────────┐
│ Display Update (Every 1000ms)                                    │
└─────────────────────────────────────────────────────────────────┘
[T+1000ms] Check: millis() - lastScreenUpdate >= 1000ms ✓
[T+1000ms] lastScreenUpdate = millis()
[T+1000ms] Calculate remaining time:
           remaining = (120000 - currentTotalTime) / 1000 = 119s
[T+1001ms] display.clearDisplay()
[T+1002ms] display.print("Recording 1\n100Hz")
[T+1003ms] display.print("119s")  // Large font
[T+1010ms] display.display()  // I²C: Send framebuffer to screen

┌─────────────────────────────────────────────────────────────────┐
│ LED Blink (Every 200ms)                                          │
└─────────────────────────────────────────────────────────────────┘
[T+200ms] Check: millis() - lastLedBlink >= 200ms ✓
[T+200ms] lastLedBlink = millis()
[T+200ms] digitalWrite(PIN_GREEN, !digitalRead(PIN_GREEN))  // Toggle

┌─────────────────────────────────────────────────────────────────┐
│ RPI Progress Display (Every 1s / 100 samples)                   │
└─────────────────────────────────────────────────────────────────┘
[T+1000ms] RPI: data_count = 100 (100 samples received)
[T+1000ms] RPI: Print "   📊   100 samples |    1.0s"
[T+2000ms] RPI: Print "   📊   200 samples |    2.0s"
... continues every 100 samples
```

**This loop repeats ~12,000 times over 120 seconds**

---

##### **Phase 4: Pause Operation** (Optional - User presses button)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Button Press During Recording                                │
└─────────────────────────────────────────────────────────────────┘
[T+5000ms] User presses button (at 5 seconds into recording)
[T+5000ms] loop() detects: digitalRead(PIN_BUTTON) == LOW
[T+5000ms] Debounce check: millis() - lastDebounceTime > 500ms ✓
[T+5000ms] currentState == RECORDING ✓

┌─────────────────────────────────────────────────────────────────┐
│ 2. State Transition: RECORDING → PAUSED                         │
└─────────────────────────────────────────────────────────────────┘
[T+5000ms] accumulatedTime += (millis() - segmentStartTime)
           accumulatedTime = 0 + (15000 - 10000) = 5000ms
[T+5000ms] currentTotalTime = accumulatedTime = 5000ms
[T+5000ms] currentState = PAUSED

┌─────────────────────────────────────────────────────────────────┐
│ 3. Protocol & Feedback                                           │
└─────────────────────────────────────────────────────────────────┘
[T+5001ms] Serial.println("PAUSE_CYCLE")
[T+5001ms] Serial.println("[USER] PAUSED")

RPI receives:
├─ Detects "PAUSE_CYCLE" → sets paused=True
├─ Prints: "⏸️  PAUSED (500 samples so far)"
└─ Log: [2026-01-19 18:30:05] INFO: Recording paused at 500 samples

[T+5005ms] Red LED: Start blinking (800ms interval)
[T+5010ms] Display update: "PAUSED 1\n5s" (frozen at 5 seconds)

┌─────────────────────────────────────────────────────────────────┐
│ 4. Paused Loop (No sampling, timer frozen)                      │
└─────────────────────────────────────────────────────────────────┘
[T+5000ms - T+15000ms] User waits 10 seconds
├─ No sensor sampling occurs
├─ currentTotalTime stays at 5000ms
├─ accumulatedTime stays at 5000ms
├─ Display shows frozen "5s"
└─ Red LED blinks every 800ms

┌─────────────────────────────────────────────────────────────────┐
│ 5. Resume (User presses button again)                           │
└─────────────────────────────────────────────────────────────────┘
[T+15000ms] User presses button
[T+15000ms] currentState == PAUSED ✓
[T+15000ms] segmentStartTime = millis() = 25000ms (new segment!)
[T+15000ms] currentState = RECORDING
[T+15000ms] accumulatedTime = 5000ms (preserved!)

[T+15001ms] Serial.println("RESUME_CYCLE")
[T+15001ms] Serial.println("[USER] RESUMED")

RPI receives:
├─ Detects "RESUME_CYCLE" → sets paused=False
├─ Prints: "▶️  RESUMED"
├─ Log: [2026-01-19 18:30:15] INFO: Recording resumed at 500 samples
└─ Resets last_data_time = time.time()  // Reset timeout detection

[T+15010ms] Green LED: Fast blink (200ms)
[T+15010ms] Display: "Recording 1\n5s" (continues from 5s)

┌─────────────────────────────────────────────────────────────────┐
│ 6. Recording Continues (Timestamps remain continuous)           │
└─────────────────────────────────────────────────────────────────┘
[T+15010ms] Next sample:
            currentTotalTime = accumulatedTime + (millis() - segmentStartTime)
            currentTotalTime = 5000 + (25010 - 25000) = 5010ms

            Serial.printf("%lu,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\n",
                          5010, ax, ay, az, gx, gy, gz)
                          ^^^^
                          Continues from 5000ms! No gap!

RPI writes to CSV:
5000,0.60,-0.18,-1.21,22.34,5.79,0.15   ← Last sample before pause
5010,0.61,-0.17,-1.20,22.33,5.78,0.14   ← First sample after resume
                                          (only 10ms gap, perfect!)
```

---

##### **Phase 5: Recording Complete**

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Duration Check (Every loop iteration)                        │
└─────────────────────────────────────────────────────────────────┘
[T+120000ms] currentTotalTime >= TARGET_DURATION (120000ms) ✓
[T+120000ms] Call stopRecording()

┌─────────────────────────────────────────────────────────────────┐
│ 2. State Transition: RECORDING → WAITING_NEXT                   │
└─────────────────────────────────────────────────────────────────┘
[T+120000ms] Serial.println("END_RECORDING")
[T+120000ms] Serial.printf("RESETS,%lu\n", sensorResets)  // e.g., 0
[T+120001ms] currentState = WAITING_NEXT

RPI receives:
├─ Detects "END_RECORDING" → sets recording=False
├─ Writes log summary:
│   [2026-01-19 18:32:00] INFO: Recording complete - 12000 samples
│   [2026-01-19 18:32:00] SUMMARY: Duration: 120.0s
│   [2026-01-19 18:32:00] SUMMARY: Sensor resets: 0
│   [2026-01-19 18:32:00] SUMMARY: Errors: 0
│   [2026-01-19 18:32:00] SUMMARY: Validation errors: 0
├─ Closes CSV and log files
└─ Prints cycle summary:
    ✅ Cycle 1 Complete!
       Total samples: 12000
       Duration: 120.0s
       Sensor resets: 0
       Errors: 0
       Validation errors: 0

[T+120010ms] Green LED: OFF
[T+120010ms] Red LED: Fast blink (500ms)
[T+120010ms] Display: "DONE\nPress for\nNext Cycle"

┌─────────────────────────────────────────────────────────────────┐
│ 3. Check Cycle Limit                                             │
└─────────────────────────────────────────────────────────────────┘
[T+120000ms] currentCycle (1) < MAX_CYCLES (2) ✓
[T+120000ms] currentState = WAITING_NEXT (not FINISHED)

If user presses button:
├─ Increment currentCycle to 2
├─ Transition to RECORDING
└─ Repeat Phase 2-5 for Cycle 2

If currentCycle == MAX_CYCLES after completion:
├─ currentState = FINISHED
├─ Serial.println("ALL_COMPLETE")
├─ Display: "FINISHED\nAll cycles done"
├─ Green LED: Solid ON
└─ Terminal state (no more recording)
```

---

This complete sequence shows every detail from power-on through initialization, I²C communication, state transitions, and continuous timestamp management across pause/resume cycles.

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

## Algorithm Validation with Motor Simulation

### Duty Cycle Motor Control (`motor_control.py`)

The system includes a DC motor with eccentric mass for generating controlled vibrations at known frequencies. The motor is controlled via PWM duty cycle.

#### Hardware Setup

**L298N Motor Driver Configuration:**
```
RPI4 GPIO -> L298N:
  - GPIO 18 -> ENA (PWM speed control)
  - GPIO 23 -> IN1 (direction control)
  - GPIO 24 -> IN2 (direction control)
  - 12V external supply -> Motor power
```

**Motor Specifications:**
- 12V DC motor, 625 RPM max (10.42 Hz)
- Eccentric mass: 40g at 1.5 cm from rotation axis
- PWM carrier frequency: 1 kHz
- Minimum duty cycle: 15% (motor start threshold)

**Duty Cycle to Frequency Mapping:**
```
Duty Cycle -> Voltage -> RPM   -> Frequency
  20%       -> 2.4V   -> ~125  -> ~2.1 Hz
  40%       -> 4.8V   -> ~250  -> ~4.2 Hz
  60%       -> 7.2V   -> ~375  -> ~6.3 Hz
  80%       -> 9.6V   -> ~500  -> ~8.3 Hz
 100%       -> 12V    -> ~625  -> ~10.4 Hz
```

**Measurement Setup:**
- **Option 1 (Ground Truth):** MPU6050 attached directly to motor
- **Option 2 (Realistic):** Hand holds motor, MPU6050 on finger

#### Running Motor Control

```bash
python3 motor_control.py

# Interactive menu:
#   - Enter duty cycle (0-100%)
#   - Motor runs continuously at that speed
#   - Change duty cycle anytime
#   - Enter 0 or 'q' to stop
```

#### Complete Validation Workflow

**Step 1: Start Motor at Known Duty Cycle**
```bash
cd /path/to/Proceesing-data-based-RPI4
python3 motor_control.py
# Set duty cycle (e.g., 40% -> ~4.2 Hz, within rest tremor band)
```

**Step 2: Record Data with ESP32**
```bash
# In separate terminal
python3 rpi_usb_recorder_v2.py
# Press button on ESP32 to start recording
# Motor vibrates at controlled frequency
```

**Step 3: Analyze with Input-Output Validation**
```bash
python3 offline_analyzer.py
# Load the CSV file from tremor_data/
# Enter expected frequency range (e.g., 3.5-5.0 Hz)
# System checks if PSD peak falls within your expected range
```

**Step 4: Validate Results**
- Verify PSD peak frequency matches motor frequency
- Check PASS/FAIL validation result
- Compare expected vs measured frequency (tolerance: +/-0.5 Hz)
- Document results for validation report

---

## Data Analysis

### Offline Rest Tremor Analyzer (`offline_analyzer.py`)

**Research-Based Signal Processing Tool**

The offline analyzer focuses on **rest tremor detection (3-7 Hz)** using a single Butterworth bandpass filter and input-output validation. Based on peer-reviewed research using MPU6050 sensors and ESP32 hardware.

#### Scientific Foundation

**Hardware Validation:**
- MPU6050 + ESP32 validated in clinical tremor research
- Research papers:
  - [MDPI - Clinical Medicine: MPU6050 Tremor Classification](https://www.mdpi.com/2077-0383/14/6/2073)
  - [MDPI - Sensors: ELENA Project with ESP32](https://www.mdpi.com/1424-8220/25/9/2763)

**Signal Processing Approach:**
- **Accelerometer Focus**: Gyroscope data excluded (motor artifact concerns in motor-holding tests)
- **Dual Perspective**: Both dominant axis analysis AND resultant vector magnitude
- **Automatic Axis Detection**: Identifies highest energy axis (X, Y, or Z) automatically
- **Single Bandpass Filter**: 2-8 Hz Butterworth order 4 (extended from clinical 3-7 Hz to avoid -3dB edge attenuation)
- **Zero-Phase Filtering**: Forward-backward (`filtfilt`) for no phase distortion
- **Resultant Vector**: Magnitude `sqrt(Ax^2 + Ay^2 + Az^2)` after gravity removal
- **PSD Analysis**: Welch method (4s window, 50% overlap), peak detection within 3-7 Hz

#### Input-Output Validation

Instead of automated classification, the system uses an **input-output validation** approach:

1. User enters expected frequency range (e.g., motor set to 4-5 Hz)
2. System computes PSD and finds dominant peak within 3-7 Hz
3. System checks if measured peak falls within expected range (+/-0.5 Hz tolerance)
4. Reports PASS or FAIL with measured vs expected values

```
Validation Logic:
  - User input: expected_low = 4.0 Hz, expected_high = 5.0 Hz
  - System measures: PSD peak = 4.3 Hz
  - Check: 4.0 - 0.5 <= 4.3 <= 5.0 + 0.5 -> PASS
```

#### Filter Design

**Single Butterworth Bandpass (2-8 Hz):**
- Order: 4 (research standard)
- Lower cutoff: 2 Hz (below clinical 3 Hz to preserve edge response)
- Upper cutoff: 8 Hz (above clinical 7 Hz to preserve edge response)
- At 3 Hz and 7 Hz: near-unity gain (no -3dB attenuation)
- Implementation: `scipy.signal.butter` + `filtfilt` (zero-phase)

#### Visualization Dashboard

**Row 1: Filter Characteristics & Metrics**
- Bode magnitude response (Butterworth order 4, 2-8 Hz)
- Bode phase response
- Validation results table (expected range, measured peak, PASS/FAIL)

**Row 2: Dominant Axis Analysis (Auto-Detected)**
- Highest energy axis - raw signal
- Filtered signal (2-8 Hz) with envelope
- Raw vs Filtered overlay comparison

**Row 3: Resultant Vector Analysis**
- Raw resultant magnitude `sqrt(Ax^2 + Ay^2 + Az^2)`
- Filtered resultant (2-8 Hz) with envelope
- Raw vs Filtered overlay comparison

**Row 4: Power Spectral Density (PSD) Analysis**
- PSD of dominant axis with 3-7 Hz clinical band highlighted
- PSD of resultant vector (raw vs filtered)
- Rest tremor band power (3-7 Hz)

#### Running the Analyzer

**GUI Mode:**
```bash
cd /home/user/Proceesing-data-based-RPI4
python3 offline_analyzer.py
```

**Steps:**
1. Click "Load CSV Data"
2. Select tremor CSV file from `tremor_data/`
3. Enter expected frequency range when prompted (for validation)
4. View dashboard with filter response, time-domain signals, and PSD
5. Check validation result: PASS/FAIL with measured peak frequency

**Configuration:**
```python
FS = 100.0              # Sampling rate (Hz)
FILTER_ORDER = 4        # Butterworth filter order
FREQ_TREMOR_LOW = 2.0   # Filter lower bound
FREQ_TREMOR_HIGH = 8.0  # Filter upper bound
FREQ_REST_LOW = 3.0     # Clinical rest tremor lower bound
FREQ_REST_HIGH = 7.0    # Clinical rest tremor upper bound
FREQ_TOLERANCE_HZ = 0.5 # Validation tolerance
```

### Quick Data Verification

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

**Data Acquisition:**
- `pyserial` - USB serial communication
- Standard library: `datetime`, `os`, `sys`, `time`

**Offline Analysis:**
- `numpy` - Numerical computing
- `scipy` - Signal processing (Butterworth filters, Welch's method)
- `matplotlib` - Visualization and plotting
- `pandas` - CSV data manipulation
- `tkinter` - GUI file dialog (usually pre-installed)

**Installation:**
```bash
# Data acquisition only
pip3 install pyserial

# Full analysis capabilities
pip3 install pyserial numpy scipy matplotlib pandas
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

## Version History

### v4.0 (Current)
- Simplified to rest tremor only (3-7 Hz)
- Single 2-8 Hz Butterworth bandpass filter
- Input-output validation (replaces Power Ratio classification)
- Duty cycle motor control (replaces tremor sequences)
- Motor eccentric mass: 40g at 1.5 cm radius

### v3
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

**Last Updated:** 2026-02-04
**Version:** 4.0

**New in v4.0:**
- Simplified to rest tremor only (3-7 Hz clinical band)
- Single Butterworth bandpass filter 2-8 Hz (avoids edge attenuation)
- Input-output validation replaces automated classification
- Duty cycle motor control (single mode, user sets percentage)
- Motor eccentric mass updated to 40g at 1.5 cm radius
- Validated against peer-reviewed MPU6050 research
