/**
 * ================================================================
 * Parkinson's Tremor Detection System - USB Serial Version (V3)
 * Dual-Core FreeRTOS with Lock-Free Circular Buffer
 * ================================================================
 *
 * ARCHITECTURE OVERVIEW
 * ---------------------
 * The ESP32 has two CPU cores. V3 assigns each core a dedicated role
 * to guarantee uninterrupted 100 Hz sampling:
 *
 *   Core 1 (samplerTask, priority 5 — high):
 *     - Owns the I2C sensor bus (Wire, GPIO 21/22) exclusively
 *     - Initializes Wire + MPU6050 on THIS core (fixes core affinity)
 *     - Reads accelerometer every 10ms via vTaskDelayUntil (drift-free)
 *     - Applies calibration offsets
 *     - Runs stuck detection + health check
 *     - Writes samples into a lock-free circular buffer
 *     - Handles sensor reset (Wire.end/begin stays on Core 1)
 *
 *   Core 0 (loop, priority 1 — normal):
 *     - Owns Serial (USB) and Wire1 (OLED, GPIO 18/19) exclusively
 *     - Drains the circular buffer → Serial.printf() CSV lines
 *     - Runs FSM state transitions (button → start/pause/resume/stop)
 *     - Updates OLED display every 1s (takes ~23ms — doesn't block Core 1)
 *     - Blinks LEDs for status indication
 *     - Pets the hardware watchdog
 *
 * DATA FLOW
 * ---------
 *   MPU6050 →(I2C, Core 1)→ sampleSensor() →(calibrate, stuck check)→
 *   → ringBuf[writeIdx] →(shared memory)→ loop() reads ringBuf[readIdx]
 *   → Serial.printf() →(USB)→ RPi
 *
 * CIRCULAR BUFFER (Lock-Free SPSC)
 * --------------------------------
 *   - 256 entries (power of 2), holds 2.56 seconds of data
 *   - Single Producer (Core 1 writes writeIdx)
 *   - Single Consumer (Core 0 writes readIdx)
 *   - No mutex needed — each index written by exactly one core
 *   - If buffer full: Core 1 increments missedSamples, drops sample
 *   - Core 0 drain rate: ~380 samples/sec (Serial 115200 baud)
 *   - Core 1 fill rate: 100 samples/sec → 3.8x safety margin
 *
 * STARTUP SEQUENCE
 * ----------------
 *   1. setup() runs on Core 0:
 *      - Serial, GPIO, OLED (Wire1), watchdog
 *      - Launches samplerTask on Core 1
 *      - Waits for sensorReady flag (Core 1 finished sensor init)
 *   2. samplerTask() starts on Core 1:
 *      - Wire.begin(21,22), Wire.setClock(400kHz), Wire.setTimeOut(10ms)
 *      - mpu.begin(), configure ±2G, 21Hz DLPF
 *      - Sets sensorReady = true
 *      - Enters sampling loop (only samples when state == RECORDING)
 *   3. setup() sees sensorReady, prints SYSTEM_READY, returns to loop()
 *
 * SAFETY STACK (unchanged from V2)
 * --------------------------------
 *   Layer 5: Watchdog (5s)           — catches any hang → auto-reboot
 *   Layer 4: Wire.setTimeOut(10ms)   — catches I2C hang → getEvent fails
 *   Layer 3: Health check (500ms)    — catches sensor disappearing
 *   Layer 2: Read failure (5x)       — catches soft I2C errors
 *   Layer 1: Stuck detection (15x)   — catches ADC lockup
 *
 * WHY V3 WORKS (vs failed previous attempt)
 * ------------------------------------------
 *   Previous V3 initialized Wire on Core 0 (setup) but used it on Core 1.
 *   ESP32's I2C driver has core affinity — it binds to the initializing core.
 *   Fix: Core 1 now calls Wire.begin() itself, so init and use are on the
 *   same core. Core 0 never touches Wire at all.
 *
 * Connection: ESP32 USB Micro → Raspberry Pi USB Port
 * Button: GPIO 13
 * ================================================================
 */

#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <esp_task_wdt.h>

// ================================================================
// HARDWARE PINS
// ================================================================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire1, -1);
Adafruit_MPU6050 mpu;

const int PIN_GREEN  = 15;
const int PIN_RED    = 2;
const int PIN_BUTTON = 13;

// ================================================================
// TIMING & CONFIG
// ================================================================
const long TARGET_DURATION = 120000;  // 2 minutes per cycle
const int SAMPLE_RATE_HZ = 100;
const int SAMPLE_INTERVAL_MS = 1000 / SAMPLE_RATE_HZ;  // 10 ms
const int MAX_CYCLES = 2;

// ================================================================
// CIRCULAR BUFFER (lock-free SPSC: Core 1 writes, Core 0 reads)
// ================================================================
struct Sample {
  unsigned long timestamp;
  float ax;
  float ay;
  float az;
};

