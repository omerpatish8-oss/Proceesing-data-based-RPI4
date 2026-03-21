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
// File: esp32_usb_serial_safe.ino

// Measurement ranges
mpu.setAccelerometerRange(MPU6050_RANGE_4_G);      // ±4g
mpu.setGyroRange(MPU6050_RANGE_500_DEG);           // ±500°/s

// Built-in hardware filter (DLPF - Digital Low Pass Filter)
mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);        // 21 Hz LPF
```

### **What Happens Inside the MPU6050:**

#### **1. Physical Sensor:**
- **Accelerometer:** Measures linear acceleration (including gravity)
- **Gyroscope:** Measures angular velocity (rotation)
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

#### **3. Calibration:**

```cpp
// Remove sensor offset
float ax = a.acceleration.x - aX_off;  // aX_off = 0.58
float ay = a.acceleration.y - aY_off;  // aY_off = -0.20
float az = a.acceleration.z - aZ_off;  // aZ_off = -1.23

float gx = (g.gyro.x * 57.296) - gX_off;  // Convert rad/s to deg/s
float gy = (g.gyro.y * 57.296) - gY_off;
float gz = (g.gyro.z * 57.296) - gZ_off;
```

**What Calibration Does:**
- Removes DC offset (constant bias) of the sensor
- **But does NOT remove gravity!**

#### **4. Data Format:**

```
Timestamp,Ax,Ay,Az,Gx,Gy,Gz
0,0.580,-0.200,-1.230,22.360,5.810,0.170
10,0.582,-0.198,-1.228,22.358,5.808,0.168
```

**Units:**
- **Timestamp:** milliseconds (ms)
- **Ax, Ay, Az:** acceleration (m/s²) - **includes gravity!**
- **Gx, Gy, Gz:** angular velocity (°/s)

### **📊 ESP32 Stage Summary:**

```
Real acceleration + gravity (9.81 m/s²)
           ↓
      [MPU6050 ADC]
           ↓
  [DLPF Hardware: 21 Hz LPF]  ← Hardware filter!
           ↓
    [100 Hz Sampling]
           ↓
   [Remove sensor offset]
           ↓
      [USB Serial]
           ↓
    CSV with data:
    - Filtered at 21 Hz
    - Still has gravity
    - No sensor offset
```

---

## 📈 Stage 2: Offline Analyzer - Software Processing

### **Input: CSV File**

```python
# offline_analyzer.py

# Load data from CSV
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

### **Stage 2.4: PSD Analysis on Independent Filtered Axes**

```python
nperseg = min(len(ax_filt), int(FS * 4))  # 4-second window
noverlap = int(nperseg * 0.5)              # 50% overlap

# Welch PSD on each filtered axis independently
f, psd_ax = welch(ax_filt, FS, nperseg=nperseg, noverlap=noverlap)
_, psd_ay = welch(ay_filt, FS, nperseg=nperseg, noverlap=noverlap)
_, psd_az = welch(az_filt, FS, nperseg=nperseg, noverlap=noverlap)

# Sum of per-axis PSDs = total spectral power
psd_total = psd_ax + psd_ay + psd_az
```

**Why PSD on Individual Axes (Not on Resultant)?**

The resultant vector `R = sqrt(x² + y² + z²)` is a **nonlinear** operation.
Taking the PSD of R would introduce **frequency doubling artifacts** — spurious
harmonics at 2× the true tremor frequency. By computing PSD on each linear
(filtered) axis and summing, we get the correct total spectral power without
any mathematical distortion.

**Welch Parameters:**

| Parameter | Value | Explanation |
|-----------|-------|-------------|
| **Window size** | 4 seconds (400 samples) | Window length for analysis |
| **Overlap** | 50% (200 samples) | Overlap between windows |
| **Frequency resolution** | 0.25 Hz | Frequency detection accuracy |
| **Window type** | Hann (default) | Reduces spectral leakage |

### **Stage 2.5: Calculate Metrics**

```python
# Dominant frequency: highest PSD peak in 2-8 Hz band
rest_mask = (freq >= 2.0) & (freq <= 8.0)
band_psd = psd_total[rest_mask]
peak_idx = np.argmax(band_psd)
metrics['dominant_freq'] = freq[rest_mask][peak_idx]

# SNR: peak PSD vs MPU6050 sensor noise floor
# MPU6050 datasheet: 400 µg/√Hz noise density
# Per-axis noise PSD = (400e-6 * 9.81)² (m/s²)²/Hz
# 3-axis sum → sensor_noise_floor = 3 × per-axis noise PSD
sensor_noise_floor = 3 * MPU6050_NOISE_PSD
metrics['snr_db'] = 10 * log10(peak_psd / sensor_noise_floor)

# DPR: integrated power around peak (±1 bin) / total band power
peak_power = trapz(psd[peak ± 1 bin])
total_power = trapz(psd[2-8 Hz])
metrics['dominant_power_ratio'] = peak_power / total_power
```

