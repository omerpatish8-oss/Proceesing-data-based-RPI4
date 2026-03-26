/**
 * Parkinson's Tremor Detection System - USB Serial Version
 * Safe & Simple communication via USB to Raspberry Pi
 * 
 * Features: 
 * 1. USB Serial (no GPIO UART needed!)
 * 2. Pause/Resume with button
 * 3. Stuck sensor detection & auto-reset
 * 4. 100 Hz sampling
 * 
 * Connection: ESP32 USB Micro → Raspberry Pi USB Port
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
const long TARGET_DURATION = 120000; // 2 minutes
const int SAMPLE_RATE_HZ = 100;       
const int SAMPLE_INTERVAL_MS = 1000 / SAMPLE_RATE_HZ;

// Stopwatch-style timing
unsigned long segmentStartTime = 0;   
unsigned long accumulatedTime = 0;    
unsigned long currentTotalTime = 0;   

// ================================================================
// STATE MACHINE
// ================================================================
enum State { IDLE, RECORDING, PAUSED, WAITING_NEXT, FINISHED };
State currentState = IDLE;

int currentCycle = 0;
const int MAX_CYCLES = 2;

// Timers
unsigned long lastSampleTime = 0;
unsigned long lastScreenUpdate = 0;
unsigned long lastLedBlink = 0;
unsigned long lastSensorCheck = 0;
unsigned long lastDebounceTime = 0;

// ================================================================
// SENSOR SAFETY
// ================================================================
float lastAx = 0, lastAy = 0, lastAz = 0;
int stuckCount = 0;
int failedReads = 0;
unsigned long lastSuccessfulRead = 0;
unsigned long sensorResets = 0;

const int MAX_STUCK = 15;
const int MAX_FAILED = 5;
const float STUCK_THRESHOLD = 0.001;

// Calibration (accelerometer only, for +/-2G range)
float aX_off = 0.301009, aY_off = 0.016101, aZ_off = 1.046231;

// ================================================================
// SETUP
// ================================================================
void setup() {
  // USB Serial - simple and safe!
  Serial.begin(115200);
  while (!Serial && millis() < 3000);
  
  Serial.println("\n╔════════════════════════════════════╗");
  Serial.println("║ Parkinson's System - USB Serial   ║");
  Serial.println("║ Safe & Simple                     ║");
  Serial.println("╚════════════════════════════════════╝");
  Serial.println("\nFeatures:");
  Serial.println("  • 100 Hz sampling");
  Serial.println("  • Pause/Resume");
  Serial.println("  • Auto sensor reset");
  Serial.println("  • USB Serial @ 115200");
  Serial.println();

  pinMode(PIN_GREEN, OUTPUT);
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  
  // Display
  Wire1.begin(18, 19);
  Wire1.setClock(400000);
  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("[ERROR] Display init failed!");
    while(1) {
      digitalWrite(PIN_RED, !digitalRead(PIN_RED));
      delay(100);
    }
  }
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  Serial.println("[OK] Display ready");
  
  // Sensor
  Wire.begin(21, 22);
  Wire.setClock(400000);
  Wire.setTimeOut(10);  // 10ms I2C timeout — prevents infinite hang if SDA/SCL disconnects mid-read
  if (!initSensor()) {
    Serial.println("[ERROR] Sensor init failed!");
    showError("Sensor Error", "Check wiring");
    while(1);
  }
  Serial.println("[OK] Sensor ready");
  
  // Hardware watchdog — reboots ESP32 if loop() hangs for >5 seconds
  const esp_task_wdt_config_t wdt_config = {
    .timeout_ms = 5000,             // 5-second timeout
    .idle_core_mask = 0,            // Don't watch idle tasks
    .trigger_panic = true           // Auto-reboot on expiry
  };
  esp_task_wdt_init(&wdt_config);   // Initialize with config struct (ESP-IDF v5.x API)
  esp_task_wdt_add(NULL);           // Watch the main (loopTask) task
  Serial.println("[OK] Watchdog armed (5s)");

  updateDisplay("READY", "Press button\nto start");
  Serial.println("SYSTEM_READY");
  Serial.println("\n[READY] Press button to start\n");
}

// ================================================================
// MAIN LOOP
// ================================================================
void loop() {
  esp_task_wdt_reset();  // Pet the watchdog — proves loop() is alive
  handleButton();

  switch (currentState) {
    case IDLE:
      if (millis() - lastLedBlink >= 1000) {
        lastLedBlink = millis();
        digitalWrite(PIN_GREEN, !digitalRead(PIN_GREEN));
      }
      break;
      
    case RECORDING:
      currentTotalTime = accumulatedTime + (millis() - segmentStartTime);
      
      // Sample sensor
      if (millis() - lastSampleTime >= SAMPLE_INTERVAL_MS) {
        lastSampleTime = millis();
        sampleSensor();
      }
      
      // Check sensor health
      if (millis() - lastSensorCheck >= 500) {
        lastSensorCheck = millis();
        if (!checkSensor()) {
          Serial.println("[ERROR] Sensor lost connection!");
          Serial.println("ERROR_SENSOR_LOST");
          resetSensor();
        }
      }
      
      // Update display
      if (millis() - lastScreenUpdate >= 1000) {
        lastScreenUpdate = millis();
        updateRecordingDisplay(false);
      }
      
      // Fast LED blink
      if (millis() - lastLedBlink >= 200) {
        lastLedBlink = millis();
        digitalWrite(PIN_GREEN, !digitalRead(PIN_GREEN));
      }
      
      // Check completion
      if (currentTotalTime >= TARGET_DURATION) {
        stopRecording();
      }
      break;

    case PAUSED:
      if (millis() - lastScreenUpdate >= 1000) {
        lastScreenUpdate = millis();
        updateRecordingDisplay(true);
      }
      
      if (millis() - lastLedBlink >= 800) {
        lastLedBlink = millis();
        digitalWrite(PIN_RED, !digitalRead(PIN_RED));
        digitalWrite(PIN_GREEN, LOW);
      }
      break;
      
    case WAITING_NEXT:
      if (millis() - lastLedBlink >= 500) {
        lastLedBlink = millis();
        digitalWrite(PIN_RED, !digitalRead(PIN_RED));
      }
      break;
      
    case FINISHED:
      digitalWrite(PIN_GREEN, HIGH);
      digitalWrite(PIN_RED, LOW);
      break;
  }
}

// ================================================================
// BUTTON HANDLER
// ================================================================
void handleButton() {
  if (digitalRead(PIN_BUTTON) == LOW) {
    if (millis() - lastDebounceTime > 500) {
      lastDebounceTime = millis();
      
      if (currentState == IDLE || currentState == WAITING_NEXT) {
        startRecording();
      }
      else if (currentState == RECORDING) {
        accumulatedTime += (millis() - segmentStartTime);
        currentTotalTime = accumulatedTime;
        currentState = PAUSED;
        Serial.println("PAUSE_CYCLE");
        Serial.println("[USER] PAUSED");
        updateRecordingDisplay(true);
      }
      else if (currentState == PAUSED) {
        segmentStartTime = millis();
        currentState = RECORDING;
        Serial.println("RESUME_CYCLE");
        Serial.println("[USER] RESUMED");
      }
    }
  }
}

// ================================================================
// SENSOR FUNCTIONS
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
  
  if (connected && (millis() - lastSuccessfulRead > 2000)) {
    return false;
  }
  
  return connected;
}

void sampleSensor() {
  sensors_event_t a, g, temp;
  
  // Try reading
  if (!mpu.getEvent(&a, &g, &temp)) {
    failedReads++;
    if (failedReads >= MAX_FAILED) {
      Serial.println("[CRITICAL] Too many read failures!");
      Serial.println("ERROR_READ_FAILED");
      resetSensor();
    }
    return;
  }
  
  // Success
  failedReads = 0;
  lastSuccessfulRead = millis();
  
  // Calculate with offsets (accelerometer only)
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
    if (stuckCount > 0) {
      Serial.println("[OK] Sensor recovered");
    }
    stuckCount = 0;
  }
  
  lastAx = ax;
  lastAy = ay;
  lastAz = az;
  
  // Output CSV (accelerometer only)
  Serial.printf("%lu,%.3f,%.3f,%.3f\n",
                currentTotalTime, ax, ay, az);
}

void resetSensor() {
  sensorResets++;
  Serial.printf("[RESET] Sensor reset #%lu\n", sensorResets);
  Serial.printf("SENSOR_RESET,%lu\n", sensorResets);
  
  Wire.end();
  delay(150);
  
  Wire.begin(21, 22);
  Wire.setClock(400000);
  Wire.setTimeOut(10);  // Re-apply I2C timeout after bus reinit
  delay(50);

  if (initSensor()) {
    Serial.println("[SUCCESS] Sensor reset OK");
    Serial.println("SENSOR_RESET_OK");
    stuckCount = 0;
    failedReads = 0;
  } else {
    Serial.println("[FAILED] Sensor reset failed");
    Serial.println("SENSOR_RESET_FAILED");
  }
}

// ================================================================
// STATE FUNCTIONS
// ================================================================

void startRecording() {
  currentCycle++;
  currentState = RECORDING;
  
  segmentStartTime = millis();
  accumulatedTime = 0;
  currentTotalTime = 0;
  
  digitalWrite(PIN_RED, LOW);
  digitalWrite(PIN_GREEN, LOW);
  
  Serial.println("\n╔═══════════════════════════════╗");
  Serial.printf("║ Recording Cycle #%d           ║\n", currentCycle);
  Serial.println("╚═══════════════════════════════╝");
  
  Serial.println("START_RECORDING");
  Serial.printf("CYCLE,%d\n", currentCycle);
  Serial.println("Timestamp,Ax,Ay,Az");
}

void stopRecording() {
  Serial.println("\n╔═══════════════════════════════╗");
  Serial.printf("║ Cycle #%d Complete           ║\n", currentCycle);
  Serial.printf("║ Sensor resets: %lu           ║\n", sensorResets);
  Serial.println("╚═══════════════════════════════╝\n");
  
  Serial.println("END_RECORDING");
  Serial.printf("RESETS,%lu\n", sensorResets);
  
  digitalWrite(PIN_GREEN, LOW);
  
  if (currentCycle < MAX_CYCLES) {
    currentState = WAITING_NEXT;
    updateDisplay("DONE", "Press for\nNext Cycle");
  } else {
    currentState = FINISHED;
    updateDisplay("FINISHED", "All cycles done");
    Serial.println("🎉 All cycles complete!");
    Serial.println("ALL_COMPLETE");
  }
}

// ================================================================
// DISPLAY FUNCTIONS
// ================================================================

void updateRecordingDisplay(bool isPaused) {
  long remaining = (TARGET_DURATION - currentTotalTime) / 1000;
  if (remaining < 0) remaining = 0;
  
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  
  if (isPaused) {
    display.print(F("PAUSED "));
    display.println(currentCycle);
  } else {
    display.print(F("Recording "));
    display.println(currentCycle);
  }
  
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
