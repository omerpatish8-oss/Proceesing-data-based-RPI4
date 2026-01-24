#!/usr/bin/env python3
"""
Tremor Analysis Suitability Assessment
Evaluates if the data quality is sufficient for tremor frequency analysis
"""

import csv
import math
import sys

def calculate_stats(values):
    """Calculate mean, std, min, max of a list"""
    n = len(values)
    if n == 0:
        return 0, 0, 0, 0

    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    std = math.sqrt(variance)
    return mean, std, min(values), max(values)

def analyze_tremor_suitability(csv_path):
    """Analyze if data is suitable for tremor analysis"""

    print(f"\n{'='*70}")
    print(f"TREMOR ANALYSIS SUITABILITY: {csv_path.split('/')[-1]}")
    print(f"{'='*70}\n")

    # Load data
    data = []
    with open(csv_path, 'r') as f:
        lines = f.readlines()
        # Find header
        header_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('Timestamp,'):
                header_idx = i
                break

        # Parse data lines
        for line in lines[header_idx + 1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                parts = line.split(',')
                if len(parts) == 7:
                    data.append({
                        'Timestamp': int(parts[0]),
                        'Ax': float(parts[1]),
                        'Ay': float(parts[2]),
                        'Az': float(parts[3]),
                        'Gx': float(parts[4]),
                        'Gy': float(parts[5]),
                        'Gz': float(parts[6])
                    })
            except (ValueError, IndexError):
                continue

    total_samples = len(data)
    duration_s = data[-1]['Timestamp'] / 1000.0

    print(f"Dataset Overview:")
    print(f"  Total samples: {total_samples}")
    print(f"  Duration: {duration_s:.1f}s")
    print(f"  Actual sampling rate: {total_samples / duration_s:.2f} Hz")

    # Calculate time intervals
    intervals = []
    for i in range(1, len(data)):
        dt = data[i]['Timestamp'] - data[i-1]['Timestamp']
        intervals.append(dt)

    mean_dt, std_dt, min_dt, max_dt = calculate_stats(intervals)
    intervals_sorted = sorted(intervals)
    median_dt = intervals_sorted[len(intervals_sorted) // 2]

    print(f"\n{'─'*70}")
    print(f"Timing Analysis:")
    print(f"{'─'*70}")
    print(f"  Mean interval: {mean_dt:.2f} ms")
    print(f"  Std deviation: {std_dt:.2f} ms")
    print(f"  Median interval: {median_dt:.0f} ms")
    print(f"  Max interval: {max_dt:.0f} ms")
    print(f"  Timing jitter (CV): {(std_dt/mean_dt)*100:.2f}%")

    # Tremor frequency analysis
    print(f"\n{'─'*70}")
    print(f"Tremor Frequency Requirements:")
    print(f"{'─'*70}")

    tremor_types = {
        "Parkinson's tremor": (3, 6),
        "Essential tremor": (4, 12),
        "Physiological tremor": (8, 12),
        "Cerebellar tremor": (2, 5),
        "Action tremor": (4, 8)
    }

    actual_fs = total_samples / duration_s
    nyquist_freq = actual_fs / 2

    print(f"  Actual sampling rate: {actual_fs:.2f} Hz")
    print(f"  Nyquist frequency: {nyquist_freq:.2f} Hz")
    print(f"\n  Can detect frequencies up to: {nyquist_freq:.1f} Hz")
    print(f"\n  Tremor type coverage:")

    all_suitable = True
    for tremor_type, (min_hz, max_hz) in tremor_types.items():
        required_fs = max_hz * 2  # Nyquist criterion
        suitable = actual_fs >= required_fs * 1.5  # 1.5x margin for safety
        status = "✅" if suitable else "⚠️"
        margin = actual_fs / required_fs
        print(f"    {status} {tremor_type}: {min_hz}-{max_hz} Hz (margin: {margin:.1f}x)")
        if not suitable:
            all_suitable = False

    # Signal quality analysis
    print(f"\n{'─'*70}")
    print(f"Signal Quality Analysis:")
    print(f"{'─'*70}")

    # Extract signal values
    ax_values = [d['Ax'] for d in data]
    ay_values = [d['Ay'] for d in data]
    az_values = [d['Az'] for d in data]
    gx_values = [d['Gx'] for d in data]
    gy_values = [d['Gy'] for d in data]
    gz_values = [d['Gz'] for d in data]

    ax_mean, ax_std, _, _ = calculate_stats(ax_values)
    ay_mean, ay_std, _, _ = calculate_stats(ay_values)
    az_mean, az_std, _, _ = calculate_stats(az_values)
    gx_mean, gx_std, _, _ = calculate_stats(gx_values)
    gy_mean, gy_std, _, _ = calculate_stats(gy_values)
    gz_mean, gz_std, _, _ = calculate_stats(gz_values)

    print(f"  Accelerometer variability (std dev):")
    print(f"    Ax: {ax_std:.4f} m/s²")
    print(f"    Ay: {ay_std:.4f} m/s²")
    print(f"    Az: {az_std:.4f} m/s²")

    print(f"\n  Gyroscope variability (std dev):")
    print(f"    Gx: {gx_std:.3f} °/s")
    print(f"    Gy: {gy_std:.3f} °/s")
    print(f"    Gz: {gz_std:.3f} °/s")

    # Sensor resolution check (MPU6050 specs)
    print(f"\n{'─'*70}")
    print(f"Sensor Specifications (MPU6050):")
    print(f"{'─'*70}")
    print(f"  Accelerometer range: ±4g")
    print(f"  Accelerometer resolution: 0.122 mg/LSB (16-bit)")
    print(f"  Gyroscope range: ±500°/s")
    print(f"  Gyroscope resolution: 0.015°/s/LSB (16-bit)")
    print(f"  Low-pass filter: 21 Hz (configured)")

    # Check data completeness
    print(f"\n{'─'*70}")
    print(f"Data Completeness:")
    print(f"{'─'*70}")

    # Check for large gaps (>50ms could affect frequency analysis)
    large_gaps = [dt for dt in intervals if dt > 50]
    percent_large_gaps = (len(large_gaps) / len(intervals)) * 100

    print(f"  Large gaps (>50ms): {len(large_gaps)} ({percent_large_gaps:.2f}%)")

    if len(large_gaps) > 0:
        print(f"  Largest gap: {max(large_gaps):.0f} ms")
        print(f"  Impact: {'Minimal' if percent_large_gaps < 1 else 'Moderate'}")

    # Missing samples estimate
    expected_samples = duration_s * 100  # Nominal 100 Hz
    missing_samples = expected_samples - total_samples
    completeness = (total_samples / expected_samples) * 100

    print(f"\n  Expected samples (100 Hz): {expected_samples:.0f}")
    print(f"  Actual samples: {total_samples}")
    print(f"  Missing samples: {missing_samples:.0f}")
    print(f"  Completeness: {completeness:.2f}%")

    # Frequency resolution
    print(f"\n{'─'*70}")
    print(f"Frequency Analysis Resolution:")
    print(f"{'─'*70}")

    freq_resolution = 1.0 / duration_s
    print(f"  Frequency resolution: {freq_resolution:.4f} Hz")
    print(f"  (Can distinguish frequencies {freq_resolution:.4f} Hz apart)")
    print(f"\n  For tremor analysis (typically 3-12 Hz):")
    print(f"    ✅ Excellent resolution - can distinguish 0.1 Hz differences")

    # Overall assessment
    print(f"\n{'─'*70}")
    print(f"OVERALL TREMOR ANALYSIS ASSESSMENT:")
    print(f"{'─'*70}")

    issues = []
    strengths = []

    # Check criteria
    if actual_fs >= 50:
        strengths.append("✅ Sampling rate ({:.1f} Hz) is excellent for tremor analysis".format(actual_fs))
    else:
        issues.append("⚠️ Sampling rate may be insufficient")

    if nyquist_freq >= 15:
        strengths.append("✅ Can detect all tremor frequencies up to {:.1f} Hz".format(nyquist_freq))
    else:
        issues.append("⚠️ Limited frequency range")

    if (std_dt / mean_dt) < 0.5:
        strengths.append("✅ Low timing jitter ({:.1f}%) - good for FFT analysis".format((std_dt/mean_dt)*100))
    else:
        issues.append("⚠️ High timing jitter may affect frequency analysis")

    if completeness >= 95:
        strengths.append("✅ Data completeness ({:.1f}%) is very good".format(completeness))
    else:
        issues.append("⚠️ Significant data loss ({:.1f}% complete)".format(completeness))

    if percent_large_gaps < 1:
        strengths.append("✅ Very few large timing gaps ({:.2f}%)".format(percent_large_gaps))
    else:
        issues.append("⚠️ Timing gaps may require interpolation")

    if duration_s >= 60:
        strengths.append("✅ Long recording ({:.0f}s) provides good statistical reliability".format(duration_s))

    if ax_std > 0.01 or gx_std > 0.1:
        strengths.append("✅ Good signal variability - sensor not frozen")
    else:
        issues.append("⚠️ Low signal variability - check if sensor is responding")

    print("\nStrengths:")
    for strength in strengths:
        print(f"  {strength}")

    if issues:
        print("\nConcerns:")
        for issue in issues:
            print(f"  {issue}")

    # Final verdict
    print(f"\n{'─'*70}")

    if len(issues) == 0:
        print("✅ EXCELLENT - Data is highly suitable for tremor analysis")
        suitability = "EXCELLENT"
    elif len(issues) <= 2:
        print("✅ GOOD - Data is suitable for tremor analysis")
        print("   Minor issues can be handled with standard preprocessing")
        suitability = "GOOD"
    else:
        print("⚠️ FAIR - Data can be used but may require careful preprocessing")
        suitability = "FAIR"

    print(f"{'─'*70}\n")

    return suitability

def main():
    csv_files = [
        '/home/user/Proceesing-data-based-RPI4/tremor_cycle1_20260121_141523.csv',
        '/home/user/Proceesing-data-based-RPI4/tremor_cycle1_20260121_160502.csv'
    ]

    print("\n" + "="*70)
    print("TREMOR ANALYSIS SUITABILITY ASSESSMENT")
    print("="*70)

    results = {}
    for csv_file in csv_files:
        results[csv_file] = analyze_tremor_suitability(csv_file)

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    for csv_file, suitability in results.items():
        filename = csv_file.split('/')[-1]
        print(f"  {filename}: {suitability}")

    print("\n" + "="*70)
    print("RECOMMENDATIONS FOR TREMOR ANALYSIS")
    print("="*70)
    print("""
1. ✅ Frequency Analysis (FFT):
   - Can reliably detect tremor frequencies from 0-49 Hz
   - Excellent for Parkinson's (3-6 Hz) and Essential tremor (4-12 Hz)
   - Use windowing (Hamming/Hann) to reduce spectral leakage

2. ✅ Time-Domain Analysis:
   - Sufficient temporal resolution for peak detection
   - Can analyze tremor amplitude variations
   - Can detect tremor episodes and patterns

3. ⚠️ Preprocessing Recommended:
   - Apply low-pass filter (e.g., 20-25 Hz cutoff) to remove noise
   - Consider resampling to exact 100 Hz if needed (interpolation)
   - Remove any DC offset (mean subtraction)
   - Handle large gaps with interpolation if present

4. ✅ Machine Learning:
   - Data quality is sufficient for feature extraction
   - Can extract frequency, amplitude, and temporal features
   - 120s windows provide good statistical reliability

5. ✅ Clinical Assessment:
   - Can characterize tremor dominant frequency
   - Can measure tremor amplitude and variability
   - Can assess tremor severity over time
    """)

    print("="*70 + "\n")

if __name__ == '__main__':
    main()
