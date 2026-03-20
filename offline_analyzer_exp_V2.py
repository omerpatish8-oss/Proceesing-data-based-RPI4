#!/usr/bin/env python3
"""
Offline Analyzer v2 - Simplified Signal Processing Pipeline
============================================================
Engineering-grade pipeline for extracting rest tremor characteristics
from MPU6050 accelerometer data recorded on Raspberry Pi 4.

Pipeline Phases:
  1. Signal Preparation: Resample to uniform 100 Hz, compute resultant, remove DC
  2. Frequency Isolation: 4th-order zero-phase Butterworth bandpass (1-15 Hz)
  3. Frequency Domain: Welch's PSD (Hanning, 4s window, 50% overlap)
  4. Feature Extraction: Dominant freq, peak power, band power, FWHM, RMS
"""

import sys
import numpy as np
from scipy.signal import butter, filtfilt, welch
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from tkinter import filedialog
import tkinter as tk

# ── Configuration ──────────────────────────────────────────────────────────────
FS_TARGET = 100.0           # Target uniform sampling rate (Hz)
FILTER_ORDER = 4            # Butterworth filter order
BANDPASS_LOW = 1.0          # Bandpass lower cutoff (Hz)
BANDPASS_HIGH = 15.0        # Bandpass upper cutoff (Hz)
WELCH_WINDOW_SEC = 4.0      # Welch window length (seconds) → 0.25 Hz resolution
WELCH_OVERLAP_FRAC = 0.5    # 50% overlap
TREMOR_BAND_LOW = 3.0       # Rest tremor band lower bound (Hz)
TREMOR_BAND_HIGH = 7.0      # Rest tremor band upper bound (Hz)


# ── Phase 1: Signal Preparation & Correction ──────────────────────────────────

def load_csv(filepath):
    """Load CSV with columns: Timestamp, Ax, Ay, Az (+ optional extras)."""
    timestamps, ax, ay, az = [], [], [], []

    with open(filepath, 'r') as f:
        lines = f.readlines()

    # Find header line
    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('Timestamp,'):
            header_idx = i
            break

    # Parse data rows
    for line in lines[header_idx + 1:]:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(',')
        if len(parts) >= 4:
            try:
                timestamps.append(int(parts[0]))
                ax.append(float(parts[1]))
                ay.append(float(parts[2]))
                az.append(float(parts[3]))
            except (ValueError, IndexError):
                continue

    return (np.array(timestamps, dtype=np.float64),
            np.array(ax), np.array(ay), np.array(az))


def resample_to_uniform(timestamps_ms, ax, ay, az, fs_target=FS_TARGET):
    """
    Resample non-uniform data onto a strict uniform time grid.

    Embedded sensors (MPU6050 over I2C/SPI) suffer from sampling jitter.
    FFT requires uniform spacing, so we interpolate onto an exact grid.

    Returns: t_uniform (seconds), ax_u, ay_u, az_u
    """
    # Convert timestamps to seconds relative to start
    t_raw = (timestamps_ms - timestamps_ms[0]) / 1000.0
    duration = t_raw[-1]

    actual_fs = len(t_raw) / duration
    print(f"  Raw samples: {len(t_raw)}")
    print(f"  Duration: {duration:.2f} s")
    print(f"  Effective sampling rate: {actual_fs:.2f} Hz")

    # Create uniform time grid at exactly fs_target Hz
    n_samples = int(duration * fs_target)
    t_uniform = np.linspace(0, duration, n_samples, endpoint=False)

    # Cubic spline interpolation per axis
    ax_u = interp1d(t_raw, ax, kind='cubic', fill_value='extrapolate')(t_uniform)
    ay_u = interp1d(t_raw, ay, kind='cubic', fill_value='extrapolate')(t_uniform)
    az_u = interp1d(t_raw, az, kind='cubic', fill_value='extrapolate')(t_uniform)

    print(f"  Resampled to {n_samples} samples at {fs_target} Hz")
    return t_uniform, ax_u, ay_u, az_u


def compute_resultant_and_remove_dc(ax, ay, az):
    """
    Compute resultant acceleration magnitude, then remove DC offset (gravity).

    A_res = sqrt(Ax² + Ay² + Az²)
    Then subtract mean to center oscillations at zero.
    """
    a_res = np.sqrt(ax**2 + ay**2 + az**2)
    a_res_centered = a_res - np.mean(a_res)
    return a_res_centered


# ── Phase 2: Frequency Isolation ──────────────────────────────────────────────

def bandpass_filter(signal, fs=FS_TARGET, low=BANDPASS_LOW, high=BANDPASS_HIGH,
                    order=FILTER_ORDER):
    """
    Apply zero-phase Butterworth bandpass filter.

    filtfilt passes the signal forward then backward through the filter,
    eliminating phase distortion entirely.
    """
    nyquist = 0.5 * fs
    b, a = butter(order, [low / nyquist, high / nyquist], btype='band')
    return filtfilt(b, a, signal)


