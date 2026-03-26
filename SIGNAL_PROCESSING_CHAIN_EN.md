# Signal Processing Chain - Tremor Analysis System
# From ESP32 to Analysis

**Date:** 2026-01-25
**System:** ESP32 + MPU6050 → Raspberry Pi → Offline Analyzer

---

## 🔄 Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ESP32 FIRMWARE (Hardware)                         │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
        [MPU6050 Sensor] → [Hardware LPF 21 Hz] → [ADC] → [Calibration]
                              ↓
                     [USB Serial 115200 baud]
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│              RASPBERRY PI (Data Recording)                           │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
                  [CSV File: Raw + Calibrated Data]
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│         OFFLINE ANALYZER (Signal Processing & Classification)        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Stage 1: ESP32 Firmware - Hardware Processing

### **MPU6050 Configuration:**

```cpp
// File: esp32_usb_serial_safe_V2.ino

// Measurement range (accelerometer only — no gyroscope used)
mpu.setAccelerometerRange(MPU6050_RANGE_2_G);      // ±2g

// Built-in hardware filter (DLPF - Digital Low Pass Filter)
mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);        // 21 Hz LPF
```

### **What Happens Inside the MPU6050:**

#### **1. Physical Sensor:**
- **Accelerometer:** Measures linear acceleration (including gravity)
- **Gyroscope:** Present in MPU6050 but **not used** by firmware
- **Internal sampling:** 1 kHz (1000 Hz)

#### **2. Built-in Hardware Filter - DLPF (Digital Low Pass Filter):**

**MPU6050_BAND_21_HZ = Low Pass Filter inside the sensor!**

| Parameter | Value |
|-----------|-------|
| **Filter Type** | Low-Pass Filter (passes low frequencies) |
| **Cutoff Frequency (-3dB)** | **21 Hz** |
| **Method** | FIR/IIR digital filter inside sensor chip |
| **Effective Sampling Rate** | 100 Hz (set in firmware) |
| **Purpose** | High-frequency noise filtering, anti-aliasing |

**📌 Important to Understand:**
- **This filter operates in hardware BEFORE data reaches our code!**
- **We cannot disable it - the data we receive is already filtered at 21 Hz**
- **All frequencies above ~21 Hz are already significantly attenuated**

#### **3. Calibration (accelerometer only):**

```cpp
// Remove sensor offset (accelerometer only, for ±2G range)
float aX_off = 0.301009, aY_off = 0.016101, aZ_off = 1.046231;

float ax = a.acceleration.x - aX_off;
float ay = a.acceleration.y - aY_off;
float az = a.acceleration.z - aZ_off;
```

**What Calibration Does:**
- Removes DC offset (constant bias) of the sensor
- **But does NOT remove gravity!**

#### **4. Data Format:**

```
Timestamp,Ax,Ay,Az
0,0.580,-0.200,-1.230
10,0.582,-0.198,-1.228
```

**Units:**
- **Timestamp:** milliseconds (ms)
- **Ax, Ay, Az:** acceleration (m/s²) - **includes gravity!**

### **📊 ESP32 Stage Summary:**

```
Real acceleration + gravity (9.81 m/s²)
           ↓
      [MPU6050 ADC, ±2g range]
           ↓
  [DLPF Hardware: 21 Hz LPF]  ← Hardware filter!
           ↓
    [100 Hz Sampling]
           ↓
   [Remove sensor offset (accel only)]
           ↓
      [USB Serial]
           ↓
    CSV with data (4 columns):
    Timestamp, Ax, Ay, Az
    - Filtered at 21 Hz
    - Still has gravity
    - No sensor offset
```

---

## 📈 Stage 2: Offline Analyzer - Software Processing

### **Input: CSV File**

```python
# offline_analyzer_exp.py

# Load data from CSV (4 columns, accelerometer only)
ax = data['Ax']  # m/s² (includes gravity, filtered at 21 Hz)
ay = data['Ay']
az = data['Az']
t = data['Timestamp'] / 1000.0  # Convert to seconds
```

