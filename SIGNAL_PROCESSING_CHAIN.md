# שרשרת עיבוד אותות - Tremor Analysis System
# Signal Processing Chain - From ESP32 to Analysis

**תאריך:** 2026-01-24
**מערכת:** ESP32 + MPU6050 → Raspberry Pi → Offline Analyzer

---

## 🔄 תרשים זרימה כולל

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

## 📊 שלב 1: ESP32 Firmware - עיבוד חומרה

### **הגדרות MPU6050:**

```cpp
// File: esp32_usb_serial_safe.ino

// טווח מדידה
mpu.setAccelerometerRange(MPU6050_RANGE_4_G);      // ±4g
mpu.setGyroRange(MPU6050_RANGE_500_DEG);           // ±500°/s

// פילטר חומרה מובנה (DLPF - Digital Low Pass Filter)
mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);        // 21 Hz LPF
```

### **מה קורה בחיישן MPU6050:**

#### **1. חיישן פיזי:**
- **Accelerometer:** מודד תאוצה לינארית (כולל כוח הכבידה)
- **Gyroscope:** מודד מהירות זוויתית (סיבוב)
- **דגימה פנימית:** 1 kHz (1000 Hz)

#### **2. פילטר חומרה מובנה - DLPF (Digital Low Pass Filter):**

**MPU6050_BAND_21_HZ = Low Pass Filter בתוך החיישן!**

| פרמטר | ערך |
|-------|-----|
| **סוג פילטר** | Low-Pass Filter (מעביר תדרים נמוכים) |
| **תדר חיתוך (-3dB)** | **21 Hz** |
| **שיטה** | FIR/IIR דיגיטלי בתוך החיישן |
| **תדר דגימה יעיל** | 100 Hz (מוגדר ב-firmware) |
| **מטרה** | סינון רעשים גבוהים, אנטי-אליאסינג |

**📌 חשוב להבין:**
- **הפילטר הזה פועל בחומרה לפני שהנתונים מגיעים לקוד!**
- **אנחנו לא יכולים לבטל אותו - הנתונים שמגיעים כבר מסוננים ב-21 Hz**
- **כל תדרים מעל ~21 Hz כבר מוחלשים משמעותית**

#### **3. קליברציה (Calibration):**

```cpp
// הסרת offset של החיישן
float ax = a.acceleration.x - aX_off;  // aX_off = 0.58
float ay = a.acceleration.y - aY_off;  // aY_off = -0.20
float az = a.acceleration.z - aZ_off;  // aZ_off = -1.23

float gx = (g.gyro.x * 57.296) - gX_off;  // המרה מ-rad/s ל-deg/s
float gy = (g.gyro.y * 57.296) - gY_off;
float gz = (g.gyro.z * 57.296) - gZ_off;
```

**מה הקליברציה עושה:**
- מסירה של DC offset (הסטה קבועה) של החיישן
- **אבל לא מסירה של כוח הכבידה!**

#### **4. פורמט נתונים:**

```
Timestamp,Ax,Ay,Az,Gx,Gy,Gz
0,0.580,-0.200,-1.230,22.360,5.810,0.170
10,0.582,-0.198,-1.228,22.358,5.808,0.168
```

**יחידות:**
- **Timestamp:** אלפיות שנייה (ms)
- **Ax, Ay, Az:** תאוצה (m/s²) - **כולל כוח כבידה!**
- **Gx, Gy, Gz:** מהירות זוויתית (°/s)

### **📊 סיכום שלב ESP32:**

```
תאוצה אמיתית + כוח כבידה (9.81 m/s²)
           ↓
      [ADC במפ6050]
           ↓
  [DLPF Hardware: 21 Hz LPF]  ← פילטר חומרה!
           ↓
    [דגימה 100 Hz]
           ↓
   [הסרת offset חיישן]
           ↓
      [USB Serial]
           ↓
    CSV עם נתונים:
    - מסוננים ב-21 Hz
    - עדיין עם כוח כבידה
    - ללא offset חיישן
```

---

## 📈 שלב 2: Offline Analyzer - עיבוד תוכנה

### **קלט: CSV File**

```python
# offline_analyzer.py

# טעינת נתונים מ-CSV
ax = data['Ax']  # m/s² (כולל כבידה, מסונן ב-21 Hz)
ay = data['Ay']
az = data['Az']
t = data['Timestamp'] / 1000.0  # המרה לשניות
```

### **שלב 2.1: הסרת DC Offset (Gravity Removal)**