#define BUF_SIZE 256  // Must be power of 2
#define BUF_MASK (BUF_SIZE - 1)

volatile Sample ringBuf[BUF_SIZE];
volatile uint32_t writeIdx = 0;  // Only written by Core 1
volatile uint32_t readIdx  = 0;  // Only written by Core 0

// ================================================================
// STATE MACHINE (shared between cores — volatile)
// ================================================================
enum State { IDLE, RECORDING, PAUSED, WAITING_NEXT, FINISHED };
volatile State currentState = IDLE;
volatile int currentCycle = 0;

// Stopwatch-style timing (written by Core 0, read by Core 1)
volatile unsigned long segmentStartTime = 0;
volatile unsigned long accumulatedTime = 0;
volatile unsigned long currentTotalTime = 0;

// ================================================================
// SENSOR SAFETY (accessed only by sampler task on Core 1)
// ================================================================
float lastAx = 0, lastAy = 0, lastAz = 0;
int stuckCount = 0;
int failedReads = 0;
unsigned long lastSuccessfulRead = 0;
volatile unsigned long sensorResets = 0;
volatile unsigned long missedSamples = 0;

const int MAX_STUCK = 15;
const int MAX_FAILED = 5;
const float STUCK_THRESHOLD = 0.001;

// Calibration (accelerometer only, for +/-2G range)
const float aX_off = 0.301009;
const float aY_off = 0.016101;
const float aZ_off = 1.046231;

// Synchronization: Core 1 signals sensor init complete
volatile bool sensorReady = false;

// ================================================================
// UI TIMERS (Core 0 only)
// ================================================================
unsigned long lastScreenUpdate = 0;
unsigned long lastGreenBlink = 0;
unsigned long lastRedBlink = 0;
unsigned long lastDebounceTime = 0;

// ================================================================
// SETUP (runs on Core 0)
// NOTE: Does NOT touch Wire or MPU6050 — Core 1 owns the sensor bus
// ================================================================
void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000);

  Serial.println("\n========================================");
  Serial.println("  Parkinson's System V3 - Dual Core");
  Serial.println("  Core 0: UI/FSM  |  Core 1: Sampling");
  Serial.println("========================================");

  pinMode(PIN_GREEN, OUTPUT);
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  // Display on Wire1 (Core 0 only — never touched by Core 1)
  Wire1.begin(18, 19);
  Wire1.setClock(400000);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("[ERROR] Display init failed!");
    while (1) {
      digitalWrite(PIN_RED, !digitalRead(PIN_RED));
      delay(100);
    }
  }
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  Serial.println("[OK] Display ready");

  // Hardware watchdog (reconfigure — Arduino framework pre-initializes TWDT)
  const esp_task_wdt_config_t wdt_config = {
    .timeout_ms = 5000,
    .idle_core_mask = 0,
    .trigger_panic = true
  };
  esp_task_wdt_reconfigure(&wdt_config);
  esp_task_wdt_add(NULL);  // Watch the Core 0 loop task
  Serial.println("[OK] Watchdog armed (5s)");

  // Launch sampler task on Core 1 — it will init Wire + sensor there
  xTaskCreatePinnedToCore(
    samplerTask,    // Task function
    "sampler",      // Name
    4096,           // Stack size (bytes)
    NULL,           // Parameter
    5,              // Priority (high — above loop's default 1)
    NULL,           // Task handle
    1               // Core 1
  );

  // Wait for Core 1 to finish sensor initialization
  Serial.print("[WAIT] Sensor init on Core 1...");
  unsigned long waitStart = millis();
  while (!sensorReady) {
    delay(10);
    esp_task_wdt_reset();  // Keep watchdog happy while waiting
    if (millis() - waitStart > 5000) {
      Serial.println(" TIMEOUT!");
      showError("Sensor Error", "Core 1 init\ntimeout");
      while (1);
    }
  }
  Serial.println(" OK");
  Serial.println("[OK] Sampler task running on Core 1");

  updateDisplay("READY", "Press button\nto start");
  Serial.println("SYSTEM_READY");
}