### **Stage 2.1: Independent Axis Filtering (DC Removal + Noise Reduction)**

```python
# Create Butterworth bandpass filter (2-8 Hz)
b_tremor, a_tremor = butter(4, [2.0/nyquist, 8.0/nyquist], btype='band')

# Apply to each axis independently via zero-phase filtering
ax_filt = filtfilt(b_tremor, a_tremor, ax)
ay_filt = filtfilt(b_tremor, a_tremor, ay)
az_filt = filtfilt(b_tremor, a_tremor, az)
```

**Why Filter First, Per-Axis?**

This single step accomplishes three things simultaneously:
1. **Removes DC (gravity):** The bandpass has no gain at 0 Hz, so the constant gravity
   component on each axis is automatically eliminated — no mean subtraction needed.
2. **Removes high-frequency noise:** Everything above 8 Hz (motor vibration, sensor noise) is attenuated.
3. **Handles wrist rotation correctly:** Unlike mean subtraction (which assumes gravity is
   constant on each axis), the bandpass correctly handles the case where gravity's projection
   shifts between axes due to hand rotation — because those slow orientation changes are
   below 2 Hz and are rejected by the filter.

**Butterworth Order 4 + filtfilt:**

| Property | Value |
|----------|-------|
| **Passband** | 2-8 Hz (extended from clinical 3-7 Hz to preserve band edges) |
| **Roll-off** | 48 dB/octave (effective, doubled by filtfilt) |
| **Passband Ripple** | 0 dB (maximally flat) |
| **Phase distortion** | Zero (filtfilt = forward-backward filtering) |

**How filtfilt works:**
```
Signal → [Filter Forward] → [Reverse] → [Filter Backward] → Result
```
- Doubles the roll-off slope (24 → 48 dB/octave)
- Cancels all phase distortion → events stay at correct time
- Critical for medical analysis where timing matters

### **Stage 2.2: Resultant Vector from Filtered Axes**

```python
# Combine filtered axes into a single 1D scalar wave
result_filtered = np.sqrt(ax_filt**2 + ay_filt**2 + az_filt**2)
```

**What This Does:**
- Converts 3 filtered axes into a single **magnitude** value at each sample
- Captures **100% of the true kinetic energy** of the tremor
- Direction-independent: measures overall tremor severity regardless of sensor orientation

**Why After Filtering (Not Before)?**

The `sqrt(x² + y² + z²)` operation is **nonlinear**. If applied to unfiltered data
(which contains a large DC gravity offset), the nonlinearity distorts the signal
and creates spurious frequency content. By filtering first:
- Each axis is a clean, zero-mean tremor oscillation
- The magnitude faithfully represents the 3D tremor envelope
- No gravity-induced artifacts contaminate the result

### **Stage 2.3: RMS Amplitude (Total Tremor Intensity)**

```python
# Root Mean Square of the filtered resultant vector
metrics['accel_rms'] = np.sqrt(np.mean(result_filtered**2))
```

**Step by step:**
1. `squared = result_filtered ** 2` — Square each sample
2. `mean_squared = mean(squared)` — Average all squared values
3. `rms = sqrt(mean_squared)` — Take the square root

**Why RMS?**
- RMS is proportional to the **total kinetic energy** of the tremor
- Always positive (unlike mean, which cancels out for symmetric oscillations)
- **International clinical standard** for tremor severity measurement
- Computed from the filtered resultant → captures 100% of 3D tremor energy

### **Stage 2.4: PSD Analysis & Dominant Axis Selection**