```python
# הסרת הממוצע = הסרת כוח הכבידה
ax_clean = ax - np.mean(ax)  # הסרת רכיב DC
ay_clean = ay - np.mean(ay)
az_clean = az - np.mean(az)
```

**למה זה עובד:**
- כוח הכבידה הוא **קבוע** לאורך זמן → DC offset
- הרעד (tremor) הוא **משתנה** לאורך זמן → AC signal
- חיסור הממוצע מסיר רק את הרכיב הקבוע (כבידה), משאיר רק תנודות (רעד)

**דוגמה:**
```
Ay (raw):     [-1.2, -1.1, -1.3, -1.0, -1.2]  ← יש DC offset של -1.16
mean(Ay):     -1.16
Ay_clean:     [-0.04, +0.06, -0.14, +0.16, -0.04]  ← רק התנודות!
```

### **שלב 2.2: חישוב Resultant Vector (וקטור תוצאתי)**

```python
# גודל הוקטור (מגניטודה)
accel_mag = np.sqrt(ax_clean**2 + ay_clean**2 + az_clean**2)
```

**מה זה עושה:**
- ממיר 3 צירים (X, Y, Z) לערך סקלרי אחד
- מודד את **גודל התאוצה הכולל** ללא קשר לכיוון
- שימושי למדידת **חומרת רעד כוללת**

### **שלב 2.3: זיהוי ציר דומיננטי**

```python
# חישוב אנרגיה בכל ציר
energy_x = np.sum(ax_clean**2)  # סכום ריבועים = אנרגיית אות
energy_y = np.sum(ay_clean**2)
energy_z = np.sum(az_clean**2)

# בחירת הציר עם האנרגיה הגבוהה ביותר
max_axis = max({'X': energy_x, 'Y': energy_y, 'Z': energy_z})
```

**למה חשוב:**
- מזהה באיזה **כיוון הרעד החזק ביותר**
- בדרך כלל Y-axis (קדימה-אחורה) דומיננטי ברעד ידיים

### **שלב 2.4: בניית מסננים - Butterworth Filters**

#### **פרמטרים:**
```python
FS = 100.0              # תדר דגימה (Hz)
FILTER_ORDER = 4        # סדר הפילטר (Butterworth)
```

#### **3 מסננים מסוג Bandpass (מעביר פס):**

**1️⃣ מסנן משולב (Combined Tremor Filter):**
```python
b_tremor, a_tremor = butter(4, [3/nyquist, 12/nyquist], btype='band')
```
- **סוג:** Butterworth Order 4
- **רוחב פס:** **3-12 Hz**
- **תדר חיתוך תחתון (-3dB):** 3 Hz
- **תדר חיתוך עליון (-3dB):** 12 Hz
- **מטרה:** סינון כל טווח הרעד (Rest + Essential)

**2️⃣ מסנן רעד מנוחה (Rest Tremor Filter):**
```python
b_rest, a_rest = butter(4, [3/nyquist, 7/nyquist], btype='band')
```
- **סוג:** Butterworth Order 4
- **רוחב פס:** **3-7 Hz**
- **מטרה:** בידוד רעד פרקינסון (Rest tremor)

**3️⃣ מסנן רעד אסנציאלי (Essential Tremor Filter):**
```python
b_ess, a_ess = butter(4, [6/nyquist, 12/nyquist], btype='band')
```
- **סוג:** Butterworth Order 4
- **רוחב פס:** **6-12 Hz**
- **מטרה:** בידוד רעד פוסטורלי (Essential tremor)

#### **מאפייני Butterworth Order 4:**

| מאפיין | ערך |
|--------|-----|
| **Roll-off (שיפוע)** | 24 dB/octave (80 dB/decade) |
| **Ripple בפסבנד** | 0 dB (שטוח לחלוטין!) |
| **שלב (Phase)** | לא ליניארי, אבל... |
| **Zero-phase?** | כן! בזכות `filtfilt()` |

### **שלב 2.5: החלת פילטרים - Zero-Phase Filtering**

```python
# סינון הציר הדומיננטי
axis_filtered = filtfilt(b_tremor, a_tremor, dominant_axis)
axis_rest = filtfilt(b_rest, a_rest, dominant_axis)
axis_ess = filtfilt(b_ess, a_ess, dominant_axis)

# סינון הוקטור התוצאתי
result_filtered = filtfilt(b_tremor, a_tremor, accel_mag)
result_rest = filtfilt(b_rest, a_rest, accel_mag)
result_ess = filtfilt(b_ess, a_ess, accel_mag)
```