#### **📊 Detailed Clinical Metrics Explanation:**

**1️⃣ MEAN (Average) - `accel_mean`**
```python
mean = np.mean(signal_filtered)  # Arithmetic mean
```
- **What it is:** Average of all filtered samples
- **Units:** **m/s²** (meters per second squared)
- **Normal range:** ±0.01 m/s² (close to zero)
- **Clinical meaning:**
  - **~0:** Symmetric oscillations (good!)
  - **>0.1:** Bias present - DC may not be fully removed
- **Where in plots:**
  - Figure 2/3, Plot 2: Imaginary horizontal line through signal center
  - Figure 3, Plot 2: Average level of resultant vector

**2️⃣ RMS (Root Mean Square) - `accel_rms`**
```python
rms = √[mean(signal²)]  # Root mean square
```
- **What it is:** **Primary severity metric!** Average tremor magnitude
- **Units:** **m/s²** (meters per second squared)
- **Formula step-by-step:**
  1. `squared = signal ** 2` - Square each sample
  2. `mean_squared = mean(squared)` - Average
  3. `rms = √(mean_squared)` - Square root
- **Why RMS and not Mean?**
  - RMS **always positive** (even if signal goes up and down)
  - RMS equivalent to **energy** of signal
  - **International standard** for tremor severity
- **Severity scale:**
  - **< 0.10 m/s²** → Mild
  - **0.10-0.30 m/s²** → Moderate
  - **> 0.30 m/s²** → **SEVERE**
- **Where in plots:**
  - **Figure 2, Fig 2.2** (Y-Axis Filtered): Title shows RMS!
  - **Figure 3, Fig 3.2** (Resultant Filtered): Also in title!
  - **Example from your data:** RMS: 1.6238 m/s² → **SEVERE!**

**3️⃣ MAX (Maximum) - `accel_max`**
```python
max_amplitude = np.max(np.abs(signal))  # Absolute maximum
```
- **What it is:** Strongest tremor peak
- **Units:** **m/s²**
- **Meaning:**
  - Sharp peaks = unstable tremor
  - High peaks = very strong tremor moments
- **Where in plots:**
  - Figure 2/3, Plot 2: Highest/lowest point
  - Figure 2/3, Plot 2: Edge of envelope

**4️⃣ POWER (Spectral Power) - `power_rest`, `power_ess`**
```python
# Integration of PSD over frequency range using trapezoidal rule
# Power = ∫[f1 to f2] PSD(f) df
power_rest = np.trapz(psd[3-7 Hz], freq[3-7 Hz])
power_ess = np.trapz(psd[6-12 Hz], freq[6-12 Hz])
```
- **What it is:** **Integral (area under curve)** of PSD in frequency range
- **Units:** **m²/s⁴** (meters squared per second to the fourth)

  **📐 Unit Derivation:**
  - PSD units: (m/s²)²/Hz = **m²/s⁴/Hz** (power spectral **density**)
  - Integration: Power = ∫PSD(f) df
  - Result: (m²/s⁴/Hz) × Hz = **m²/s⁴** (Hz cancels out)

- **Mathematical explanation:**
  ```
  PSD(f) = Power spectral density at frequency f [m²/s⁴/Hz]

  Power = ∫[f1 to f2] PSD(f) df = Area under PSD curve

  Discrete approximation (trapezoidal integration):
  Power ≈ Σ[(PSD[i] + PSD[i+1])/2 × Δf]
  ```

- **Why Integration and Not Simple Sum?**
  - ❌ **Wrong:** `power = np.sum(psd[mask])`
    - Units: m²/s⁴/Hz (missing the Hz integration!)
    - Underestimates power
  - ✅ **Correct:** `power = np.trapz(psd[mask], freq[mask])`
    - Units: m²/s⁴ (proper integral)
    - Accounts for frequency spacing
    - Standard practice in signal processing
- **Typical values:**
  - **Power < 2:** Weak tremor in this band
  - **Power 2-5:** Moderate tremor
  - **Power > 5:** Strong tremor in this band
- **Use for classification:**
  ```python
  ratio = power_rest / power_ess
  if ratio > 2.0:  → Rest Tremor
  if ratio < 0.5:  → Essential Tremor
  else:            → Mixed
  ```
