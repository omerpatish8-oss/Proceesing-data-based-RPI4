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

### **Stage 2.1: DC Offset Removal (Gravity Removal)**

```python
# Remove mean = remove gravity
ax_clean = ax - np.mean(ax)  # Remove DC component
ay_clean = ay - np.mean(ay)
az_clean = az - np.mean(az)
```

**Why This Works:**
- Gravity is **constant** over time → DC offset
- Tremor is **time-varying** → AC signal
- Subtracting the mean removes only the constant component (gravity), leaving oscillations (tremor)

**Example:**
```
Ay (raw):     [-1.2, -1.1, -1.3, -1.0, -1.2]  ← DC offset of -1.16
mean(Ay):     -1.16
Ay_clean:     [-0.04, +0.06, -0.14, +0.16, -0.04]  ← Only oscillations!
```

### **Stage 2.2: Calculate Resultant Vector**

```python
# Vector magnitude
accel_mag = np.sqrt(ax_clean**2 + ay_clean**2 + az_clean**2)
```

**What This Does:**
- Converts 3 axes (X, Y, Z) to a single scalar value
- Measures **total acceleration magnitude** regardless of direction
- Useful for measuring **overall tremor severity**

### **Stage 2.3: Identify Dominant Axis**

```python
# Calculate energy in each axis
energy_x = np.sum(ax_clean**2)  # Sum of squares = signal energy
energy_y = np.sum(ay_clean**2)
energy_z = np.sum(az_clean**2)

# Select axis with highest energy
max_axis = max({'X': energy_x, 'Y': energy_y, 'Z': energy_z})
```

**Why Important:**
- Identifies which **direction has the strongest tremor**
- Usually Y-axis (anterior-posterior) is dominant in hand tremor

### **Stage 2.4: Build Filters - Butterworth Filters**

#### **Parameters:**
```python
FS = 100.0              # Sampling frequency (Hz)
FILTER_ORDER = 4        # Filter order (Butterworth)
```

#### **3 Bandpass Filters:**

**1️⃣ Combined Tremor Filter:**
```python
b_tremor, a_tremor = butter(4, [3/nyquist, 12/nyquist], btype='band')
```
- **Type:** Butterworth Order 4
- **Passband:** **3-12 Hz**
- **Lower cutoff (-3dB):** 3 Hz
- **Upper cutoff (-3dB):** 12 Hz
- **Purpose:** Filter entire tremor range (Rest + Essential)

**2️⃣ Rest Tremor Filter:**
```python
b_rest, a_rest = butter(4, [3/nyquist, 7/nyquist], btype='band')
```
- **Type:** Butterworth Order 4
- **Passband:** **3-7 Hz**
- **Purpose:** Isolate Parkinsonian rest tremor

**3️⃣ Essential Tremor Filter:**
```python
b_ess, a_ess = butter(4, [6/nyquist, 12/nyquist], btype='band')
```
- **Type:** Butterworth Order 4
- **Passband:** **6-12 Hz**
- **Purpose:** Isolate postural/essential tremor

#### **Butterworth Order 4 Characteristics:**

| Property | Value |
|----------|-------|
| **Roll-off (slope)** | 24 dB/octave (80 dB/decade) |
| **Passband Ripple** | 0 dB (completely flat!) |
| **Phase** | Non-linear, but... |
| **Zero-phase?** | Yes! Thanks to `filtfilt()` |

### **Stage 2.5: Apply Filters - Zero-Phase Filtering**

```python
# Filter dominant axis
axis_filtered = filtfilt(b_tremor, a_tremor, dominant_axis)
axis_rest = filtfilt(b_rest, a_rest, dominant_axis)
axis_ess = filtfilt(b_ess, a_ess, dominant_axis)

# Filter resultant vector
result_filtered = filtfilt(b_tremor, a_tremor, accel_mag)
result_rest = filtfilt(b_rest, a_rest, accel_mag)
result_ess = filtfilt(b_ess, a_ess, accel_mag)
```

**Why `filtfilt()` and not `filter()`?**

`filtfilt()` = **Zero-Phase Filtering**
- **Filters forward and backward** (Forward-Backward)
- **No phase distortion** (No phase shift)
- **Preserves timing of features** (events stay at same time)
- **Important for medical analysis!** (doesn't change timing of tremor)

**How It Works:**
```
Signal → [Filter Forward] → [Reverse] → [Filter Backward] → Result
```
**Result:** 48 dB/octave slope (doubled!), zero phase shift

### **Stage 2.6: PSD Analysis - Power Spectral Density**

```python
nperseg = min(len(accel_mag), int(FS * 4))  # 4-second window
noverlap = int(nperseg * 0.5)                # 50% overlap

# Calculate PSD using Welch's method
f, psd = welch(signal, FS, nperseg=nperseg, noverlap=noverlap)
```

**Welch Parameters:**

| Parameter | Value | Explanation |
|-----------|-------|-------------|
| **Window size** | 4 seconds (400 samples) | Window length for analysis |
| **Overlap** | 50% (200 samples) | Overlap between windows |
| **Frequency resolution** | 0.25 Hz | Frequency detection accuracy |
| **Window type** | Hann (default) | Reduces spectral leakage |

**Why Welch's Method:**
- Divides signal into small windows
- Computes FFT for each window
- Averages the results
- **Reduces noise**, improves reliability

### **Stage 2.7: Calculate Clinical Metrics**

```python
# Features from Paper 1 (MDPI)
metrics['accel_mean'] = np.mean(accel_filt)              # Mean
metrics['accel_rms'] = np.sqrt(np.mean(accel_filt**2))  # RMS
metrics['accel_max'] = np.max(np.abs(accel_filt))       # Maximum

# Power in frequency bands
rest_mask = (freq >= 3) & (freq <= 7)
ess_mask = (freq >= 6) & (freq <= 12)

metrics['power_rest'] = np.sum(psd[rest_mask])      # Power at 3-7 Hz
metrics['power_ess'] = np.sum(psd[ess_mask])        # Power at 6-12 Hz

# Dominant frequency
tremor_mask = (freq >= 3) & (freq <= 12)
peak_idx = np.argmax(psd[tremor_mask])
metrics['dominant_freq'] = freq[tremor_mask][peak_idx]
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
CSV with raw data
           ↓
[Remove DC = remove gravity]  ← ax_clean = ax - mean(ax)
           ↓
[Calculate Resultant Vector]  ← mag = √(x² + y² + z²)
           ↓
[Identify Dominant Axis]      ← energy = Σ(signal²)
           ↓
[Butterworth Bandpass Filters]
  - Combined: 3-12 Hz (Order 4)
  - Rest: 3-7 Hz (Order 4)
  - Essential: 6-12 Hz (Order 4)
           ↓
[Zero-Phase Filtering]     ← filtfilt() - forward-backward
           ↓
[PSD Analysis (Welch)]
  - Window: 4 sec
  - Overlap: 50%
  - Resolution: 0.25 Hz
           ↓
[Calculate Clinical Metrics]
  - Mean, RMS, Max
  - Power in bands
  - Dominant frequency
           ↓
[Automatic Classification]
  - Rest / Essential / Mixed
  - Confidence level
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

Need clarification on any specific part?