**למה `filtfilt()` ולא `filter()`?**

`filtfilt()` = **Zero-Phase Filtering**
- **מסנן קדימה ואחורה** (Forward-Backward)
- **אין עיוות פאזה** (No phase distortion)
- **שומר על מיקום זמן של תכונות** (אירועים נשארים באותו מקום)
- **חשוב לניתוח רפואי!** (לא משנה את התזמון של הרעד)

**איך זה עובד:**
```
Signal → [Filter Forward] → [Reverse] → [Filter Backward] → Result
```
**תוצאה:** שיפוע של 48 dB/octave (כפול!), אפס שינוי פאזה

### **שלב 2.6: ניתוח PSD - Power Spectral Density**

```python
nperseg = min(len(accel_mag), int(FS * 4))  # חלון של 4 שניות
noverlap = int(nperseg * 0.5)                # חפיפה של 50%

# חישוב PSD בשיטת Welch
f, psd = welch(signal, FS, nperseg=nperseg, noverlap=noverlap)
```

**פרמטרי Welch:**

| פרמטר | ערך | הסבר |
|-------|-----|------|
| **Window size** | 4 seconds (400 samples) | אורך חלון לניתוח |
| **Overlap** | 50% (200 samples) | חפיפה בין חלונות |
| **Frequency resolution** | 0.25 Hz | דיוק זיהוי תדר |
| **Window type** | Hann (ברירת מחדל) | מפחית דליפה ספקטרלית |

**למה שיטת Welch:**
- מחלק את האות לחלונות קטנים
- מחשב FFT לכל חלון
- ממצע את התוצאות
- **מפחית רעש**, משפר אמינות

### **שלב 2.7: חישוב מדדים קליניים**

```python
# תכונות מ-Paper 1 (MDPI)
metrics['accel_mean'] = np.mean(accel_filt)              # ממוצע
metrics['accel_rms'] = np.sqrt(np.mean(accel_filt**2))  # RMS
metrics['accel_max'] = np.max(np.abs(accel_filt))       # מקסימום

# כוח בפסים
rest_mask = (freq >= 3) & (freq <= 7)
ess_mask = (freq >= 6) & (freq <= 12)

metrics['power_rest'] = np.sum(psd[rest_mask])      # כוח ב-3-7 Hz
metrics['power_ess'] = np.sum(psd[ess_mask])        # כוח ב-6-12 Hz

# תדר דומיננטי
tremor_mask = (freq >= 3) & (freq <= 12)
peak_idx = np.argmax(psd[tremor_mask])
metrics['dominant_freq'] = freq[tremor_mask][peak_idx]
```

#### **📊 הסבר מפורט של המדדים הקליניים:**

**1️⃣ MEAN (ממוצע) - `accel_mean`**
```python
mean = np.mean(signal_filtered)  # ממוצע חשבוני
```
- **מה זה:** הממוצע של כל הדגימות המסוננות
- **יחידות:** **m/s²** (מטר לשנייה בריבוע)
- **טווח ערכים תקין:** ±0.01 m/s² (קרוב לאפס)
- **משמעות קלינית:**
  - **~0:** תנודות סימטריות (טוב!)
  - **>0.1:** יש הטיה - אולי לא הוסר DC לגמרי
- **איפה בגרפים:**
  - Row 2, Plot 2: קו דמיוני אופקי דרך מרכז האות
  - Row 3, Plot 2: רמה ממוצעת של הוקטור התוצאתי

**2️⃣ RMS (Root Mean Square) - `accel_rms`**
```python
rms = √[mean(signal²)]  # שורש ממוצע ריבועים
```
- **מה זה:** **מדד החומרה העיקרי!** גודל ממוצע של הרעד
- **יחידות:** **m/s²** (מטר לשנייה בריבוע)
- **נוסחה צעד-צעד:**
  1. `squared = signal ** 2` - ריבוע כל דגימה
  2. `mean_squared = mean(squared)` - ממוצע
  3. `rms = √(mean_squared)` - שורש
- **למה RMS ולא Mean?**
  - RMS **תמיד חיובי** (גם אם האות נע למעלה ולמטה)
  - RMS שקול ל**אנרגיה** של האות
  - **מדד בינלאומי** לחומרת רעד
- **סקלת חומרה:**
  - **< 0.10 m/s²** → Mild (קל)
  - **0.10-0.30 m/s²** → Moderate (בינוני)
  - **> 0.30 m/s²** → **Severe (חמור)**