- **Where in plots:**
  - **Figure 4, Fig 4.1** (PSD Y-Axis): Colored areas!
    - Pink area (3-7 Hz) = Rest
    - Blue area (6-12 Hz) = Essential
  - **Figure 4, Fig 4.2** (PSD Resultant): Same areas
  - **Figure 4, Fig 4.3** (Bar Chart): **The bars themselves!**
    - Red bar height = `power_rest`
    - Blue bar height = `power_ess`

**5️⃣ DOMINANT FREQUENCY & PEAK PSD**
```python
# Find peak in tremor frequency range
tremor_mask = (freq >= 3) & (freq <= 12)
peak_idx = np.argmax(psd[tremor_mask])  # Find peak
dominant_freq = freq[tremor_mask][peak_idx]       # Frequency at peak
peak_power_density = psd[tremor_mask][peak_idx]   # PSD value at peak
```
- **Dominant Frequency:**
  - **What it is:** Frequency with maximum power spectral density
  - **Units:** **Hz** (Hertz - cycles per second)
  - **Clinical meaning:**
    - **3-5 Hz:** Typical rest tremor (Parkinson's)
    - **5-7 Hz:** Borderline
    - **8-12 Hz:** Essential tremor

- **Peak PSD:**
  - **What it is:** Maximum PSD value in tremor range
  - **Units:** **m²/s⁴/Hz** (power spectral **density** - note the /Hz!)
  - **Not the same as integrated Power!**
    - Peak PSD = height of peak in PSD plot
    - Power = area under PSD curve
  - **Used for:** Marking the peak on PSD plots

- **Where in plots:**
  - **Figure 4, Fig 4.1 & 4.2**: **Red circle ● on peak!**
  - Label: `Peak: 5.75 Hz` (example)
  - Height of red circle = Peak PSD value (in dB for plotting)

---

#### **🔗 Correlation Table: Metrics ↔ Plots**

| Metric | Example Value | Units | Where to See | How to Identify |
|--------|---------------|-------|--------------|----------------|
| **Mean** | 0.0014 | m/s² | Figure 2/3, Plot 2 | Imaginary horizontal line (near zero) |
| **RMS** | 1.6238 | m/s² | Figure 2/3, Plot 2 | **In plot title!** "RMS: X.XXXX" |
| **Max** | 8.8714 | m/s² | Figure 2/3, Plot 2 | Highest point |
| **Power Rest** | 6.5008 | m²/s⁴ | Figure 4, Plot 3 | **Red bar height** (integrated!) |
| **Power Ess** | 8.7993 | m²/s⁴ | Figure 4, Plot 3 | **Blue bar height** (integrated!) |
| **Dom. Freq** | 5.75 | Hz | Figure 4, Plot 1&2 | **Red circle ● position** |
| **Peak PSD** | 2.731 | m²/s⁴/Hz | Figure 4, Plot 1&2 | **Red circle ● height** (in dB) |

**Example from Your Data - Complete Decoding:**
```
┌─ Clinical Metrics (Table in Figure 1) ─┐
│                                         │
│ Axis RMS (Y): 3.5928 m/s²              │ ← Y-axis RMS only
│ Resultant RMS: 1.6238 m/s²             │ ← Resultant vector RMS
│ Mean: 0.0014 m/s²                      │ ← Close to zero ✓
│ Max: 8.8714 m/s²                       │ ← Very high peak!
│                                         │
│ Rest (3-7 Hz):                         │
│   Power: 6.5008 m²/s⁴                  │ ← Red bar in chart
│                                         │
│ Essential (6-12 Hz):                   │
│   Power: 8.7993 m²/s⁴                  │ ← Blue bar (higher!)
│                                         │
│ Ratio: 0.74                            │ ← 6.5/8.8 = 0.74
│ Type: Mixed Tremor                     │ ← Because 0.5 < 0.74 < 2.0
│ Confidence: Moderate                   │
│                                         │
│ Dominant Freq: 5.75 Hz                 │ ← Red circle in PSD
└─────────────────────────────────────────┘
```

**Correlation to Plots (MATLAB-style tabbed interface):**
1. **Figure 4, Fig 4.3** (Bar Chart):
   - Red bar height 6.5 ← Power Rest
   - Blue bar height 8.8 ← Power Essential
   - Blue > Red → Essential slightly dominant

2. **Figure 4, Fig 4.1 & 4.2** (PSD):
   - Red circle ● at 5.75 Hz ← Dominant Frequency
   - Blue area (6-12) higher ← Essential stronger

3. **Figure 2, Fig 2.2** (Y-Axis Filtered):
   - Title: "RMS: 3.5928 m/s²" ← Y-axis RMS
   - Wide signal width ← High RMS

4. **Figure 3, Fig 3.2** (Resultant Filtered):
   - Title: "RMS: 1.6238 m/s²" ← Resultant vector RMS
   - Wide envelope ← Strong tremor

**Navigation:**
- Click "Figure 1" tab for metrics table
- Click "Figure 2" tab for Y-axis analysis
- Click "Figure 3" tab for resultant vector analysis
- Click "Figure 4" tab for frequency (PSD) analysis

### **Stage 2.8: Tremor Classification**

```python
power_ratio = power_rest / (power_ess + 1e-10)

if power_ratio > 2.0:
    tremor_type = "Rest Tremor (Parkinsonian)"      # Parkinson's
    confidence = "High"
elif power_ratio < 0.5:
    tremor_type = "Essential Tremor (Postural)"     # Essential
    confidence = "High"
else:
    tremor_type = "Mixed Tremor"                    # Mixed
    confidence = "Moderate"
```

---

## 📊 Complete Processing Chain Summary

### **Stage 1: ESP32 (Hardware)**
```
Physical acceleration + gravity (9.81 m/s²)
           ↓
   [16-bit ADC in MPU6050]
           ↓
 [DLPF Hardware: 21 Hz]  ← Hardware Low-Pass filter
           ↓
   [100 Hz Sampling]
           ↓
 [Remove sensor offset]
           ↓
  [Calibration: ±4g, ±500°/s]
           ↓
    CSV: Ax, Ay, Az (m/s²)
    - Filtered at 21 Hz
    - Includes gravity
```

### **Stage 2: Offline Analyzer (Software)**
```
CSV with raw data (Ax, Ay, Az including gravity)
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
[PSD on Individual Axes]      ← Welch on Ax_f, Ay_f, Az_f separately
  - Sum of per-axis PSDs       ← Avoids frequency doubling
  - Window: 4 sec, Overlap: 50%
  - Resolution: 0.25 Hz
           ↓
[Calculate Metrics]
  - Dominant frequency (Hz)
  - RMS amplitude (m/s²)
  - Peak SNR vs sensor noise floor (dB)
  - Max amplitude (m/s²)
  - DPR (dominant power ratio)
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
- We analyze only 3-12 Hz, so **this doesn't interfere**
- But if we wanted to analyze higher frequencies (15-20 Hz), we'd be limited

### **3. Thermal Noise and Measurement Noise:**
✅ **Good!** Filter removes high-frequency noise:
- Electronic noise (> 21 Hz)
- Motor noise (if at high frequencies)
- Environmental noise

### **4. Minor Phase Distortion:**
⚠️ Hardware filter may add small phase distortion at 3-12 Hz
- **But:** Our `filtfilt()` corrects this!
- **Result:** Zero overall distortion

---

## 📐 Summary Table: All Filters in the System

| Stage | Filter | Type | Passband | Cutoff | Roll-off | Zero-Phase? |
|-------|--------|------|----------|--------|----------|-------------|
| **ESP32** | DLPF (MPU6050) | Low-Pass | DC - 21 Hz | 21 Hz | ~20 dB/dec | ❌ No |
| **Analyzer 1** | Combined Tremor | Bandpass | 3-12 Hz | 3 Hz, 12 Hz | 48 dB/oct | ✅ Yes |
| **Analyzer 2** | Rest Tremor | Bandpass | 3-7 Hz | 3 Hz, 7 Hz | 48 dB/oct | ✅ Yes |
| **Analyzer 3** | Essential Tremor | Bandpass | 6-12 Hz | 6 Hz, 12 Hz | 48 dB/oct | ✅ Yes |

---

## 💡 Important Points to Understand

### **1. Why don't we filter more on ESP32?**
- The 21 Hz filter is **anti-aliasing** only
- Tremor-specific filtering (3-12 Hz) is done **only in analysis**
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
- **Frequency resolution:** 0.25 Hz (good enough for 3-12 Hz)
- **Noise reduction:** Averaging over windows improves SNR
- **Standard:** Common in tremor analysis

---

## ✅ Passband Summary

```
Frequencies (Hz):  0    3    6    7    12   21   50 (Nyquist)
                   |____|____|____|____|____|____|
ESP32 DLPF:        |████████████████████████|      ← 21 Hz LPF
Rest Tremor:       |    |████████|                 ← 3-7 Hz BPF
Essential:         |         |████████|            ← 6-12 Hz BPF
Combined:          |    |████████████████|         ← 3-12 Hz BPF

████ = Passband
|    = Cutoff frequency
```

---

**Final Summary:**
1. **ESP32:** 21 Hz hardware filter (anti-aliasing)
2. **Analyzer:** 3 Butterworth Order 4 filters (3-12 Hz, 3-7 Hz, 6-12 Hz)
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