```python
nperseg = min(len(ax_filt), int(FS * 4))  # 4-second window
noverlap = int(nperseg * 0.5)              # 50% overlap

# Welch PSD on each filtered axis independently
f, psd_ax = welch(ax_filt, FS, nperseg=nperseg, noverlap=noverlap)
_, psd_ay = welch(ay_filt, FS, nperseg=nperseg, noverlap=noverlap)
_, psd_az = welch(az_filt, FS, nperseg=nperseg, noverlap=noverlap)

# Identify dominant axis: whichever holds the absolute max PSD peak in 2-8 Hz
rest_mask = (f >= 2.0) & (f <= 8.0)
peaks = {
    'X': max(psd_ax[rest_mask]),
    'Y': max(psd_ay[rest_mask]),
    'Z': max(psd_az[rest_mask]),
}
dominant_axis = max(peaks, key=peaks.get)  # e.g. 'Y'
psd_dominant = {'X': psd_ax, 'Y': psd_ay, 'Z': psd_az}[dominant_axis]
```

**Why PSD on Individual Axes (Not on Resultant)?**

The resultant vector `R = sqrt(x² + y² + z²)` is a **nonlinear** operation.
Taking the PSD of R would introduce **frequency doubling artifacts** — spurious
harmonics at 2× the true tremor frequency. By computing PSD on each linear
(filtered) axis, we get a clean spectrum without mathematical distortion.

**Why Select One Dominant Axis?**

The axis with the strongest PSD peak carries the clearest tremor signal.
Using its PSD exclusively for frequency-domain metrics (SNR, DPR, dominant freq)
ensures these metrics are not diluted by noise from weaker axes. The PSD plot
and FFT plot also show the dominant axis only for clarity.

**Welch Parameters:**

| Parameter | Value | Explanation |
|-----------|-------|-------------|
| **Window size** | 4 seconds (400 samples) | Window length for analysis |
| **Overlap** | 50% (200 samples) | Overlap between windows |
| **Frequency resolution** | 0.25 Hz | Frequency detection accuracy |
| **Window type** | Hann (default) | Reduces spectral leakage |

### **Stage 2.5: Calculate Metrics**

**Time-domain metric** — computed from the **resultant vector** (captures full 3D energy):
```python
metrics['accel_rms'] = sqrt(mean(result_filtered**2))   # RMS
```

**Frequency-domain metrics** — computed from the **dominant axis PSD** only:
```python
# Dominant frequency: highest PSD peak in 2-8 Hz on dominant axis
band_psd = psd_dominant[rest_mask]
peak_idx = argmax(band_psd)
metrics['dominant_freq'] = freq[rest_mask][peak_idx]
metrics['peak_power_density'] = band_psd[peak_idx]

# Total band power (integrated PSD across 2-8 Hz)
metrics['total_power'] = trapz(psd_dominant[2-8 Hz], freq[2-8 Hz])

# DPR: integrated power around peak (±1 bin) / total band power
peak_power = trapz(psd_dominant[peak ± 1 bin], freq[peak ± 1 bin])
metrics['dominant_power_ratio'] = peak_power / total_power

# Deviation from motor PWM frequency (informational, no pass/fail)
metrics['deviation'] = abs(dominant_freq - pwm_freq)
```

#### **📊 Detailed Metrics Explanation:**

**1️⃣ RMS (Root Mean Square) - `accel_rms`**
```python
rms = √[mean(result_filtered²)]  # Root mean square of resultant vector
```
- **What it is:** **Primary severity metric!** Average tremor magnitude
- **Units:** **m/s²** (meters per second squared)
- **Formula step-by-step:**
  1. `result_filtered = sqrt(ax_filt² + ay_filt² + az_filt²)` — Resultant at each sample
  2. `squared = result_filtered ** 2` — Square each sample
  3. `mean_squared = mean(squared)` — Average
  4. `rms = √(mean_squared)` — Square root
- **Why RMS?**
  - RMS **always positive** (even if signal goes up and down)
  - RMS equivalent to **energy** of signal
  - **International standard** for tremor severity
- **Severity scale:**
  - **< 0.10 m/s²** → Mild
  - **0.10-0.30 m/s²** → Moderate
  - **> 0.30 m/s²** → **SEVERE**