- **איפה בגרפים:**
  - **Row 2, Plot 2** (Y-Axis Filtered): הכותרת מציגה RMS!
  - **Row 3, Plot 2** (Resultant Filtered): גם כאן בכותרת!
  - **דוגמה מהתמונה שלך:** RMS: 1.6238 m/s² → **SEVERE!**

**3️⃣ MAX (מקסימום) - `accel_max`**
```python
max_amplitude = np.max(np.abs(signal))  # ערך מוחלט מקסימלי
```
- **מה זה:** השיא החזק ביותר של הרעד
- **יחידות:** **m/s²**
- **משמעות:**
  - פיקים חדים = רעד לא יציב
  - פיקים גבוהים = רגעי רעד חזקים מאוד
- **איפה בגרפים:**
  - Row 2/3, Plot 2: הנקודה הגבוהה/נמוכה ביותר
  - Row 2/3, Plot 2: קצה העטיפה (envelope)

**4️⃣ POWER (כוח ספקטרלי) - `power_rest`, `power_ess`**
```python
# אינטגרציה של PSD על טווח תדרים
power_rest = Σ[PSD בין 3-7 Hz]  # סכום
power_ess = Σ[PSD בין 6-12 Hz]
```
- **מה זה:** סכום (אינטגרל) של ה-PSD בטווח תדרים
- **יחידות:** **m²/s⁴** (מטר בריבוע לשנייה בחזקת 4)
  - **למה היחידות האלה?**
    - PSD יחידות: (m/s²)²/Hz = m²/s⁴/Hz
    - Power = ∫PSD dF = m²/s⁴/Hz × Hz = **m²/s⁴**
- **הסבר פיזי:**
  ```
  PSD[f] = "כוח בתדר f בודד"
  Power = ∫PSD df = "כוח כולל בטווח תדרים"
  ```
- **ערכים טיפוסיים:**
  - **Power < 2:** רעד חלש בפס זה
  - **Power 2-5:** רעד בינוני
  - **Power > 5:** רעד חזק בפס זה
- **שימוש לסיווג:**
  ```python
  ratio = power_rest / power_ess
  if ratio > 2.0:  → Rest Tremor
  if ratio < 0.5:  → Essential Tremor
  else:            → Mixed
  ```
- **איפה בגרפים:**
  - **Row 4, Plot 1** (PSD Y-Axis): האזורים הצבועים!
    - אזור ורוד (3-7 Hz) = Rest
    - אזור כחול (6-12 Hz) = Essential
  - **Row 4, Plot 2** (PSD Resultant): אותם אזורים
  - **Row 4, Plot 3** (Bar Chart): **העמודות עצמן!**
    - גובה עמודה אדומה = `power_rest`
    - גובה עמודה כחולה = `power_ess`

**5️⃣ DOMINANT FREQUENCY (תדר דומיננטי)**
```python
peak_idx = np.argmax(psd[3:12 Hz])  # מציאת הפסגה
dominant_freq = freq[peak_idx]       # התדר שלה
```
- **מה זה:** התדר עם הכוח המקסימלי
- **יחידות:** **Hz** (הרץ - מחזורים לשנייה)
- **משמעות קלינית:**
  - **3-5 Hz:** Rest Tremor טיפוסי (פרקינסון)
  - **5-7 Hz:** גבול (Borderline)
  - **8-12 Hz:** Essential Tremor
- **איפה בגרפים:**
  - **Row 4, Plot 1 & 2**: **עיגול אדום ● על הפסגה!**
  - הכיתוב: `Peak: 5.75 Hz` (דוגמה)

---

#### **🔗 טבלת קורלציה: מדדים ↔ גרפים**

| מדד | ערך בדוגמה | יחידות | איפה רואים | איך לזהות |
|-----|-----------|--------|-------------|-----------|
| **Mean** | 0.0014 | m/s² | Row 2/3, Plot 2 | קו דמיוני אופקי (קרוב לאפס) |
| **RMS** | 1.6238 | m/s² | Row 2/3, Plot 2 | **בכותרת הגרף!** "RMS: X.XXXX" |
| **Max** | 8.8714 | m/s² | Row 2/3, Plot 2 | הנקודה הגבוהה ביותר |
| **Power Rest** | 6.5008 | m²/s⁴ | Row 4, Plot 3 | **גובה עמודה אדומה** |
| **Power Ess** | 8.7993 | m²/s⁴ | Row 4, Plot 3 | **גובה עמודה כחולה** |
| **Dom. Freq** | 5.75 | Hz | Row 4, Plot 1&2 | **עיגול אדום ●** |

