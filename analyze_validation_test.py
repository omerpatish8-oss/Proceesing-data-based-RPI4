#!/usr/bin/env python3
"""
Validation Test Analysis Script

Purpose: Analyze validation test results by comparing commanded inputs
         (from validation_test_log.csv) with measured outputs (from sensor data)

Usage:
    python3 analyze_validation_test.py <log_file.csv> <sensor_data.csv>

Expected sensor data format:
    - CSV with columns: Timestamp,Ax,Ay,Az,Gx,Gy,Gz
    - Timestamp in milliseconds
    - Accelerometer data in m/s²
    - Gyroscope data in deg/s

Validation Criteria:
    ✓ Frequency error < 0.2 Hz (FFT peak detection)
    ✓ Amplitude correlation R² > 0.95 with PWM² (centrifugal force validation)
    ✓ Step response rise time < 1 second
"""

import sys
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from datetime import datetime
from scipy import signal, stats
from pathlib import Path


def load_validation_log(log_file):
    """Load the validation test log CSV"""
    print(f"📂 Loading validation log: {log_file}")

    log_data = []
    with open(log_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            log_data.append(row)

    print(f"   ✓ Loaded {len(log_data)} log entries")
    return log_data


def load_sensor_data(sensor_file):
    """
    Load sensor data CSV

    Expected format:
    Timestamp,Ax,Ay,Az,Gx,Gy,Gz
    """
    print(f"📂 Loading sensor data: {sensor_file}")

    timestamps = []
    accel_x, accel_y, accel_z = [], [], []
    gyro_x, gyro_y, gyro_z = [], [], []

    with open(sensor_file, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Skip comment lines
            if row.get('Timestamp', '').startswith('#'):
                continue

            try:
                timestamps.append(int(row['Timestamp']))
                accel_x.append(float(row['Ax']))
                accel_y.append(float(row['Ay']))
                accel_z.append(float(row['Az']))
                gyro_x.append(float(row['Gx']))
                gyro_y.append(float(row['Gy']))
                gyro_z.append(float(row['Gz']))
            except (ValueError, KeyError) as e:
                print(f"   ⚠️  Skipping invalid row: {e}")
                continue

    sensor_data = {
        'timestamps': np.array(timestamps),
        'accel_x': np.array(accel_x),
        'accel_y': np.array(accel_y),
        'accel_z': np.array(accel_z),
        'gyro_x': np.array(gyro_x),
        'gyro_y': np.array(gyro_y),
        'gyro_z': np.array(gyro_z)
    }

    print(f"   ✓ Loaded {len(timestamps)} sensor readings")
    print(f"   ✓ Duration: {timestamps[-1] - timestamps[0]:.1f} ms ({(timestamps[-1] - timestamps[0])/1000:.1f} s)")

    return sensor_data


def extract_frequency_fft(signal_data, sampling_rate):
    """
    Extract dominant frequency from signal using FFT

    Args:
        signal_data: 1D numpy array of signal values
        sampling_rate: Sampling rate in Hz

    Returns:
        (dominant_frequency, amplitude, fft_freqs, fft_magnitude)
    """
    # Remove DC component
    signal_data = signal_data - np.mean(signal_data)

    # Apply window to reduce spectral leakage
    window = np.hanning(len(signal_data))
    windowed_signal = signal_data * window

    # Compute FFT
    fft_values = np.fft.rfft(windowed_signal)
    fft_magnitude = np.abs(fft_values)
    fft_freqs = np.fft.rfftfreq(len(signal_data), 1.0 / sampling_rate)

    # Find dominant frequency (excluding DC component at index 0)
    # Only look in tremor range: 2-15 Hz
    freq_mask = (fft_freqs > 2) & (fft_freqs < 15)
    masked_magnitude = np.where(freq_mask, fft_magnitude, 0)

    dominant_idx = np.argmax(masked_magnitude)
    dominant_freq = fft_freqs[dominant_idx]
    amplitude = fft_magnitude[dominant_idx]

    return dominant_freq, amplitude, fft_freqs, fft_magnitude


def compute_signal_amplitude(signal_data):
    """
    Compute signal amplitude metrics

    Returns:
        (peak_to_peak, rms, std_dev)
    """
    peak_to_peak = np.max(signal_data) - np.min(signal_data)
    rms = np.sqrt(np.mean(signal_data**2))
    std_dev = np.std(signal_data)

    return peak_to_peak, rms, std_dev


def extract_sensor_segment(sensor_data, start_time_str, duration_sec, time_offset_sec=0):
    """
    Extract a segment of sensor data based on timestamp

    Args:
        sensor_data: dict with 'timestamps' and sensor arrays
        start_time_str: ISO format timestamp from validation log
        duration_sec: duration of segment in seconds
        time_offset_sec: manual time offset for synchronization (seconds)

    Returns:
        dict with segment data
    """
    # Parse start time
    start_time = datetime.fromisoformat(start_time_str)

    # For now, we'll use relative timing within the sensor data
    # Assumes sensor data starts at roughly the same time as validation test
    # User needs to manually synchronize if needed

    # Find the segment in sensor data
    # This is a simplified approach - assumes sensor timestamps are milliseconds from start

    # Calculate offset in milliseconds
    offset_ms = time_offset_sec * 1000

    # Get first timestamp in sensor data
    sensor_start_ms = sensor_data['timestamps'][0]

    # For simplicity, we'll extract based on duration from current position
    # This is a placeholder - real implementation needs proper time synchronization

    print(f"   ⚠️  Using simple sequential extraction (TODO: implement proper timestamp sync)")

    return None  # Placeholder


def validate_frequency_sweep(log_data, sensor_data, sensor_column='accel_x', output_dir='validation_results'):
    """
    Validate frequency sweep test

    Compare commanded frequencies with measured frequencies from FFT
    """
    print("\n" + "="*70)
    print("🧪 VALIDATING FREQUENCY SWEEP TEST")
    print("="*70)

    # Extract frequency sweep entries from log
    freq_sweep_entries = [
        entry for entry in log_data
        if entry['test_phase'] == 'frequency_sweep'
    ]

    print(f"\nFound {len(freq_sweep_entries)} frequency sweep test segments")
    print(f"Analyzing sensor column: {sensor_column}")

    # For this analysis, we'll assume the sensor data is sequential
    # and matches the test sequence
    # Real implementation would need proper timestamp synchronization

    sampling_rate = 100  # Hz (from README)
    segment_duration = 30  # seconds per segment

    results = []
    commanded_freqs = []
    measured_freqs = []
    freq_errors = []

    # Estimate where each segment starts in the sensor data
    samples_per_segment = int(sampling_rate * segment_duration)

    # Skip initial samples (allow for startup time)
    start_sample = 100

    print("\n" + "-"*70)
    print("FREQUENCY ANALYSIS")
    print("-"*70)

    for i, entry in enumerate(freq_sweep_entries):
        commanded_freq = float(entry['frequency_hz'])
        duration = float(entry['duration_sec'])

        # Extract segment
        segment_start = start_sample + i * samples_per_segment
        segment_end = segment_start + samples_per_segment

        if segment_end > len(sensor_data[sensor_column]):
            print(f"\n⚠️  Segment {i+1}: Not enough sensor data")
            break

        segment = sensor_data[sensor_column][segment_start:segment_end]

        # Perform FFT analysis
        measured_freq, amplitude, fft_freqs, fft_magnitude = extract_frequency_fft(segment, sampling_rate)
        freq_error = abs(measured_freq - commanded_freq)

        # Store results
        results.append({
            'commanded': commanded_freq,
            'measured': measured_freq,
            'error': freq_error,
            'amplitude': amplitude,
            'pass': freq_error < 0.2
        })

        commanded_freqs.append(commanded_freq)
        measured_freqs.append(measured_freq)
        freq_errors.append(freq_error)

        # Print result
        status = "✓ PASS" if freq_error < 0.2 else "✗ FAIL"
        print(f"\n📍 Segment {i+1}:")
        print(f"   Commanded: {commanded_freq} Hz")
        print(f"   Measured:  {measured_freq:.2f} Hz")
        print(f"   Error:     {freq_error:.2f} Hz")
        print(f"   Amplitude: {amplitude:.2f}")
        print(f"   {status}")

    # Generate frequency validation plot
    if results:
        plt.figure(figsize=(12, 5))

        # Plot 1: Commanded vs Measured
        plt.subplot(1, 2, 1)
        plt.plot(commanded_freqs, commanded_freqs, 'k--', label='Perfect match', alpha=0.5)
        plt.plot(commanded_freqs, measured_freqs, 'bo-', label='Measured', markersize=8)
        plt.xlabel('Commanded Frequency (Hz)')
        plt.ylabel('Measured Frequency (Hz)')
        plt.title('Frequency Accuracy')
        plt.legend()
        plt.grid(True, alpha=0.3)

        # Plot 2: Frequency Error
        plt.subplot(1, 2, 2)
        plt.plot(commanded_freqs, freq_errors, 'ro-', markersize=8)
        plt.axhline(y=0.2, color='r', linestyle='--', label='Tolerance (±0.2 Hz)')
        plt.axhline(y=-0.2, color='r', linestyle='--')
        plt.xlabel('Commanded Frequency (Hz)')
        plt.ylabel('Frequency Error (Hz)')
        plt.title('Frequency Error vs Commanded')
        plt.legend()
        plt.grid(True, alpha=0.3)

        plt.tight_layout()
        output_path = Path(output_dir) / 'frequency_validation.png'
        plt.savefig(output_path, dpi=150)
        print(f"\n   📊 Plot saved: {output_path}")

    # Summary
    print("\n" + "-"*70)
    print("📊 FREQUENCY SWEEP VALIDATION SUMMARY")
    print("-"*70)

    if results:
        passed = sum(1 for r in results if r['pass'])
        total = len(results)
        mean_error = np.mean(freq_errors)
        max_error = np.max(np.abs(freq_errors))

        print(f"  Tests passed: {passed}/{total}")
        print(f"  Mean error: {mean_error:.3f} Hz")
        print(f"  Max error: {max_error:.3f} Hz")

        if passed == total:
            print("\n  ✅ ALL FREQUENCY TESTS PASSED")
        else:
            print(f"\n  ⚠️  {total - passed} FREQUENCY TESTS FAILED")
    else:
        print("  ⚠️  No results to validate")

    return results


def validate_amplitude_linearity(log_data, sensor_data, sensor_column='accel_x', output_dir='validation_results'):
    """
    Validate amplitude linearity test

    Check if measured amplitude correlates with PWM² (F = m*ω²*r)
    """
    print("\n" + "="*70)
    print("🧪 VALIDATING AMPLITUDE LINEARITY TEST")
    print("="*70)

    # Extract amplitude linearity entries from log
    amp_entries = [
        entry for entry in log_data
        if entry['test_phase'] == 'amplitude_linearity'
    ]

    print(f"\nFound {len(amp_entries)} amplitude test segments")
    print(f"Analyzing sensor column: {sensor_column}")

    sampling_rate = 100  # Hz
    segment_duration = 20  # seconds per segment
    samples_per_segment = int(sampling_rate * segment_duration)

    # Estimate start position (after frequency sweep)
    freq_sweep_count = len([e for e in log_data if e['test_phase'] == 'frequency_sweep'])
    start_sample = 100 + freq_sweep_count * int(sampling_rate * 30)  # 30s per freq sweep

    commanded_pwm = []
    pwm_squared = []
    measured_amplitudes = []

    print("\n" + "-"*70)
    print("AMPLITUDE ANALYSIS")
    print("-"*70)

    for i, entry in enumerate(amp_entries):
        pwm_range = entry['pwm_percent']
        max_pwm = int(pwm_range.split('-')[1])  # Extract max PWM value
        duration = float(entry['duration_sec'])

        # Extract segment
        segment_start = start_sample + i * samples_per_segment
        segment_end = segment_start + samples_per_segment

        if segment_end > len(sensor_data[sensor_column]):
            print(f"\n⚠️  Segment {i+1}: Not enough sensor data")
            break

        segment = sensor_data[sensor_column][segment_start:segment_end]

        # Compute amplitude
        ptp, rms, std = compute_signal_amplitude(segment)

        commanded_pwm.append(max_pwm)
        pwm_squared.append(max_pwm ** 2)
        measured_amplitudes.append(ptp)

        print(f"\n📍 PWM {max_pwm}%:")
        print(f"   Expected force ∝ {max_pwm**2}")
        print(f"   Measured amplitude (p-p): {ptp:.4f} m/s²")
        print(f"   RMS: {rms:.4f} m/s²")

    # Perform linear regression: amplitude vs PWM²
    if len(pwm_squared) > 1:
        slope, intercept, r_value, p_value, std_err = stats.linregress(pwm_squared, measured_amplitudes)
        r_squared = r_value ** 2

        print("\n" + "-"*70)
        print("📊 AMPLITUDE LINEARITY VALIDATION SUMMARY")
        print("-"*70)
        print(f"  Linear fit: Amplitude = {slope:.6f} × PWM² + {intercept:.4f}")
        print(f"  R² = {r_squared:.4f}")
        print(f"  p-value = {p_value:.4e}")

        if r_squared > 0.95:
            print(f"\n  ✅ PASS - Strong correlation (R² > 0.95)")
        else:
            print(f"\n  ⚠️  FAIL - Weak correlation (R² = {r_squared:.4f} < 0.95)")

        # Generate plot
        plt.figure(figsize=(10, 6))
        plt.scatter(pwm_squared, measured_amplitudes, s=100, alpha=0.7, label='Measured')

        # Fit line
        fit_line = slope * np.array(pwm_squared) + intercept
        plt.plot(pwm_squared, fit_line, 'r--', label=f'Linear fit (R²={r_squared:.3f})')

        plt.xlabel('PWM² (% squared)')
        plt.ylabel('Amplitude (m/s², peak-to-peak)')
        plt.title('Amplitude vs PWM² - Centrifugal Force Validation\nF = m×ω²×r, where ω ∝ PWM')
        plt.legend()
        plt.grid(True, alpha=0.3)

        output_path = Path(output_dir) / 'amplitude_linearity.png'
        plt.savefig(output_path, dpi=150)
        print(f"\n   📊 Plot saved: {output_path}")

        return r_squared
    else:
        print("\n⚠️  Not enough data points for regression")
        return None


def validate_step_response(log_data, sensor_data, sensor_column='accel_x', output_dir='validation_results'):
    """
    Validate step response test

    Measure rise time, overshoot, settling time
    """
    print("\n" + "="*70)
    print("🧪 VALIDATING STEP RESPONSE TEST")
    print("="*70)

    step_entries = [
        entry for entry in log_data
        if entry['test_phase'] == 'step_response'
    ]

    print(f"\nFound {len(step_entries)} step response segments")
    print(f"Note: Step response analysis requires manual inspection")
    print("      Check for rapid transitions and minimal overshoot")

    print("\n" + "-"*70)
    print("📊 STEP RESPONSE VALIDATION SUMMARY")
    print("-"*70)
    print("  ⚠️  Manual inspection recommended")
    print("  TODO: Implement automated rise time / overshoot analysis")


def generate_validation_report(log_file, sensor_file, output_dir="validation_results"):
    """
    Main validation function - generates comprehensive report
    """
    print("\n" + "="*70)
    print("DATA QUALITY VALIDATION ANALYSIS")
    print("="*70)
    print(f"\nValidation Log: {log_file}")
    print(f"Sensor Data: {sensor_file}")
    print(f"Output Directory: {output_dir}")

    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)

    # Load data
    try:
        log_data = load_validation_log(log_file)
        sensor_data = load_sensor_data(sensor_file)
    except Exception as e:
        print(f"\n❌ Error loading data: {e}")
        return

    # Run validation tests
    print("\n" + "="*70)
    print("RUNNING VALIDATION TESTS")
    print("="*70)

    freq_results = validate_frequency_sweep(log_data, sensor_data, output_dir=output_dir)
    r_squared = validate_amplitude_linearity(log_data, sensor_data, output_dir=output_dir)
    validate_step_response(log_data, sensor_data, output_dir=output_dir)

    print("\n" + "="*70)
    print("✅ VALIDATION ANALYSIS COMPLETE")
    print("="*70)
    print(f"\n📊 Results saved to: {output_dir}/")
    print("   - frequency_validation.png")
    print("   - amplitude_linearity.png")


def main():
    """Main entry point"""
    if len(sys.argv) < 3:
        print("Usage: python3 analyze_validation_test.py <validation_log.csv> <sensor_data.csv>")
        print("\nExample:")
        print("  python3 analyze_validation_test.py validation_test_log_20260127_143022.csv tremor_cycle1_20260127_143000.csv")
        sys.exit(1)

    log_file = sys.argv[1]
    sensor_file = sys.argv[2]

    # Check files exist
    if not Path(log_file).exists():
        print(f"❌ Error: Validation log file not found: {log_file}")
        sys.exit(1)

    if not Path(sensor_file).exists():
        print(f"❌ Error: Sensor data file not found: {sensor_file}")
        sys.exit(1)

    # Run validation
    generate_validation_report(log_file, sensor_file)


if __name__ == "__main__":
    main()
