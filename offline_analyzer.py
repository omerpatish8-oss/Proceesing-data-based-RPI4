#!/usr/bin/env python3
"""
Tremor Analysis Tool - Research-Based Implementation
Based on MDPI papers: Parkinson's tremor assessment with MPU6050 + ESP32
Uses resultant vector magnitude for accelerometer and gyroscope (optional)
Maintains both Rest (3-7 Hz) and Essential (6-12 Hz) tremor detection
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
from scipy.signal import butter, filtfilt, welch, hilbert, freqz
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.gridspec import GridSpec
import mplcursors

# ==========================================
# CONFIGURATION PARAMETERS (Research-Based)
# ==========================================
FS = 100.0              # Sampling rate (Hz)
FILTER_ORDER = 4        # Butterworth filter order (standard)

# Tremor frequency bands (from research papers)
FREQ_REST_LOW = 3.0     # Rest tremor (Parkinson's): 3-7 Hz (Paper 1)
FREQ_REST_HIGH = 7.0    # Extended from 6 to 7 Hz per research
FREQ_ESSENTIAL_LOW = 6.0   # Essential tremor: 6-12 Hz
FREQ_ESSENTIAL_HIGH = 12.0

# Combined tremor band for main filter
FREQ_TREMOR_LOW = 3.0   # Lower bound
FREQ_TREMOR_HIGH = 12.0 # Upper bound

# PSD parameters
WINDOW_SEC = 4          # Welch window size (seconds)
PSD_OVERLAP = 0.5       # 50% overlap

# Tremor detection thresholds
TREMOR_POWER_THRESHOLD = 0.01
CLASSIFICATION_RATIO = 2.0

# Visual styling
COL_REST = '#DC143C'        # Crimson - Rest tremor
COL_ESSENTIAL = '#4169E1'   # Royal Blue - Essential tremor
COL_RAW = '#2F4F4F'         # Dark Slate Gray - Raw signal
COL_FILTERED = '#FF6347'    # Tomato - Filtered signal
COL_GYRO = '#9370DB'        # Medium Purple - Gyroscope

class TremorAnalyzerResearch:
    def __init__(self, root):
        self.root = root
        self.root.title("Tremor Analyzer - Research-Based (Resultant Vector Analysis)")
        self.root.geometry("1600x1000")

        # Data storage
        self.csv_path = None
        self.data = None

        # Setup UI
        self.setup_style()
        self.setup_main_layout()
        self.create_analysis_dashboard()

    def setup_style(self):
        """Configure matplotlib style"""
        plt.style.use('seaborn-v0_8-whitegrid')
        plt.rcParams.update({
            'font.family': 'sans-serif',
            'font.size': 9,
            'axes.labelsize': 9,
            'axes.titlesize': 10,
            'axes.titleweight': 'bold',
            'lines.linewidth': 1.2,
            'figure.autolayout': True
        })

    def setup_main_layout(self):
        """Create main UI layout"""
        # Top control panel
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(control_frame, text="📂 Load CSV Data",
                   command=self.load_and_process).pack(side=tk.LEFT, padx=10)

        self.lbl_file = ttk.Label(control_frame, text="No file loaded",
                                  font=("Arial", 9), foreground="gray")
        self.lbl_file.pack(side=tk.LEFT, padx=10)

        self.lbl_status = ttk.Label(control_frame, text="Ready",
                                    font=("Arial", 10, "bold"))
        self.lbl_status.pack(side=tk.LEFT, padx=20)

        # Info panel (right side)
        self.info_frame = ttk.LabelFrame(control_frame, text="Tremor Classification",
                                         padding="5")
        self.info_frame.pack(side=tk.RIGHT, padx=10)

        self.lbl_tremor_type = ttk.Label(self.info_frame, text="Type: N/A",
                                         font=("Arial", 11, "bold"))
        self.lbl_tremor_type.pack()

        self.lbl_confidence = ttk.Label(self.info_frame, text="Confidence: N/A")
        self.lbl_confidence.pack()

    def create_analysis_dashboard(self):
        """Create research-based analysis dashboard"""
        # Main canvas frame
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create figure with custom layout
        self.fig = plt.figure(figsize=(16, 10))
        gs = GridSpec(4, 3, figure=self.fig, hspace=0.4, wspace=0.3)

        # Row 1: FILTER VERIFICATION
        self.ax_bode_mag = self.fig.add_subplot(gs[0, 0])
        self.ax_bode_phase = self.fig.add_subplot(gs[0, 1])
        self.ax_filter_comparison = self.fig.add_subplot(gs[0, 2])

        # Row 2: ACCELEROMETER (Resultant Vector)
        self.ax_accel_raw = self.fig.add_subplot(gs[1, 0])
        self.ax_accel_filtered = self.fig.add_subplot(gs[1, 1])
        self.ax_accel_overlay = self.fig.add_subplot(gs[1, 2])

        # Row 3: ACCELEROMETER FREQUENCY ANALYSIS
        self.ax_accel_psd = self.fig.add_subplot(gs[2, 0])
        self.ax_accel_bands = self.fig.add_subplot(gs[2, 1])
        self.ax_spectrogram = self.fig.add_subplot(gs[2, 2])

        # Row 4: GYROSCOPE + METRICS
        self.ax_gyro_raw = self.fig.add_subplot(gs[3, 0])
        self.ax_gyro_filtered = self.fig.add_subplot(gs[3, 1])
        self.ax_metrics = self.fig.add_subplot(gs[3, 2])

        # Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=canvas_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Toolbar
        toolbar_frame = ttk.Frame(canvas_frame)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        toolbar.update()

        # Initialize plots
        self.clear_all_plots()

    def clear_all_plots(self):
        """Clear all plots and show instructions"""
        for ax in [self.ax_bode_mag, self.ax_bode_phase, self.ax_filter_comparison,
                   self.ax_accel_raw, self.ax_accel_filtered, self.ax_accel_overlay,
                   self.ax_accel_psd, self.ax_accel_bands, self.ax_spectrogram,
                   self.ax_gyro_raw, self.ax_gyro_filtered, self.ax_metrics]:
            ax.clear()
            ax.text(0.5, 0.5, 'Load CSV data to begin analysis',
                   ha='center', va='center', transform=ax.transAxes,
                   fontsize=10, color='gray')
            ax.set_xticks([])
            ax.set_yticks([])

        self.canvas.draw()

    def load_and_process(self):
        """Load CSV file and process data"""
        # File dialog
        filepath = filedialog.askopenfilename(
            title="Select Tremor Data CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not filepath:
            return

        self.csv_path = filepath
        self.lbl_file.config(text=f"File: {filepath.split('/')[-1]}")
        self.lbl_status.config(text="Processing...", foreground="blue")
        self.root.update()

        try:
            # Load data
            self.data = self.load_csv_data(filepath)

            # Process and visualize
            self.process_tremor_analysis()

            self.lbl_status.config(text="✅ Analysis Complete", foreground="green")

            # Enable interactive cursors
            mplcursors.cursor(hover=True)

        except Exception as e:
            messagebox.showerror("Error", f"Processing failed:\n{str(e)}")
            self.lbl_status.config(text="❌ Error", foreground="red")
            import traceback
            traceback.print_exc()

    def load_csv_data(self, filepath):
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

    def process_tremor_analysis(self):
        """Main tremor analysis pipeline - Research-based approach"""

        # Extract data
        ax = self.data['Ax']
        ay = self.data['Ay']
        az = self.data['Az']
        gx = self.data['Gx']
        gy = self.data['Gy']
        gz = self.data['Gz']
        t = self.data['Timestamp'] / 1000.0  # Convert to seconds

        # Remove DC offset per axis (gravity removal)
        ax_clean = ax - np.mean(ax)
        ay_clean = ay - np.mean(ay)
        az_clean = az - np.mean(az)
        gx_clean = gx - np.mean(gx)
        gy_clean = gy - np.mean(gy)
        gz_clean = gz - np.mean(gz)

        # Calculate resultant vectors (magnitude)
        accel_mag = np.sqrt(ax_clean**2 + ay_clean**2 + az_clean**2)
        gyro_mag = np.sqrt(gx_clean**2 + gy_clean**2 + gz_clean**2)

        # Create filters
        nyquist = 0.5 * FS

        # Combined tremor filter (3-12 Hz) - main filter
        b_tremor, a_tremor = butter(FILTER_ORDER,
                                    [FREQ_TREMOR_LOW/nyquist, FREQ_TREMOR_HIGH/nyquist],
                                    btype='band')

        # Rest tremor filter (3-7 Hz) - Paper 1 recommendation
        b_rest, a_rest = butter(FILTER_ORDER,
                                [FREQ_REST_LOW/nyquist, FREQ_REST_HIGH/nyquist],
                                btype='band')

        # Essential tremor filter (6-12 Hz)
        b_ess, a_ess = butter(FILTER_ORDER,
                              [FREQ_ESSENTIAL_LOW/nyquist, FREQ_ESSENTIAL_HIGH/nyquist],
                              btype='band')

        # Apply filters to accelerometer
        accel_filtered = filtfilt(b_tremor, a_tremor, accel_mag)
        accel_rest = filtfilt(b_rest, a_rest, accel_mag)
        accel_ess = filtfilt(b_ess, a_ess, accel_mag)

        # Apply filters to gyroscope
        gyro_filtered = filtfilt(b_tremor, a_tremor, gyro_mag)

        # Calculate PSDs
        nperseg = min(len(accel_mag), int(FS * WINDOW_SEC))
        noverlap = int(nperseg * PSD_OVERLAP)

        f_accel, psd_accel_raw = welch(accel_mag, FS, nperseg=nperseg, noverlap=noverlap)
        _, psd_accel_filt = welch(accel_filtered, FS, nperseg=nperseg, noverlap=noverlap)
        f_gyro, psd_gyro_raw = welch(gyro_mag, FS, nperseg=nperseg, noverlap=noverlap)

        # Calculate metrics (Paper 1 features)
        metrics = self.calculate_metrics(
            accel_mag, accel_filtered, accel_rest, accel_ess,
            gyro_mag, gyro_filtered,
            f_accel, psd_accel_raw
        )

        # Visualize everything
        self.plot_research_analysis(
            t, accel_mag, accel_filtered, accel_rest, accel_ess,
            gyro_mag, gyro_filtered,
            f_accel, psd_accel_raw, psd_accel_filt,
            f_gyro, psd_gyro_raw,
            b_tremor, a_tremor, b_rest, a_rest, b_ess, a_ess,
            metrics
        )

    def calculate_metrics(self, accel_raw, accel_filt, accel_rest, accel_ess,
                          gyro_raw, gyro_filt, freq, psd):
        """Calculate tremor metrics per Paper 1"""
        metrics = {}

        # Paper 1 Features - Accelerometer
        metrics['accel_mean'] = np.mean(accel_filt)  # Mean linear acceleration
        metrics['accel_rms'] = np.sqrt(np.mean(accel_filt**2))  # RMS
        metrics['accel_max'] = np.max(np.abs(accel_filt))  # Maximal amplitude

        # Band-specific RMS
        metrics['rest_rms'] = np.sqrt(np.mean(accel_rest**2))
        metrics['ess_rms'] = np.sqrt(np.mean(accel_ess**2))

        # Power in 3-7 Hz band (Paper 1 metric)
        rest_mask = (freq >= FREQ_REST_LOW) & (freq <= FREQ_REST_HIGH)
        ess_mask = (freq >= FREQ_ESSENTIAL_LOW) & (freq <= FREQ_ESSENTIAL_HIGH)

        metrics['power_rest'] = np.sum(psd[rest_mask])
        metrics['power_ess'] = np.sum(psd[ess_mask])

        # Paper 1 Features - Gyroscope
        metrics['gyro_mean'] = np.mean(gyro_filt)  # Mean angular velocity
        metrics['gyro_rms'] = np.sqrt(np.mean(gyro_filt**2))
        metrics['gyro_max'] = np.max(np.abs(gyro_filt))

        # Dominant frequency
        tremor_mask = (freq >= 3) & (freq <= 12)
        if np.sum(tremor_mask) > 0:
            peak_idx = np.argmax(psd[tremor_mask])
            metrics['dominant_freq'] = freq[tremor_mask][peak_idx]
            metrics['peak_power'] = psd[tremor_mask][peak_idx]
        else:
            metrics['dominant_freq'] = 0
            metrics['peak_power'] = 0

        # Classification (maintains both tremor types)
        power_ratio = metrics['power_rest'] / (metrics['power_ess'] + 1e-10)

        if metrics['power_rest'] < TREMOR_POWER_THRESHOLD and \
           metrics['power_ess'] < TREMOR_POWER_THRESHOLD:
            metrics['tremor_type'] = "No significant tremor"
            metrics['confidence'] = "N/A"
            metrics['color'] = 'gray'
        elif power_ratio > CLASSIFICATION_RATIO:
            metrics['tremor_type'] = "Rest Tremor (Parkinsonian)"
            metrics['confidence'] = f"High (ratio: {power_ratio:.2f})"
            metrics['color'] = COL_REST
        elif power_ratio < 1/CLASSIFICATION_RATIO:
            metrics['tremor_type'] = "Essential Tremor (Postural)"
            metrics['confidence'] = f"High (ratio: {power_ratio:.2f})"
            metrics['color'] = COL_ESSENTIAL
        else:
            metrics['tremor_type'] = "Mixed Tremor"
            metrics['confidence'] = f"Moderate (ratio: {power_ratio:.2f})"
            metrics['color'] = COL_REST

        # Update UI
        self.lbl_tremor_type.config(text=f"Type: {metrics['tremor_type']}",
                                   foreground=metrics['color'])
        self.lbl_confidence.config(text=f"Confidence: {metrics['confidence']}")

        return metrics

    def plot_research_analysis(self, t, accel_raw, accel_filt, accel_rest, accel_ess,
                               gyro_raw, gyro_filt,
                               f_accel, psd_accel_raw, psd_accel_filt,
                               f_gyro, psd_gyro_raw,
                               b_tremor, a_tremor, b_rest, a_rest, b_ess, a_ess,
                               metrics):
        """Plot research-based analysis"""

        # ============================================================
        # ROW 1: FILTER VERIFICATION (Bode Plots)
        # ============================================================

        # Bode Magnitude
        self.ax_bode_mag.clear()
        w, h_tremor = freqz(b_tremor, a_tremor, worN=4096, fs=FS)
        _, h_rest = freqz(b_rest, a_rest, worN=4096, fs=FS)
        _, h_ess = freqz(b_ess, a_ess, worN=4096, fs=FS)

        self.ax_bode_mag.plot(w, 20*np.log10(abs(h_tremor)), color='purple',
                             linewidth=2, label='Combined (3-12 Hz)')
        self.ax_bode_mag.plot(w, 20*np.log10(abs(h_rest)), color=COL_REST,
                             linewidth=1.5, linestyle='--', label='Rest (3-7 Hz)')
        self.ax_bode_mag.plot(w, 20*np.log10(abs(h_ess)), color=COL_ESSENTIAL,
                             linewidth=1.5, linestyle='--', label='Essential (6-12 Hz)')

        self.ax_bode_mag.axvline(FREQ_REST_LOW, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_mag.axvline(FREQ_REST_HIGH, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_mag.axvline(FREQ_ESSENTIAL_HIGH, color='blue', linestyle=':', alpha=0.5)

        self.ax_bode_mag.set_title('Filter Magnitude Response (Butterworth Order 4)', fontweight='bold')
        self.ax_bode_mag.set_xlabel('Frequency (Hz)')
        self.ax_bode_mag.set_ylabel('Magnitude (dB)')
        self.ax_bode_mag.set_xlim(0, 20)
        self.ax_bode_mag.set_ylim(-60, 5)
        self.ax_bode_mag.grid(True, alpha=0.3)
        self.ax_bode_mag.legend(fontsize=8)

        # Bode Phase
        self.ax_bode_phase.clear()
        self.ax_bode_phase.plot(w, np.unwrap(np.angle(h_tremor)) * 180/np.pi,
                               color='purple', linewidth=2, label='Combined')
        self.ax_bode_phase.plot(w, np.unwrap(np.angle(h_rest)) * 180/np.pi,
                               color=COL_REST, linewidth=1.5, linestyle='--', label='Rest')

        self.ax_bode_phase.axvline(FREQ_REST_LOW, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_phase.axvline(FREQ_REST_HIGH, color='red', linestyle=':', alpha=0.5)

        self.ax_bode_phase.set_title('Filter Phase Response', fontweight='bold')
        self.ax_bode_phase.set_xlabel('Frequency (Hz)')
        self.ax_bode_phase.set_ylabel('Phase (degrees)')
        self.ax_bode_phase.set_xlim(0, 20)
        self.ax_bode_phase.grid(True, alpha=0.3)
        self.ax_bode_phase.legend(fontsize=8)

        # Filter comparison
        self.ax_filter_comparison.clear()
        self.ax_filter_comparison.plot(w, 20*np.log10(abs(h_rest)), color=COL_REST,
                                      linewidth=2, label='Rest (3-7 Hz)')
        self.ax_filter_comparison.plot(w, 20*np.log10(abs(h_ess)), color=COL_ESSENTIAL,
                                      linewidth=2, label='Essential (6-12 Hz)')
        self.ax_filter_comparison.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH,
                                         color=COL_REST, alpha=0.2)
        self.ax_filter_comparison.axvspan(FREQ_ESSENTIAL_LOW, FREQ_ESSENTIAL_HIGH,
                                         color=COL_ESSENTIAL, alpha=0.2)

        self.ax_filter_comparison.set_title('Rest vs Essential Tremor Filters', fontweight='bold')
        self.ax_filter_comparison.set_xlabel('Frequency (Hz)')
        self.ax_filter_comparison.set_ylabel('Magnitude (dB)')
        self.ax_filter_comparison.set_xlim(0, 15)
        self.ax_filter_comparison.set_ylim(-60, 5)
        self.ax_filter_comparison.grid(True, alpha=0.3)
        self.ax_filter_comparison.legend(fontsize=8)

        # ============================================================
        # ROW 2: ACCELEROMETER (Resultant Vector)
        # ============================================================

        # Raw signal
        self.ax_accel_raw.clear()
        self.ax_accel_raw.plot(t, accel_raw, color=COL_RAW, linewidth=0.8, alpha=0.7)
        self.ax_accel_raw.set_title(f'Accelerometer Resultant (Raw) | RMS: {np.sqrt(np.mean(accel_raw**2)):.4f} m/s²',
                                   fontweight='bold')
        self.ax_accel_raw.set_ylabel('Magnitude (m/s²)')
        self.ax_accel_raw.grid(True, alpha=0.3)
        self.ax_accel_raw.margins(x=0)

        # Filtered signal
        self.ax_accel_filtered.clear()
        self.ax_accel_filtered.plot(t, accel_filt, color=COL_FILTERED, linewidth=1.2)

        # Add envelope
        envelope = np.abs(hilbert(accel_filt))
        self.ax_accel_filtered.plot(t, envelope, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)
        self.ax_accel_filtered.plot(t, -envelope, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)

        self.ax_accel_filtered.set_title(f'Filtered (3-12 Hz) | RMS: {metrics["accel_rms"]:.4f} m/s²',
                                        fontweight='bold')
        self.ax_accel_filtered.set_ylabel('Filtered (m/s²)')
        self.ax_accel_filtered.grid(True, alpha=0.3)
        self.ax_accel_filtered.margins(x=0)

        # Overlay comparison
        self.ax_accel_overlay.clear()
        self.ax_accel_overlay.plot(t, accel_raw, color=COL_RAW, linewidth=1,
                                  alpha=0.5, label='Raw')
        self.ax_accel_overlay.plot(t, accel_filt, color=COL_FILTERED, linewidth=1.5,
                                  label='Filtered (3-12 Hz)')

        self.ax_accel_overlay.set_title('Raw vs Filtered Comparison', fontweight='bold')
        self.ax_accel_overlay.set_ylabel('Accel (m/s²)')
        self.ax_accel_overlay.grid(True, alpha=0.3)
        self.ax_accel_overlay.margins(x=0)
        self.ax_accel_overlay.legend(fontsize=8)

        # ============================================================
        # ROW 3: FREQUENCY ANALYSIS
        # ============================================================

        # PSD
        self.ax_accel_psd.clear()
        psd_raw_db = 10*np.log10(psd_accel_raw + 1e-12)
        psd_filt_db = 10*np.log10(psd_accel_filt + 1e-12)

        self.ax_accel_psd.plot(f_accel, psd_raw_db, color=COL_RAW,
                              linewidth=1, alpha=0.6, label='Raw')
        self.ax_accel_psd.plot(f_accel, psd_filt_db, color=COL_FILTERED,
                              linewidth=1.5, label='Filtered')

        self.ax_accel_psd.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH,
                                 color=COL_REST, alpha=0.2, label='Rest (3-7 Hz)')
        self.ax_accel_psd.axvspan(FREQ_ESSENTIAL_LOW, FREQ_ESSENTIAL_HIGH,
                                 color=COL_ESSENTIAL, alpha=0.2, label='Essential (6-12 Hz)')

        # Mark dominant frequency
        if metrics['dominant_freq'] > 0:
            dom_psd_db = 10*np.log10(metrics['peak_power'] + 1e-12)
            self.ax_accel_psd.plot(metrics['dominant_freq'], dom_psd_db, 'o',
                                  color='red', markersize=8,
                                  label=f"Peak: {metrics['dominant_freq']:.2f} Hz")

        self.ax_accel_psd.set_title('Power Spectral Density (Accelerometer)', fontweight='bold')
        self.ax_accel_psd.set_xlabel('Frequency (Hz)')
        self.ax_accel_psd.set_ylabel('Power (dB)')
        self.ax_accel_psd.set_xlim(0, 20)
        self.ax_accel_psd.grid(True, alpha=0.3)
        self.ax_accel_psd.legend(fontsize=7)

        # Band power comparison
        self.ax_accel_bands.clear()
        bands = ['Rest\n(3-7 Hz)', 'Essential\n(6-12 Hz)']
        powers = [metrics['power_rest'], metrics['power_ess']]
        colors = [COL_REST, COL_ESSENTIAL]

        bars = self.ax_accel_bands.bar(bands, powers, color=colors, alpha=0.7, edgecolor='black')

        # Add value labels on bars
        for bar, power in zip(bars, powers):
            height = bar.get_height()
            self.ax_accel_bands.text(bar.get_x() + bar.get_width()/2., height,
                                    f'{power:.4f}',
                                    ha='center', va='bottom', fontsize=9)

        self.ax_accel_bands.set_title('Tremor Band Power Comparison', fontweight='bold')
        self.ax_accel_bands.set_ylabel('Power')
        self.ax_accel_bands.grid(True, alpha=0.3, axis='y')

        # Spectrogram
        self.ax_spectrogram.clear()
        nperseg_spec = int(FS * 2)
        noverlap_spec = int(nperseg_spec * 0.9)

        self.ax_spectrogram.specgram(accel_filt[:int(30*FS)], Fs=FS,
                                    NFFT=nperseg_spec, noverlap=noverlap_spec,
                                    cmap='jet')

        self.ax_spectrogram.set_title('Spectrogram (First 30s)', fontweight='bold')
        self.ax_spectrogram.set_ylabel('Frequency (Hz)')
        self.ax_spectrogram.set_xlabel('Time (s)')
        self.ax_spectrogram.set_ylim(0, 15)

        # ============================================================
        # ROW 4: GYROSCOPE + METRICS
        # ============================================================

        # Gyro raw
        self.ax_gyro_raw.clear()
        self.ax_gyro_raw.plot(t, gyro_raw, color=COL_GYRO, linewidth=0.8, alpha=0.7)
        self.ax_gyro_raw.set_title(f'Gyroscope Resultant (Raw) | RMS: {np.sqrt(np.mean(gyro_raw**2)):.2f} °/s',
                                  fontweight='bold')
        self.ax_gyro_raw.set_ylabel('Angular Vel (°/s)')
        self.ax_gyro_raw.set_xlabel('Time (s)')
        self.ax_gyro_raw.grid(True, alpha=0.3)
        self.ax_gyro_raw.margins(x=0)

        # Gyro filtered
        self.ax_gyro_filtered.clear()
        self.ax_gyro_filtered.plot(t, gyro_filt, color=COL_GYRO, linewidth=1.2)

        envelope_gyro = np.abs(hilbert(gyro_filt))
        self.ax_gyro_filtered.plot(t, envelope_gyro, '--', color=COL_GYRO, alpha=0.4, linewidth=0.8)
        self.ax_gyro_filtered.plot(t, -envelope_gyro, '--', color=COL_GYRO, alpha=0.4, linewidth=0.8)

        self.ax_gyro_filtered.set_title(f'Gyro Filtered (3-12 Hz) | RMS: {metrics["gyro_rms"]:.2f} °/s ⚠️ May include motor',
                                       fontweight='bold', fontsize=9)
        self.ax_gyro_filtered.set_ylabel('Filtered (°/s)')
        self.ax_gyro_filtered.set_xlabel('Time (s)')
        self.ax_gyro_filtered.grid(True, alpha=0.3)
        self.ax_gyro_filtered.margins(x=0)

        # Metrics table
        self.ax_metrics.clear()
        self.ax_metrics.axis('off')

        metrics_text = f"""