**דוגמה מהתמונה שלך - פענוח מלא:**
```
┌─ Clinical Metrics (טבלה מצד ימין) ─┐
│                                      │
│ Mean: 0.0014 m/s²                   │ ← קרוב לאפס ✓
│ RMS: 1.6238 m/s²                    │ ← SEVERE! (>0.30)
│ Max: 8.8714 m/s²                    │ ← פיק גבוה מאוד!
│                                      │
│ Rest (3-7 Hz):                      │
│   Power: 6.5008 m²/s⁴               │ ← עמודה אדומה בגרף
│                                      │
│ Essential (6-12 Hz):                │
│   Power: 8.7993 m²/s⁴               │ ← עמודה כחולה (גבוהה יותר!)
│                                      │
│ Ratio: 0.74                         │ ← 6.5/8.8 = 0.74
│ Type: Mixed Tremor                  │ ← כי 0.5 < 0.74 < 2.0
│ Confidence: Moderate                │
│                                      │
│ Dominant Freq: 5.75 Hz              │ ← העיגול האדום ב-PSD
└──────────────────────────────────────┘
```

**התאמה לגרפים:**
1. **Row 4, Plot 3** (Bar Chart):
   - עמודה אדומה גובה 6.5 ← Power Rest
   - עמודה כחולה גובה 8.8 ← Power Essential
   - כחול > אדום → Essential דומיננטי קצת

2. **Row 4, Plot 1 & 2** (PSD):
   - עיגול אדום ● ב-5.75 Hz ← Dominant Frequency
   - אזור כחול (6-12) גבוה יותר ← Essential חזק יותר

3. **Row 2, Plot 2** (Y-Axis Filtered):
   - כותרת: "RMS: 1.6238 m/s²" ← חומרה חמורה
   - רוחב האות גדול ← RMS גבוה

4. **Row 3, Plot 2** (Resultant Filtered):
   - כותרת: "RMS: 1.6238 m/s²" ← אותו ערך
   - עטיפה רחבה ← רעד חזק

### **שלב 2.8: סיווג רעד**

```python
power_ratio = power_rest / (power_ess + 1e-10)

if power_ratio > 2.0:
    tremor_type = "Rest Tremor (Parkinsonian)"      # פרקינסון
    confidence = "High"
elif power_ratio < 0.5:
    tremor_type = "Essential Tremor (Postural)"     # אסנציאלי
    confidence = "High"
else:
    tremor_type = "Mixed Tremor"                    # מעורב
    confidence = "Moderate"
```

---

## 📊 סיכום שרשרת העיבוד המלאה

### **שלב 1: ESP32 (חומרה)**
```
תאוצה פיזית + כבידה (9.81 m/s²)
           ↓
   [ADC 16-bit במפ6050]
           ↓
 [DLPF Hardware: 21 Hz]  ← מסנן Low-Pass חומרתי
           ↓
   [דגימה 100 Hz]
           ↓
 [הסרת offset חיישן]
           ↓
  [קליברציה: ±4g, ±500°/s]
           ↓
    CSV: Ax, Ay, Az (m/s²)
    - מסונן ב-21 Hz
    - כולל כבידה
```

### **שלב 2: Offline Analyzer (תוכנה)**
```
CSV עם נתונים גולמיים
           ↓
[הסרת DC = הסרת כבידה]  ← ax_clean = ax - mean(ax)
           ↓
[חישוב Resultant Vector]  ← mag = √(x² + y² + z²)
           ↓
[זיהוי ציר דומיננטי]      ← energy = Σ(signal²)
           ↓
[Butterworth Bandpass Filters]
  - Combined: 3-12 Hz (Order 4)
  - Rest: 3-7 Hz (Order 4)
  - Essential: 6-12 Hz (Order 4)
           ↓
[Zero-Phase Filtering]     ← filtfilt() - קדימה ואחורה
           ↓
[PSD Analysis (Welch)]
  - Window: 4 sec
  - Overlap: 50%
  - Resolution: 0.25 Hz
           ↓
[חישוב מדדים קליניים]
  - Mean, RMS, Max
  - Power בפסים
  - תדר דומיננטי
           ↓
[סיווג אוטומטי]
  - Rest / Essential / Mixed
  - רמת ביטחון
```

---