# ── Phase 3: Frequency Domain Analysis ────────────────────────────────────────

def compute_psd(signal, fs=FS_TARGET):
    """
    Compute Power Spectral Density using Welch's method.

    Parameters chosen for long recordings with periodic tremor:
      - Hanning window, 4 seconds (400 samples) → 0.25 Hz resolution
      - 50% overlap for variance reduction
    """
    nperseg = int(fs * WELCH_WINDOW_SEC)  # 400 samples
    noverlap = int(nperseg * WELCH_OVERLAP_FRAC)  # 200 samples
    freqs, psd = welch(signal, fs, window='hann', nperseg=nperseg,
                       noverlap=noverlap)
    return freqs, psd


# ── Phase 4: Feature Extraction ──────────────────────────────────────────────

def extract_features(freqs, psd, filtered_signal):
    """
    Extract tremor profile features from PSD and filtered time-domain signal.

    Returns dict with:
      - dominant_freq:  Frequency of peak power in 3-7 Hz band
      - peak_power:     PSD amplitude at dominant frequency
      - band_power:     Total power (area under PSD) in 3-7 Hz band
      - fwhm:           Full Width at Half Maximum of the dominant peak
      - rms:            Time-domain RMS of filtered signal
      - motor_rpm:      Estimated motor RPM from dominant frequency
    """
    features = {}

    # Mask for tremor band (3-7 Hz)
    band_mask = (freqs >= TREMOR_BAND_LOW) & (freqs <= TREMOR_BAND_HIGH)
    band_freqs = freqs[band_mask]
    band_psd = psd[band_mask]

    if len(band_psd) == 0:
        return {k: 0.0 for k in ['dominant_freq', 'peak_power', 'band_power',
                                  'fwhm', 'rms', 'motor_rpm']}

    # Dominant frequency: frequency bin with max power in 3-7 Hz
    peak_idx = np.argmax(band_psd)
    features['dominant_freq'] = band_freqs[peak_idx]
    features['peak_power'] = band_psd[peak_idx]

    # Band power: area under PSD curve (trapezoidal integration)
    freq_resolution = freqs[1] - freqs[0]
    features['band_power'] = np.trapz(band_psd, dx=freq_resolution)

    # FWHM: width of peak at half its maximum height
    half_max = features['peak_power'] / 2.0
    above_half = band_psd >= half_max
    if np.any(above_half):
        indices = np.where(above_half)[0]
        features['fwhm'] = (indices[-1] - indices[0]) * freq_resolution
    else:
        features['fwhm'] = 0.0

    # Time-domain RMS of filtered signal
    features['rms'] = np.sqrt(np.mean(filtered_signal**2))

    # Motor RPM estimate (freq Hz × 60 = RPM)
    features['motor_rpm'] = features['dominant_freq'] * 60.0

    return features


# ── Visualization ─────────────────────────────────────────────────────────────