TREMOR CLASSIFICATION
{'─'*40}
Type: {metrics['tremor_type']}
Confidence: {metrics['confidence']}

ACCELEROMETER FEATURES (Paper 1)
{'─'*40}
Mean Amplitude:       {metrics['accel_mean']:.4f} m/s²
RMS:                  {metrics['accel_rms']:.4f} m/s²
Max Amplitude:        {metrics['accel_max']:.4f} m/s²

TREMOR BAND ANALYSIS
{'─'*40}
Rest (3-7 Hz):
  RMS:                {metrics['rest_rms']:.4f} m/s²
  Power:              {metrics['power_rest']:.6f}

Essential (6-12 Hz):
  RMS:                {metrics['ess_rms']:.4f} m/s²
  Power:              {metrics['power_ess']:.6f}

Power Ratio:          {metrics['power_rest']/metrics['power_ess']:.2f}

GYROSCOPE FEATURES (⚠️  Motor artifact)
{'─'*40}
Mean Angular Vel:     {metrics['gyro_mean']:.2f} °/s
RMS:                  {metrics['gyro_rms']:.2f} °/s
Max:                  {metrics['gyro_max']:.2f} °/s

FREQUENCY
{'─'*40}
Dominant Frequency:   {metrics['dominant_freq']:.2f} Hz
Peak Power:           {metrics['peak_power']:.6f}
"""

        self.ax_metrics.text(0.05, 0.95, metrics_text,
                            transform=self.ax_metrics.transAxes,
                            fontfamily='monospace', fontsize=8,
                            verticalalignment='top')

        self.ax_metrics.set_title('Clinical Metrics (Research-Based)', fontweight='bold', loc='left')

        self.canvas.draw()

        # Print to console
        print("\n" + "="*70)
        print("TREMOR ANALYSIS RESULTS (Research-Based)")
        print("="*70)
        print(metrics_text)
        print("="*70 + "\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = TremorAnalyzerResearch(root)
    root.mainloop()
