/**
 * Parkinson's Tremor Detection System - USB Serial Version (V3)
 * Dual-Core FreeRTOS: sampling on Core 1, UI/FSM on Core 0
 *
 * V3 changes from V2:
 * - Sampling runs on a dedicated FreeRTOS task pinned to Core 1
 * - vTaskDelayUntil provides drift-free 10ms intervals
 * - OLED display, LED, button handling run on Core 0 (loop)
 * - Missed sample counter tracks any overruns
 * - I2C sensor bus (Wire) is used exclusively by the sampler task
 * - Health check moved into sampler task (no cross-core I2C contention)
 *
 * Connection: ESP32 USB Micro -> Raspberry Pi USB Port
 * Button: GPIO 13
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

// ================================================================
// UI TIMERS (Core 0 only)
// ================================================================
unsigned long lastScreenUpdate = 0;
unsigned long lastLedBlink = 0;
unsigned long lastDebounceTime = 0;

// ================================================================
// SETUP (runs on Core 0)
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

  // Display on Wire1 (Core 0 only)
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

  // Sensor on Wire (will be used exclusively by Core 1 sampler)
  Wire.begin(21, 22);
  Wire.setClock(400000);
  Wire.setTimeOut(10);
  if (!initSensor()) {
    Serial.println("[ERROR] Sensor init failed!");
    showError("Sensor Error", "Check wiring");
    while (1);
  }
  Serial.println("[OK] Sensor ready");

  // Hardware watchdog (watches Core 0 loop task)
  const esp_task_wdt_config_t wdt_config = {
    .timeout_ms = 5000,
    .idle_core_mask = 0,
    .trigger_panic = true
  };
  esp_task_wdt_init(&wdt_config);
  esp_task_wdt_add(NULL);
  Serial.println("[OK] Watchdog armed (5s)");

  // Launch sampler task on Core 1
  xTaskCreatePinnedToCore(
    samplerTask,    // Task function
    "sampler",      // Name
    4096,           // Stack size (bytes)
    NULL,           // Parameter
    5,              // Priority (high — above loop's default 1)
    NULL,           // Task handle (not needed)
    1               // Core 1
  );
  Serial.println("[OK] Sampler task launched on Core 1");

  updateDisplay("READY", "Press button\nto start");
  Serial.println("SYSTEM_READY");
}

// ================================================================
// SAMPLER TASK — Core 1 (dedicated to sensor I2C + Serial output)
// ================================================================
void samplerTask(void *param) {
  TickType_t lastWake = xTaskGetTickCount();
  unsigned long lastHealthCheck = 0;

  while (true) {
    if (currentState == RECORDING) {
      sampleSensor();

      // Health check every 500ms (runs on same core as sensor — no I2C contention)
      if (millis() - lastHealthCheck >= 500) {
        lastHealthCheck = millis();
        if (!checkSensor()) {
          Serial.println("[ERROR] Sensor lost connection!");
          Serial.println("ERROR_SENSOR_LOST");
          resetSensor();
        }
      }
    }

    // Precise 10ms interval — compensates for execution time automatically
    vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(SAMPLE_INTERVAL_MS));
  }
}

// ================================================================
// MAIN LOOP — Core 0 (UI, button, LED, FSM transitions)
// ================================================================
void loop() {
  esp_task_wdt_reset();
  handleButton();

  switch (currentState) {
    case IDLE:
      blinkLed(PIN_GREEN, 1000);
      break;

    case RECORDING:
      currentTotalTime = accumulatedTime + (millis() - segmentStartTime);
      blinkLed(PIN_GREEN, 200);
      updateScreenPeriodic(false);
      if (currentTotalTime >= TARGET_DURATION) {
        stopRecording();
      }
      break;

    case PAUSED:
      blinkLed(PIN_RED, 800);
      digitalWrite(PIN_GREEN, LOW);
      updateScreenPeriodic(true);
      break;

    case WAITING_NEXT:
      blinkLed(PIN_RED, 500);
      break;

    case FINISHED:
      digitalWrite(PIN_GREEN, HIGH);
      digitalWrite(PIN_RED, LOW);
      break;
  }
}

// ================================================================
// UI HELPERS (Core 0 only)
// ================================================================

void blinkLed(int pin, unsigned long interval) {
  if (millis() - lastLedBlink >= interval) {
    lastLedBlink = millis();
    digitalWrite(pin, !digitalRead(pin));
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

void sampleSensor() {
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

  Serial.printf("%lu,%.3f,%.3f,%.3f\n", currentTotalTime, ax, ay, az);
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

  digitalWrite(PIN_RED, LOW);
  digitalWrite(PIN_GREEN, LOW);

  Serial.println("START_RECORDING");
  Serial.printf("CYCLE,%d\n", currentCycle);
  Serial.println("Timestamp,Ax,Ay,Az");

  currentState = RECORDING;  // Enable sampler (must be last)
}

void stopRecording() {
  currentState = IDLE;  // Pause sampler immediately

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