def plot_results(t, a_res_centered, filtered, freqs, psd, features):
    """Generate a clean 2×2 summary dashboard."""
    fig = plt.figure(figsize=(14, 9))
    fig.suptitle('Tremor Signal Processing — v2 Pipeline', fontsize=13,
                 fontweight='bold')
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.3)

    # ── Plot 1: Raw resultant (DC-removed) ─────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(t, a_res_centered, color='#2F4F4F', linewidth=0.6, alpha=0.7)
    ax1.set_title('Resultant Acceleration (DC Removed)')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Acceleration (m/s²)')
    ax1.margins(x=0)
    ax1.grid(True, alpha=0.3)

    # ── Plot 2: Filtered signal (1-15 Hz) ──────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(t, filtered, color='#DC143C', linewidth=0.8)
    ax2.set_title(f'Bandpass Filtered ({BANDPASS_LOW}-{BANDPASS_HIGH} Hz)')
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('Acceleration (m/s²)')
    ax2.margins(x=0)
    ax2.grid(True, alpha=0.3)
    # Annotate RMS
    ax2.text(0.02, 0.95, f'RMS = {features["rms"]:.4f} m/s²',
             transform=ax2.transAxes, fontsize=9, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # ── Plot 3: PSD with tremor band highlighted ───────────────
    ax3 = fig.add_subplot(gs[1, 0])
    psd_db = 10 * np.log10(psd + 1e-12)
    ax3.plot(freqs, psd_db, color='black', linewidth=1)

    # Highlight 3-7 Hz band
    band_mask = (freqs >= TREMOR_BAND_LOW) & (freqs <= TREMOR_BAND_HIGH)
    ax3.fill_between(freqs, psd_db, where=band_mask,
                     color='#DC143C', alpha=0.3, label='Rest Tremor (3-7 Hz)')

    # Mark dominant frequency
    dom_f = features['dominant_freq']
    dom_p = 10 * np.log10(features['peak_power'] + 1e-12)
    ax3.plot(dom_f, dom_p, 'ro', markersize=8,
             label=f'Peak: {dom_f:.2f} Hz ({features["motor_rpm"]:.0f} RPM)')
    ax3.set_title('Power Spectral Density (Welch)')
    ax3.set_xlabel('Frequency (Hz)')
    ax3.set_ylabel('Power (dB)')
    ax3.set_xlim(0, 20)
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)

    # ── Plot 4: Feature summary table ──────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis('off')

    sep = '─' * 38
    summary = (
        f"EXTRACTED FEATURES\n"
        f"{sep}\n"
        f"Dominant Frequency:   {features['dominant_freq']:.2f} Hz\n"
        f"Estimated Motor RPM:  {features['motor_rpm']:.0f}\n"
        f"Peak Power:           {features['peak_power']:.6f}\n"
        f"Band Power (3-7 Hz):  {features['band_power']:.6f}\n"
        f"Tremor Dispersion:    {features['fwhm']:.2f} Hz (FWHM)\n"
        f"Time-Domain RMS:      {features['rms']:.4f} m/s²\n"
        f"{sep}\n"
        f"\n"
        f"PIPELINE PARAMETERS\n"
        f"{sep}\n"
        f"Target Fs:            {FS_TARGET} Hz\n"
        f"Bandpass:             {BANDPASS_LOW}-{BANDPASS_HIGH} Hz\n"
        f"Filter:               Butterworth order {FILTER_ORDER}\n"
        f"Welch window:         {WELCH_WINDOW_SEC}s (Hanning)\n"
        f"Welch overlap:        {WELCH_OVERLAP_FRAC*100:.0f}%\n"
        f"Freq resolution:      {FS_TARGET/(FS_TARGET*WELCH_WINDOW_SEC):.2f} Hz\n"
    )
    ax4.text(0.05, 0.95, summary, transform=ax4.transAxes,
             fontfamily='monospace', fontsize=9, verticalalignment='top')

    plt.tight_layout()
    plt.show()


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(filepath):
    """Execute the full 4-phase signal processing pipeline."""
    print("\n" + "=" * 60)
    print("TREMOR ANALYSIS PIPELINE v2")
    print("=" * 60)

    # Phase 1: Load & prepare
    print("\n[Phase 1] Signal Preparation & Correction")
    timestamps, ax_raw, ay_raw, az_raw = load_csv(filepath)
    t, ax_u, ay_u, az_u = resample_to_uniform(timestamps, ax_raw, ay_raw, az_raw)
    a_res = compute_resultant_and_remove_dc(ax_u, ay_u, az_u)
    print(f"  Resultant vector computed, DC removed (mean → 0)")

    # Phase 2: Filter
    print("\n[Phase 2] Frequency Isolation")
    filtered = bandpass_filter(a_res)
    print(f"  Butterworth bandpass {BANDPASS_LOW}-{BANDPASS_HIGH} Hz, "
          f"order {FILTER_ORDER}, zero-phase")

    # Phase 3: PSD
    print("\n[Phase 3] Frequency Domain Analysis (Welch)")
    freqs, psd = compute_psd(filtered)
    print(f"  Window: {WELCH_WINDOW_SEC}s Hanning, "
          f"{WELCH_OVERLAP_FRAC*100:.0f}% overlap, "
          f"resolution: {freqs[1]-freqs[0]:.2f} Hz")

    # Phase 4: Features
    print("\n[Phase 4] Feature Extraction")
    features = extract_features(freqs, psd, filtered)

    print(f"  Dominant Frequency:  {features['dominant_freq']:.2f} Hz")
    print(f"  Motor RPM estimate:  {features['motor_rpm']:.0f}")
    print(f"  Peak Power:          {features['peak_power']:.6f}")
    print(f"  Band Power (3-7 Hz): {features['band_power']:.6f}")
    print(f"  Tremor Dispersion:   {features['fwhm']:.2f} Hz (FWHM)")
    print(f"  Time-Domain RMS:     {features['rms']:.4f} m/s²")
    print("=" * 60 + "\n")

    # Visualize
    plot_results(t, a_res, filtered, freqs, psd, features)

    return features


def main():
    """Entry point: pick a CSV file and run the pipeline."""
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        root = tk.Tk()
        root.withdraw()
        filepath = filedialog.askopenfilename(
            title="Select Tremor Data CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        root.destroy()
        if not filepath:
            print("No file selected. Exiting.")
            return

    run_pipeline(filepath)


if __name__ == "__main__":
    main()