## 🔍 איך הפילטר של ESP32 (21 Hz) משפיע על הניתוח?

### **1. אנטי-אליאסינג:**
✅ **טוב!** הפילטר של 21 Hz מונע aliasing:
- תדר Nyquist = 50 Hz (חצי מ-100 Hz)
- פילטר 21 Hz מבטיח שאין תדרים גבוהים שיגרמו לאליאסינג

### **2. הגבלת רוחב פס:**
⚠️ **חשוב להכיר!**
- כל התדרים מעל 21 Hz כבר מוחלשים בחומרה
- אנחנו מנתחים רק 3-12 Hz, אז **זה לא מפריע**
- אבל אם היינו רוצים לנתח תדרים גבוהים יותר (15-20 Hz), היינו מוגבלים

### **3. רעש תרמי ורעש מדידה:**
✅ **טוב!** הפילטר מסיר רעשים גבוהים:
- רעש אלקטרוני (> 21 Hz)
- רעשי מנוע (אם בתדרים גבוהים)
- רעש סביבתי

### **4. עיוות פאזה מינורי:**
⚠️ הפילטר החומרתי עשוי להוסיף עיוות פאזה קטן ב-3-12 Hz
- **אבל:** `filtfilt()` שלנו מתקן את זה!
- **תוצאה:** אפס עיוות כולל

---

## 📐 טבלת סיכום: כל המסננים במערכת

| שלב | מסנן | סוג | רוחב פס | תדר חיתוך | Roll-off | Zero-Phase? |
|-----|------|-----|---------|-----------|----------|-------------|
| **ESP32** | DLPF (MPU6050) | Low-Pass | DC - 21 Hz | 21 Hz | ~20 dB/dec | ❌ לא |
| **Analyzer 1** | Combined Tremor | Bandpass | 3-12 Hz | 3 Hz, 12 Hz | 48 dB/oct | ✅ כן |
| **Analyzer 2** | Rest Tremor | Bandpass | 3-7 Hz | 3 Hz, 7 Hz | 48 dB/oct | ✅ כן |
| **Analyzer 3** | Essential Tremor | Bandpass | 6-12 Hz | 6 Hz, 12 Hz | 48 dB/oct | ✅ כן |

---

## 💡 נקודות חשובות להבנה

### **1. למה אנחנו לא מסוננים ב-ESP32 יותר?**
- הפילטר של 21 Hz הוא **אנטי-אליאסינג** בלבד
- סינון ספציפי לרעד (3-12 Hz) נעשה **רק בניתוח**
- כך אפשר לשנות פרמטרים בלי לשנות firmware

### **2. למה Butterworth Order 4?**
- **Flat passband** (אין גלים בפס המעבר)
- **Steep roll-off** (שיפוע תלול - טוב להפרדה)
- **סטנדרט במחקר** (מאמרי MDPI)
- **אופטימלי** בין חדות להשהיה

### **3. למה Zero-Phase (`filtfilt()`)?**
- **שומר על זמן** של אירועים
- **חשוב לניתוח קליני** (מתי הרעד מתרחש)
- **מכפיל את Roll-off** (48 dB/oct במקום 24)

### **4. למה Welch עם חלונות של 4 שניות?**
- **רזולוציה תדר:** 0.25 Hz (מספיק טוב ל-3-12 Hz)
- **הפחתת רעש:** ממוצע על חלונות משפר SNR
- **סטנדרט:** נפוץ בניתוח רעידות

---

## ✅ סיכום פסבנדים (Passband Summary)

```
תדרים (Hz):  0    3    6    7    12   21   50 (Nyquist)
             |____|____|____|____|____|____|
ESP32 DLPF:  |████████████████████████|      ← 21 Hz LPF
Rest Tremor: |    |████████|                 ← 3-7 Hz BPF
Essential:   |         |████████|            ← 6-12 Hz BPF
Combined:    |    |████████████████|         ← 3-12 Hz BPF

████ = פס מעבר (Passband)
|    = תדר חיתוך
```

---

**סיכום אחרון:**
1. **ESP32:** מסנן 21 Hz בחומרה (אנטי-אליאסינג)
2. **Analyzer:** 3 מסננים Butterworth Order 4 (3-12 Hz, 3-7 Hz, 6-12 Hz)
3. **כל הסינון הספציפי לרעד נעשה בתוכנה!**
4. **Zero-Phase filtering שומר על תזמון מדויק**

האם צריך הבהרות נוספות על חלק מסוים?