// ================================================================
// SAMPLER TASK — Core 1
// Owns Wire (GPIO 21/22) exclusively. Never touches Wire1 or Serial
// for data output (only for error messages during sensor reset).
// ================================================================
void samplerTask(void *param) {
  // ---- One-time sensor init ON THIS CORE (fixes core affinity) ----
  Wire.begin(21, 22);
  Wire.setClock(400000);
  Wire.setTimeOut(10);

  if (!initSensor()) {
    // Signal failure — Core 0 will detect timeout
    // Cannot show on OLED from here (Wire1 belongs to Core 0)
    Serial.println("[ERROR] Sensor init failed on Core 1!");
    vTaskDelete(NULL);  // Kill this task
    return;
  }

  sensorReady = true;  // Signal Core 0: init complete

  // ---- Sampling loop ----
  TickType_t lastWake = xTaskGetTickCount();
  unsigned long lastHealthCheck = 0;

  while (true) {
    if (currentState == RECORDING) {
      // Compute timestamp on Core 1 (avoids race with Core 0's currentTotalTime)
      unsigned long ts = accumulatedTime + (millis() - segmentStartTime);

      sampleAndBuffer(ts);

      // Health check every 500ms (same core as sensor — no I2C contention)
      if (millis() - lastHealthCheck >= 500) {
        lastHealthCheck = millis();
        if (!checkSensor()) {
          Serial.println("[ERROR] Sensor lost connection!");
          Serial.println("ERROR_SENSOR_LOST");
          resetSensor();
          lastWake = xTaskGetTickCount();  // Reset timing after 200ms delay
        }
      }
    }

    vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(SAMPLE_INTERVAL_MS));
  }
}

// ================================================================
// SAMPLE AND BUFFER (Core 1 only)
// Reads sensor, applies calibration, stuck check, writes to ring buf
// ================================================================
void sampleAndBuffer(unsigned long timestamp) {
  sensors_event_t a, g, temp;

  if (!mpu.getEvent(&a, &g, &temp)) {
    failedReads++;
    if (failedReads >= MAX_FAILED) {
      Serial.println("[CRITICAL] Too many read failures!");
      Serial.println("ERROR_READ_FAILED");
      resetSensor();
    }
    return;
  }

  failedReads = 0;
  lastSuccessfulRead = millis();

  float ax = a.acceleration.x - aX_off;
  float ay = a.acceleration.y - aY_off;
  float az = a.acceleration.z - aZ_off;

  // Stuck detection
  bool stuck = (abs(ax - lastAx) < STUCK_THRESHOLD &&
                abs(ay - lastAy) < STUCK_THRESHOLD &&
                abs(az - lastAz) < STUCK_THRESHOLD);

  if (stuck) {
    stuckCount++;
    if (stuckCount >= MAX_STUCK) {
      Serial.printf("[CRITICAL] Sensor stuck! (%d identical reads)\n", stuckCount);
      Serial.println("ERROR_SENSOR_STUCK");
      resetSensor();
      return;
    }
  } else {
    stuckCount = 0;
  }

  lastAx = ax;
  lastAy = ay;
  lastAz = az;

  // Write to circular buffer
  uint32_t nextWrite = (writeIdx + 1) & BUF_MASK;
  if (nextWrite == readIdx) {
    // Buffer full — drop sample
    missedSamples++;
    return;
  }

  ringBuf[writeIdx].timestamp = timestamp;
  ringBuf[writeIdx].ax = ax;
  ringBuf[writeIdx].ay = ay;
  ringBuf[writeIdx].az = az;
  writeIdx = nextWrite;  // Publish to Core 0 (single atomic write)
}

// ================================================================
// MAIN LOOP — Core 0 (UI, Serial output, button, LED, FSM)
// ================================================================
void loop() {
  esp_task_wdt_reset();
  handleButton();

  // Drain ring buffer → Serial (runs every loop iteration, all states)
  drainBuffer();

  switch (currentState) {
    case IDLE:
      blinkGreen(1000);
      break;

    case RECORDING:
      currentTotalTime = accumulatedTime + (millis() - segmentStartTime);
      blinkGreen(200);
      updateScreenPeriodic(false);
      if (currentTotalTime >= TARGET_DURATION) {
        stopRecording();
      }
      break;

    case PAUSED:
      blinkRed(800);
      digitalWrite(PIN_GREEN, LOW);
      updateScreenPeriodic(true);
      break;

    case WAITING_NEXT:
      blinkRed(500);
      break;

    case FINISHED:
      digitalWrite(PIN_GREEN, HIGH);
      digitalWrite(PIN_RED, LOW);
      break;
  }
}

// ================================================================
// BUFFER DRAIN (Core 0 only — reads ring buffer, writes to Serial)
// ================================================================
void drainBuffer() {
  // Drain up to 10 samples per loop iteration to stay responsive
  int count = 0;
  while (readIdx != writeIdx && count < 10) {
    volatile Sample *s = &ringBuf[readIdx];
    Serial.printf("%lu,%.3f,%.3f,%.3f\n", s->timestamp, s->ax, s->ay, s->az);
    readIdx = (readIdx + 1) & BUF_MASK;
    count++;
  }
}

// ================================================================
// UI HELPERS (Core 0 only)
// ================================================================

void blinkGreen(unsigned long interval) {
  if (millis() - lastGreenBlink >= interval) {
    lastGreenBlink = millis();
    digitalWrite(PIN_GREEN, !digitalRead(PIN_GREEN));
  }
}

