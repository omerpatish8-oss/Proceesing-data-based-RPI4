#!/usr/bin/env python3
"""Quick analysis script for sensor data validation"""

import sys
import io

def analyze_csv_data(data_string):
    """Analyze sensor data from CSV string"""
    lines = data_string.strip().split('\n')

    # Parse data
    timestamps = []
    accel_x, accel_y, accel_z = [], [], []
    gyro_x, gyro_y, gyro_z = [], [], []

    for line in lines:
        parts = line.split(',')
        if len(parts) != 7:
            continue
        try:
            ts = int(parts[0])
            ax, ay, az = float(parts[1]), float(parts[2]), float(parts[3])
            gx, gy, gz = float(parts[4]), float(parts[5]), float(parts[6])

            timestamps.append(ts)
            accel_x.append(ax)
            accel_y.append(ay)
            accel_z.append(az)
            gyro_x.append(gx)
            gyro_y.append(gy)
            gyro_z.append(gz)
        except ValueError:
            continue

    if not timestamps:
        return "No valid data found"

    # Calculate statistics
    intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]

    results = []
    results.append("=" * 70)
    results.append("SENSOR DATA ANALYSIS")
    results.append("=" * 70)
    results.append(f"\n📊 Sample Statistics:")
    results.append(f"   Total samples: {len(timestamps)}")
    results.append(f"   Duration: {(timestamps[-1] - timestamps[0])/1000:.1f} seconds")
    results.append(f"   Expected samples at 100Hz: {(timestamps[-1] - timestamps[0])/10}")

    results.append(f"\n⏱️  Timing Analysis:")
    results.append(f"   Expected interval: 10 ms")
    results.append(f"   Actual mean interval: {sum(intervals)/len(intervals):.2f} ms")
    results.append(f"   Min interval: {min(intervals)} ms")
    results.append(f"   Max interval: {max(intervals)} ms")

    # Count irregular intervals
    irregular = [i for i in intervals if i != 10]
    results.append(f"   Irregular intervals: {len(irregular)}/{len(intervals)} ({100*len(irregular)/len(intervals):.1f}%)")

    # Show first few irregular intervals
    if irregular:
        results.append(f"\n   First irregular gaps:")
        shown = 0
        for i, interval in enumerate(intervals[:50]):
            if interval != 10 and shown < 5:
                results.append(f"      Sample {i}: {timestamps[i]}ms → {timestamps[i+1]}ms (gap: {interval}ms)")
                shown += 1

    results.append(f"\n📏 Accelerometer Ranges (m/s²):")
    results.append(f"   X-axis: {min(accel_x):+7.3f} to {max(accel_x):+7.3f}")
    results.append(f"   Y-axis: {min(accel_y):+7.3f} to {max(accel_y):+7.3f}")
    results.append(f"   Z-axis: {min(accel_z):+7.3f} to {max(accel_z):+7.3f}")

    # Check gravity baseline
    stationary_samples = [i for i, (ax, ay, az) in enumerate(zip(accel_x[:100], accel_y[:100], accel_z[:100]))
                          if 9.0 < az < 10.5 and abs(ax) < 2 and abs(ay) < 2]
    if stationary_samples:
        results.append(f"   ✓ Gravity baseline detected (~9.8 m/s² on Z-axis)")

    # Check for extreme accelerations
    extreme_accel = [(i, ax, ay, az) for i, (ax, ay, az) in enumerate(zip(accel_x, accel_y, accel_z))
                     if abs(ax) > 12 or abs(ay) > 12 or abs(az) > 20 or abs(az) < 2]
    if extreme_accel:
        results.append(f"   ⚠️  Extreme accelerations detected: {len(extreme_accel)} samples")
        results.append(f"       (This suggests rapid motion, impact, or shaking)")

    results.append(f"\n🔄 Gyroscope Ranges (°/s):")
    results.append(f"   X-axis: {min(gyro_x):+8.3f} to {max(gyro_x):+8.3f}")
    results.append(f"   Y-axis: {min(gyro_y):+8.3f} to {max(gyro_y):+8.3f}")
    results.append(f"   Z-axis: {min(gyro_z):+8.3f} to {max(gyro_z):+8.3f}")

    # Check for high rotation rates
    high_rotation = [(i, gx, gy, gz) for i, (gx, gy, gz) in enumerate(zip(gyro_x, gyro_y, gyro_z))
                     if abs(gx) > 100 or abs(gy) > 100 or abs(gz) > 100]
    if high_rotation:
        results.append(f"   ⚠️  High rotation rates: {len(high_rotation)} samples exceed 100°/s")

    results.append(f"\n🔍 Data Quality Assessment:")

    # Check for sensor freeze
    frozen_samples = 0
    for i in range(15, len(accel_x)):
        if all(accel_x[i-j] == accel_x[i] and
               accel_y[i-j] == accel_y[i] and
               accel_z[i-j] == accel_z[i] for j in range(15)):
            frozen_samples += 1

    if frozen_samples > 0:
        results.append(f"   ❌ Frozen sensor detected: {frozen_samples} samples")
    else:
        results.append(f"   ✓ No sensor freezes detected")

    # Overall assessment
    results.append(f"\n{'='*70}")
    results.append("OVERALL ASSESSMENT:")
    results.append("=" * 70)

    issues = []
    if len(irregular) / len(intervals) > 0.05:  # More than 5% irregular
        issues.append("⚠️  TIMING: Irregular sampling intervals detected")
        issues.append("   → Check ESP32 loop timing and serial buffer")

    if extreme_accel:
        issues.append("⚠️  MOTION: Extreme accelerations detected")
        issues.append("   → This may be normal for tremor data, but verify")

    if high_rotation:
        issues.append("⚠️  ROTATION: High rotation rates detected")
        issues.append("   → This may be normal for tremor data, but verify")

    if not issues:
        results.append("✅ Data looks good! No major issues detected.")
    else:
        for issue in issues:
            results.append(issue)

    results.append("\n" + "=" * 70)

    return "\n".join(results)

if __name__ == "__main__":
    # For standalone testing
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            data = f.read()
        print(analyze_csv_data(data))
    else:
        print("Usage: python3 data_analysis.py <csv_file>")
