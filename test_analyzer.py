#!/usr/bin/env python3
"""
Test script for offline_analyzer_motor_optimized.py
Processes both CSV files and displays tremor analysis results
"""

import numpy as np
from scipy.signal import butter, filtfilt, welch, hilbert
import os

# Configuration (matching analyzer)
FS = 100.0
FILTER_ORDER = 4
FREQ_REST_LOW = 3.0
FREQ_REST_HIGH = 6.0
FREQ_ESSENTIAL_LOW = 6.0
FREQ_ESSENTIAL_HIGH = 12.0
WINDOW_SEC = 4
PSD_OVERLAP = 0.5
TREMOR_POWER_THRESHOLD = 0.01
CLASSIFICATION_RATIO = 2.0

def load_csv_data(filepath):
    """Load CSV data from file"""
    data = {'Timestamp': [], 'Ax': [], 'Ay': [], 'Az': [],
            'Gx': [], 'Gy': [], 'Gz': []}

    with open(filepath, 'r') as f:
        lines = f.readlines()

        # Find header
        header_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('Timestamp,'):
                header_idx = i
                break

        # Parse data
        for line in lines[header_idx + 1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                parts = line.split(',')
                if len(parts) == 7:
                    data['Timestamp'].append(int(parts[0]))
                    data['Ax'].append(float(parts[1]))
                    data['Ay'].append(float(parts[2]))
                    data['Az'].append(float(parts[3]))
                    data['Gx'].append(float(parts[4]))
                    data['Gy'].append(float(parts[5]))
                    data['Gz'].append(float(parts[6]))
            except (ValueError, IndexError):
                continue

    # Convert to numpy arrays
    for key in data:
        data[key] = np.array(data[key])

    return data

def analyze_tremor(data):
    """Analyze tremor from CSV data"""

    # Extract accelerometer data
    ax = data['Ax']
    ay = data['Ay']
    az = data['Az']

    # Remove DC offset (gravity + bias)
    ax_clean = ax - np.mean(ax)
    ay_clean = ay - np.mean(ay)
    az_clean = az - np.mean(az)

    # Create filters
    nyquist = 0.5 * FS

    # Rest tremor filter (3-6 Hz)
    b_rest, a_rest = butter(FILTER_ORDER,
                            [FREQ_REST_LOW/nyquist, FREQ_REST_HIGH/nyquist],
                            btype='band')

    # Essential tremor filter (6-12 Hz)
    b_ess, a_ess = butter(FILTER_ORDER,
                          [FREQ_ESSENTIAL_LOW/nyquist, FREQ_ESSENTIAL_HIGH/nyquist],
                          btype='band')

    # Apply filters
    rest_x = filtfilt(b_rest, a_rest, ax_clean)
    rest_y = filtfilt(b_rest, a_rest, ay_clean)
    rest_z = filtfilt(b_rest, a_rest, az_clean)

    ess_x = filtfilt(b_ess, a_ess, ax_clean)
    ess_y = filtfilt(b_ess, a_ess, ay_clean)
    ess_z = filtfilt(b_ess, a_ess, az_clean)

    # Calculate PSDs
    psd_data = {}
    for axis_name, signal in [('X', ax_clean), ('Y', ay_clean), ('Z', az_clean)]:
        nperseg = min(len(signal), int(FS * WINDOW_SEC))
        noverlap = int(nperseg * PSD_OVERLAP)
        f, psd = welch(signal, FS, nperseg=nperseg, noverlap=noverlap)
        psd_data[axis_name] = {'freq': f, 'psd': psd}

    # Calculate metrics
    metrics = {}

    # RMS amplitudes
    metrics['rest_rms'] = {
        'X': np.sqrt(np.mean(rest_x**2)),
        'Y': np.sqrt(np.mean(rest_y**2)),
        'Z': np.sqrt(np.mean(rest_z**2))
    }

    metrics['ess_rms'] = {
        'X': np.sqrt(np.mean(ess_x**2)),
        'Y': np.sqrt(np.mean(ess_y**2)),
        'Z': np.sqrt(np.mean(ess_z**2))
    }

    # Total powers
    metrics['rest_power_total'] = sum(metrics['rest_rms'].values())
    metrics['ess_power_total'] = sum(metrics['ess_rms'].values())

    # Dominant frequencies
    metrics['dominant_freq'] = {}
    metrics['peak_power'] = {}

    for axis in ['X', 'Y', 'Z']:
        f = psd_data[axis]['freq']
        psd = psd_data[axis]['psd']

        # Limit to tremor range (3-12 Hz)
        tremor_mask = (f >= 3) & (f <= 12)
        f_tremor = f[tremor_mask]
        psd_tremor = psd[tremor_mask]

        if len(psd_tremor) > 0:
            peak_idx = np.argmax(psd_tremor)
            metrics['dominant_freq'][axis] = f_tremor[peak_idx]
            metrics['peak_power'][axis] = psd_tremor[peak_idx]
        else:
            metrics['dominant_freq'][axis] = 0
            metrics['peak_power'][axis] = 0

    # Power in specific bands from PSD
    for axis in ['X', 'Y', 'Z']:
        f = psd_data[axis]['freq']
        psd = psd_data[axis]['psd']

        # Rest tremor power (3-6 Hz)
        rest_mask = (f >= FREQ_REST_LOW) & (f <= FREQ_REST_HIGH)
        metrics['rest_rms'][f'{axis}_psd_power'] = np.sum(psd[rest_mask])

        # Essential tremor power (6-12 Hz)
        ess_mask = (f >= FREQ_ESSENTIAL_LOW) & (f <= FREQ_ESSENTIAL_HIGH)
        metrics['ess_rms'][f'{axis}_psd_power'] = np.sum(psd[ess_mask])

    # Classify tremor
    power_ratio = metrics['rest_power_total'] / (metrics['ess_power_total'] + 1e-10)

    if metrics['rest_power_total'] < TREMOR_POWER_THRESHOLD and \
       metrics['ess_power_total'] < TREMOR_POWER_THRESHOLD:
        metrics['tremor_type'] = "No significant tremor detected"
        metrics['confidence'] = "N/A"
    elif power_ratio > CLASSIFICATION_RATIO:
        metrics['tremor_type'] = "Rest Tremor (Parkinsonian)"
        metrics['confidence'] = f"High (ratio: {power_ratio:.2f})"
    elif power_ratio < 1/CLASSIFICATION_RATIO:
        metrics['tremor_type'] = "Essential Tremor (Postural)"
        metrics['confidence'] = f"High (ratio: {power_ratio:.2f})"
    else:
        metrics['tremor_type'] = "Mixed Tremor"
        metrics['confidence'] = f"Moderate (ratio: {power_ratio:.2f})"

    return metrics

def print_results(filename, metrics):
    """Print analysis results"""
    print("\n" + "="*70)
    print(f"FILE: {filename}")
    print("="*70)

    print(f"\n{'─'*70}")
    print("TREMOR CLASSIFICATION")
    print(f"{'─'*70}")
    print(f"  Type: {metrics['tremor_type']}")
    print(f"  Confidence: {metrics['confidence']}")

    print(f"\n{'─'*70}")
    print("REST TREMOR BAND (3-6 Hz) - RMS Amplitude")
    print(f"{'─'*70}")
    for axis in ['X', 'Y', 'Z']:
        print(f"  {axis}-axis: {metrics['rest_rms'][axis]:.4f} m/s²")
    print(f"  Total Power: {metrics['rest_power_total']:.4f}")

    print(f"\n{'─'*70}")
    print("ESSENTIAL TREMOR BAND (6-12 Hz) - RMS Amplitude")
    print(f"{'─'*70}")
    for axis in ['X', 'Y', 'Z']:
        print(f"  {axis}-axis: {metrics['ess_rms'][axis]:.4f} m/s²")
    print(f"  Total Power: {metrics['ess_power_total']:.4f}")

    print(f"\n{'─'*70}")
    print("DOMINANT FREQUENCIES (from PSD)")
    print(f"{'─'*70}")
    for axis in ['X', 'Y', 'Z']:
        freq = metrics['dominant_freq'][axis]
        power = metrics['peak_power'][axis]
        tremor_type = "Rest" if 3 <= freq <= 6 else "Essential" if 6 < freq <= 12 else "Unknown"
        print(f"  {axis}-axis: {freq:.2f} Hz (Power: {power:.6f}) [{tremor_type} range]")

    print(f"\n{'─'*70}")
    print("CLINICAL INTERPRETATION")
    print(f"{'─'*70}")

    # Interpret results
    if "Rest" in metrics['tremor_type']:
        print("  ✅ Rest tremor detected (Parkinson's-like)")
        print("  → Dominant in 3-6 Hz band")
        print("  → Appears at rest, may reduce with movement")
        print("  → Typical of Parkinson's disease")
    elif "Essential" in metrics['tremor_type']:
        print("  ✅ Essential tremor detected (Postural)")
        print("  → Dominant in 6-12 Hz band")
        print("  → Appears when holding position")
        print("  → Higher frequency than Parkinson's")
    elif "Mixed" in metrics['tremor_type']:
        print("  ⚠️  Mixed tremor pattern")
        print("  → Power in both rest and essential bands")
        print("  → May indicate combined pathology")
        print("  → Requires clinical correlation")
    else:
        print("  ℹ️  No significant tremor detected")
        print("  → Tremor power below detection threshold")

    # Assess severity
    max_rms = max(metrics['rest_rms']['X'], metrics['rest_rms']['Y'], metrics['rest_rms']['Z'],
                  metrics['ess_rms']['X'], metrics['ess_rms']['Y'], metrics['ess_rms']['Z'])

    print(f"\n  Severity Assessment (Max RMS: {max_rms:.4f} m/s²):")
    if max_rms < 0.05:
        print("    • Minimal/Absent tremor")
    elif max_rms < 0.15:
        print("    • Mild tremor")
    elif max_rms < 0.30:
        print("    • Moderate tremor")
    else:
        print("    • Severe tremor")

    # Identify dominant axis
    rest_dominant = max(metrics['rest_rms'], key=metrics['rest_rms'].get)
    ess_dominant = max(metrics['ess_rms'], key=metrics['ess_rms'].get)

    print(f"\n  Dominant Tremor Axis:")
    print(f"    • Rest tremor: {rest_dominant}-axis ({metrics['rest_rms'][rest_dominant]:.4f} m/s²)")
    print(f"    • Essential tremor: {ess_dominant}-axis ({metrics['ess_rms'][ess_dominant]:.4f} m/s²)")

def main():
    """Main test function"""
    csv_files = [
        'tremor_cycle1_20260121_141523.csv',
        'tremor_cycle1_20260121_160502.csv'
    ]

    print("\n" + "="*70)
    print("TREMOR ANALYZER TEST - Motor-Holding Scenario")
    print("="*70)
    print(f"Sampling Rate: {FS} Hz")
    print(f"Rest Tremor Band: {FREQ_REST_LOW}-{FREQ_REST_HIGH} Hz (Parkinson's)")
    print(f"Essential Tremor Band: {FREQ_ESSENTIAL_LOW}-{FREQ_ESSENTIAL_HIGH} Hz (Postural)")
    print("="*70)

    for csv_file in csv_files:
        filepath = f'/home/user/Proceesing-data-based-RPI4/{csv_file}'

        if not os.path.exists(filepath):
            print(f"\n❌ File not found: {csv_file}")
            continue

        try:
            # Load data
            print(f"\n📂 Loading {csv_file}...")
            data = load_csv_data(filepath)

            print(f"   Samples: {len(data['Timestamp'])}")
            print(f"   Duration: {data['Timestamp'][-1]/1000.0:.1f}s")

            # Analyze
            print(f"   Analyzing tremor patterns...")
            metrics = analyze_tremor(data)

            # Print results
            print_results(csv_file, metrics)

        except Exception as e:
            print(f"\n❌ Error processing {csv_file}: {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
    print("\nTo view graphical analysis, run:")
    print("  python3 offline_analyzer_motor_optimized.py")
    print("\nThen load CSV file using the GUI.")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