void blinkRed(unsigned long interval) {
  if (millis() - lastRedBlink >= interval) {
    lastRedBlink = millis();
    digitalWrite(PIN_RED, !digitalRead(PIN_RED));
  }
}

void updateScreenPeriodic(bool isPaused) {
  if (millis() - lastScreenUpdate >= 1000) {
    lastScreenUpdate = millis();
    updateRecordingDisplay(isPaused);
  }
}

// ================================================================
// BUTTON HANDLER (Core 0)
// ================================================================
void handleButton() {
  if (digitalRead(PIN_BUTTON) == LOW && millis() - lastDebounceTime > 500) {
    lastDebounceTime = millis();

    if (currentState == IDLE || currentState == WAITING_NEXT) {
      startRecording();
    }
    else if (currentState == RECORDING) {
      accumulatedTime += (millis() - segmentStartTime);
      currentTotalTime = accumulatedTime;
      currentState = PAUSED;
      Serial.println("PAUSE_CYCLE");
    }
    else if (currentState == PAUSED) {
      segmentStartTime = millis();
      currentState = RECORDING;
      Serial.println("RESUME_CYCLE");
    }
  }
}

// ================================================================
// SENSOR FUNCTIONS (Core 1 only — exclusive Wire access)
// ================================================================

bool initSensor() {
  if (!mpu.begin()) return false;
  mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  stuckCount = 0;
  failedReads = 0;
  lastSuccessfulRead = millis();
  delay(100);
  return true;
}

bool checkSensor() {
  Wire.beginTransmission(0x68);
  bool connected = (Wire.endTransmission() == 0);
  if (connected && (millis() - lastSuccessfulRead > 2000)) return false;
  return connected;
}

void resetSensor() {
  sensorResets++;
  Serial.printf("[RESET] Sensor reset #%lu\n", sensorResets);
  Serial.printf("SENSOR_RESET,%lu\n", sensorResets);

  Wire.end();
  delay(150);
  Wire.begin(21, 22);
  Wire.setClock(400000);
  Wire.setTimeOut(10);
  delay(50);

  if (initSensor()) {
    Serial.println("SENSOR_RESET_OK");
  } else {
    Serial.println("SENSOR_RESET_FAILED");
  }
}

// ================================================================
// STATE FUNCTIONS (Core 0)
// ================================================================

void startRecording() {
  currentCycle++;
  segmentStartTime = millis();
  accumulatedTime = 0;
  currentTotalTime = 0;
  missedSamples = 0;

  // Clear buffer before starting
  readIdx = 0;
  writeIdx = 0;

  digitalWrite(PIN_RED, LOW);
  digitalWrite(PIN_GREEN, LOW);

  Serial.println("START_RECORDING");
  Serial.printf("CYCLE,%d\n", currentCycle);
  Serial.println("Timestamp,Ax,Ay,Az");

  currentState = RECORDING;  // Enable sampler (must be last)
}

void stopRecording() {
  currentState = IDLE;  // Pause sampler immediately

  // Drain remaining samples from buffer
  while (readIdx != writeIdx) {
    volatile Sample *s = &ringBuf[readIdx];
    Serial.printf("%lu,%.3f,%.3f,%.3f\n", s->timestamp, s->ax, s->ay, s->az);
    readIdx = (readIdx + 1) & BUF_MASK;
  }

  Serial.println("END_RECORDING");
  Serial.printf("RESETS,%lu\n", sensorResets);
  Serial.printf("MISSED,%lu\n", missedSamples);

  digitalWrite(PIN_GREEN, LOW);

  if (currentCycle < MAX_CYCLES) {
    currentState = WAITING_NEXT;
    updateDisplay("DONE", "Press for\nNext Cycle");
  } else {
    currentState = FINISHED;
    updateDisplay("FINISHED", "All cycles done");
    Serial.println("ALL_COMPLETE");
  }
}

// ================================================================
// DISPLAY FUNCTIONS (Core 0 only — exclusive Wire1 access)
// ================================================================

void updateRecordingDisplay(bool isPaused) {
  long remaining = (TARGET_DURATION - currentTotalTime) / 1000;
  if (remaining < 0) remaining = 0;

  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print(isPaused ? F("PAUSED ") : F("REC "));
  display.println(currentCycle);
  display.print(F("100Hz"));

  display.setTextSize(3);
  display.setCursor(30, 25);
  display.print(remaining);
  display.setTextSize(1);
  display.print(F("s"));

  display.display();
}

void updateDisplay(String title, String sub) {
  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(0, 0);
  display.println(title);
  display.setTextSize(1);
  display.setCursor(0, 25);
  display.println(sub);
  display.display();
}

void showError(String title, String message) {
  updateDisplay(title, message);
  digitalWrite(PIN_RED, HIGH);
}