- **Where in plots:**
  - **Figure 2, Fig 2.1** (Dominant Axis Raw): Title shows RMS
  - **Figure 3, Fig 3.3** (Metrics panel): Listed as "RMS Amplitude"

**2️⃣ DOMINANT FREQUENCY - `dominant_freq`**
```python
# Find peak in the 2-8 Hz analysis band on the dominant axis PSD
rest_mask = (freq >= 2.0) & (freq <= 8.0)
peak_idx = np.argmax(psd_dominant[rest_mask])
dominant_freq = freq[rest_mask][peak_idx]
```
- **What it is:** Frequency with maximum power spectral density
- **Units:** **Hz** (Hertz - cycles per second)
- **Clinical meaning:**
  - **3-5 Hz:** Typical rest tremor (Parkinson's)
  - **5-7 Hz:** Borderline
  - **8-12 Hz:** Essential tremor
- **Where in plots:**
  - **Figure 3, Fig 3.1 & 3.2**: **Red circle ● on peak!**
  - **Figure 6** (FFT): Red circle on FFT peak

**3️⃣ PEAK PSD - `peak_power_density`**
```python
peak_power_density = psd_dominant[rest_mask][peak_idx]
```
- **What it is:** Maximum PSD value in the 2-8 Hz band
- **Units:** **(m/s²)²/Hz** (power spectral **density**)
- **Not the same as integrated Power!**
  - Peak PSD = height of peak in PSD plot
  - Band Power = area under PSD curve
- **Where in plots:**
  - **Figure 3, Fig 3.1 & 3.2**: Height of red circle ● (in dB for plotting)

**4️⃣ BAND POWER (Total Power) - `total_power`**
```python
# Integration of PSD over 2-8 Hz using trapezoidal rule
total_power = np.trapz(psd_dominant[2-8 Hz], freq[2-8 Hz])
```
- **What it is:** **Integral (area under curve)** of PSD in the analysis band
- **Units:** **(m/s²)²** = **m²/s⁴**

  **📐 Unit Derivation:**
  - PSD units: (m/s²)²/Hz = m²/s⁴/Hz (power spectral **density**)
  - Integration: Power = ∫PSD(f) df
  - Result: (m²/s⁴/Hz) × Hz = **m²/s⁴** (Hz cancels out)

- **Why Integration and Not Simple Sum?**
  - ✅ **Correct:** `power = np.trapz(psd[mask], freq[mask])`
    - Units: m²/s⁴ (proper integral)
    - Accounts for frequency spacing
    - Standard practice in signal processing
- **Where in plots:**
  - **Figure 3, Fig 3.3** (Metrics panel): Listed as "Band Power"

**5️⃣ DOMINANT POWER RATIO (DPR) - `dominant_power_ratio`**
```python
# Power concentrated around the peak (±1 bin = ±0.25 Hz)
peak_power = trapz(psd_dominant[peak-1 .. peak+1], freq[peak-1 .. peak+1])
total_power = trapz(psd_dominant[2-8 Hz], freq[2-8 Hz])
DPR = peak_power / total_power
```
- **What it is:** Fraction of total band power concentrated at the dominant frequency
- **Units:** Dimensionless (0 to 1, displayed as percentage)
- **Interpretation:**
  - **DPR close to 100%:** Nearly all energy at one frequency — strong, clean signal
  - **DPR close to 0%:** Energy spread across band — no dominant frequency, noise-like
- **Where in plots:**
  - **Figure 3, Fig 3.3** (Metrics panel): Listed as "Dom. Power Ratio"

**6️⃣ DEVIATION - `deviation`**
```python
deviation = abs(dominant_freq - pwm_freq)
```
- **What it is:** Difference between the detected dominant frequency and the motor PWM frequency
- **Units:** **Hz**
- **Purpose:** Informational only — no pass/fail judgment
- **Where in plots:**
  - **Figure 3, Fig 3.3** (Metrics panel): Listed as "Deviation"
  - **Figure 3, Fig 3.2** (PSD zoomed): Blue reference band around PWM frequency

---

#### **🔗 Correlation Table: Metrics ↔ Plots**

| Metric | Units | Where to See | How to Identify |
|--------|-------|--------------|----------------|
| **RMS** | m/s² | Figure 2, Fig 2.1 title; Figure 3, Fig 3.3 | **In plot title!** "RMS: X.XXXX" |
| **Dom. Freq** | Hz | Figure 3, Fig 3.1 & 3.2; Figure 6 | **Red circle ● position** |
| **Peak PSD** | (m/s²)²/Hz | Figure 3, Fig 3.1 & 3.2 | **Red circle ● height** (in dB) |
| **Band Power** | (m/s²)² | Figure 3, Fig 3.3 | Listed in metrics panel |
| **DPR** | % | Figure 3, Fig 3.3 | Listed in metrics panel |
| **Deviation** | Hz | Figure 3, Fig 3.2 & 3.3 | Blue PWM reference line + band |

**Navigation (tabbed interface):**
- Click "Figure 1" tab for filter characteristics (Bode magnitude & phase)
- Click "Figure 2" tab for dominant axis time-domain (raw & filtered, 40-80s view)
- Click "Figure 3" tab for PSD analysis & metrics panel
- Click "Figure 4" tab for zoomed 5s window A (mid-recording)
- Click "Figure 5" tab for zoomed 5s window B (consecutive)
- Click "Figure 6" tab for FFT magnitude (1-12 Hz, full 120s)

---

## 📊 Complete Processing Chain Summary

### **Stage 1: ESP32 (Hardware)**
```
Physical acceleration + gravity (9.81 m/s²)
           ↓
   [16-bit ADC in MPU6050, ±2g]
           ↓
 [DLPF Hardware: 21 Hz]  ← Hardware Low-Pass filter
           ↓
   [100 Hz Sampling]
           ↓
 [Remove sensor offset (accel only)]
           ↓
    CSV: Timestamp, Ax, Ay, Az (m/s²)
    - Filtered at 21 Hz
    - Includes gravity
```

### **Stage 2: Offline Analyzer Experimental (Software)**
```
CSV with raw data (Timestamp, Ax, Ay, Az including gravity)
           ↓
[Bandpass Filter Each Axis]   ← filtfilt(2-8 Hz) on Ax, Ay, Az independently
  - Removes DC (gravity) automatically
  - Removes high-freq noise
  - Handles wrist rotation correctly
           ↓
[Resultant Vector]            ← R = √(Ax_f² + Ay_f² + Az_f²)
  - From FILTERED axes
  - Captures 100% kinetic energy
           ↓
[RMS Amplitude]               ← √(mean(R²))
  - Total tremor intensity
           ↓
[PSD on Each Axis]            ← Welch on Ax_f, Ay_f, Az_f separately
  - Window: 4 sec, Overlap: 50%
  - Resolution: 0.25 Hz
           ↓
[Identify Dominant Axis]      ← Axis with absolute max PSD peak in 2-8 Hz
           ↓
[Calculate Metrics]
  Time-domain (from Resultant):
  - RMS amplitude (m/s²)
  Freq-domain (from Dominant Axis PSD):
  - Dominant frequency (Hz)
  - Peak PSD ((m/s²)²/Hz)
  - Band power ((m/s²)²)
  - DPR (dominant power ratio)
  - Deviation from PWM (Hz)
```

---

## 🔍 How Does the ESP32 21 Hz Filter Affect Analysis?

### **1. Anti-Aliasing:**
✅ **Good!** The 21 Hz filter prevents aliasing:
- Nyquist frequency = 50 Hz (half of 100 Hz)
- 21 Hz filter ensures no high frequencies cause aliasing

### **2. Bandwidth Limitation:**
⚠️ **Important to know!**
- All frequencies above 21 Hz are already attenuated in hardware
- We analyze only 2-8 Hz, so **this doesn't interfere**
- But if we wanted to analyze higher frequencies (15-20 Hz), we'd be limited

### **3. Thermal Noise and Measurement Noise:**
✅ **Good!** Filter removes high-frequency noise:
- Electronic noise (> 21 Hz)
- Motor noise (if at high frequencies)
- Environmental noise

### **4. Minor Phase Distortion:**
⚠️ Hardware filter may add small phase distortion at 2-8 Hz
- **But:** Our `filtfilt()` corrects this!
- **Result:** Zero overall distortion

---

## 📐 Summary Table: All Filters in the System

| Stage | Filter | Type | Passband | Cutoff | Roll-off | Zero-Phase? |
|-------|--------|------|----------|--------|----------|-------------|
| **ESP32** | DLPF (MPU6050) | Low-Pass | DC - 21 Hz | 21 Hz | ~20 dB/dec | ❌ No |
| **Analyzer** | Tremor Bandpass | Bandpass | 2-8 Hz | 2 Hz, 8 Hz | 48 dB/oct (filtfilt) | ✅ Yes |

---

## 💡 Important Points to Understand

### **1. Why don't we filter more on ESP32?**
- The 21 Hz filter is **anti-aliasing** only
- Tremor-specific filtering (2-8 Hz) is done **only in analysis**
- This allows changing parameters without changing firmware

### **2. Why Butterworth Order 4?**
- **Flat passband** (no ripples in passband)
- **Steep roll-off** (sharp slope - good separation)
- **Standard in research** (MDPI papers)
- **Optimal** balance between sharpness and delay

### **3. Why Zero-Phase (`filtfilt()`)?**
- **Preserves timing** of events
- **Important for clinical analysis** (when tremor occurs)
- **Doubles Roll-off** (48 dB/oct instead of 24)

### **4. Why Welch with 4-second windows?**
- **Frequency resolution:** 0.25 Hz (good enough for 2-8 Hz)
- **Noise reduction:** Averaging over windows improves SNR
- **Standard:** Common in tremor analysis

---

## ✅ Passband Summary

```
Frequencies (Hz):  0    2         8         21   50 (Nyquist)
                   |____|_________|_________|____|
ESP32 DLPF:        |████████████████████████|      ← 21 Hz LPF
Tremor BPF:        |    |█████████|                ← 2-8 Hz BPF (filtfilt)

████ = Passband
|    = Cutoff frequency
```

---

**Final Summary:**
1. **ESP32:** 21 Hz hardware filter (anti-aliasing), ±2g range, accelerometer only
2. **Analyzer:** 1 Butterworth Order 4 bandpass filter (2-8 Hz), applied per-axis via filtfilt
3. **All tremor-specific filtering is done in software!**
4. **Zero-Phase filtering preserves precise timing**

---

## 🎛️ Controlled Tremor Simulation for Validation

### **Motor-Based Tremor Simulator** (`motor_control.py`)

For algorithm validation and demonstration, the system includes a controlled motor simulator that generates tremor-like oscillations at specific frequencies.

### **Hardware Setup:**
```
L298N Motor Driver:
  - ENA (PWM) → GPIO 18 (Raspberry Pi)
  - IN1 → GPIO 23
  - IN2 → GPIO 24
  - 12V power supply

MPU6050 Sensor:
  - Attached to motor or held by hand holding motor
  - Measures tremor-like oscillations
```

### **Simulation Sequences:**

#### **1. Rest-Dominant Tremor Sequence** (120 seconds)
```python
# Simulates Parkinsonian rest tremor characteristics
# Frequency range: 4-6 Hz (within clinical 3-7 Hz band)

Segments (30s each):
  1. 4.0 Hz at 40% power  ← Low rest frequency
  2. 5.0 Hz at 45% power  ← Mid rest frequency
  3. 6.0 Hz at 50% power  ← High rest frequency (near overlap)
  4. 5.0 Hz at 42% power  ← Variation (realistic fluctuation)

Expected Classification: "Rest Tremor"
Expected Dominant Frequency: ~5 Hz
```

**Purpose:**
- Validates algorithm's ability to identify rest-band tremor (3-7 Hz)
- Demonstrates robustness to frequency variation
- Shows clear classification in rest tremor range

#### **2. Essential Tremor Sequence** (120 seconds)
```python
# Simulates postural/essential tremor characteristics
# Frequency range: 8-10 Hz (within clinical 6-12 Hz band)

Segments (30s each):
  1. 8.0 Hz at 45% power   ← Low essential frequency
  2. 9.0 Hz at 50% power   ← Mid essential frequency
  3. 10.0 Hz at 55% power  ← High essential frequency
  4. 9.0 Hz at 48% power   ← Variation (realistic fluctuation)

Expected Classification: "Essential Tremor"
Expected Dominant Frequency: ~9 Hz
```

**Purpose:**
- Validates algorithm's ability to identify essential-band tremor (6-12 Hz)
- Demonstrates clear separation from rest tremor frequencies
- Shows consistent classification across frequency range

### **Motor Control Mechanism:**

```python
# Oscillation generation (forward-reverse cycles)
period = 1.0 / frequency          # e.g., 5 Hz → 0.2s period
half_period = period / 2.0         # 0.1s per direction

while recording:
    motor.forward(amplitude)       # 0.1s forward
    time.sleep(half_period)
    motor.reverse(amplitude)       # 0.1s reverse
    time.sleep(half_period)
    # Result: 5 complete cycles per second (5 Hz)
```

### **Validation Methodology:**

**Phase 1 - Ground Truth Validation:**
1. Attach MPU6050 directly to motor (rigid coupling)
2. Run rest-dominant sequence (4-6 Hz)
3. Verify algorithm identifies rest tremor band
4. Run essential sequence (8-10 Hz)
5. Verify algorithm identifies essential tremor band

**Phase 2 - Biomechanical Damping Test:**
1. Hold motor in hand with sensor on finger
2. Run same sequences
3. Observe effect of biological damping
4. Document algorithm robustness to real-world conditions

### **Expected PSD Results:**

**Rest Sequence (4-6 Hz):**
```
PSD Analysis:
  - Dominant peak: ~5 Hz
  - Power in 3-7 Hz band: HIGH
  - Power in 6-12 Hz band: LOW
  - Ratio: > 2.0 → "Rest Tremor" ✓
```

**Essential Sequence (8-10 Hz):**
```
PSD Analysis:
  - Dominant peak: ~9 Hz
  - Power in 3-7 Hz band: LOW
  - Power in 6-12 Hz band: HIGH
  - Ratio: < 0.5 → "Essential Tremor" ✓
```

### **Clinical Significance:**

✅ **Controlled validation** - Known input frequencies
✅ **Reproducible** - Same test sequence every time
✅ **Educational** - Clear demonstration of algorithm capabilities
✅ **Professional** - Shows systematic validation approach

⚠️ **Limitations:**
- Motor oscillations are sinusoidal (real tremor may be more complex)
- Biological damping differs from real pathological tremor
- This is proof-of-concept validation, not clinical validation
- Real patient data required for clinical accuracy claims

### **Usage:**

```bash
# Interactive menu
python3 motor_control.py

# Direct sequence execution
python3 motor_control.py rest       # Run rest-dominant sequence
python3 motor_control.py essential  # Run essential sequence
python3 motor_control.py test       # Hardware test
```

### **Integration with Tremor Analysis:**

1. **Run motor sequence** while recording with ESP32
2. **Analyze recorded CSV** with `offline_analyzer.py`
3. **Verify classification** matches expected tremor type
4. **Document results** for validation report

This controlled simulation approach demonstrates the system's ability to distinguish tremor frequency bands under known conditions, providing confidence in the algorithm's clinical application.

---

Need clarification on any specific part?
