#!/usr/bin/env python3
"""
Rest Tremor Analysis Tool - Research-Based Implementation
Focused on rest tremor (2-8 Hz) detection using resultant vector magnitude.
Bandpass filter: 2-8 Hz (avoids edge attenuation at 3 and 7 Hz).
Validation: user enters PWM frequency, system checks if PSD peak matches within +/-0.5 Hz.
Based on MDPI papers: Parkinson's tremor assessment with MPU6050 + ESP32
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
# CONFIGURATION PARAMETERS
# ==========================================
FS = 100.0              # Sampling rate (Hz)
FILTER_ORDER = 4        # Butterworth filter order (standard)

# Rest tremor bandpass filter (2-8 Hz)
# Extended from clinical 3-7 Hz to avoid -3dB attenuation at band edges
FREQ_TREMOR_LOW = 2.0   # Lower bound (below 3 Hz to preserve edge)
FREQ_TREMOR_HIGH = 8.0  # Upper bound (above 7 Hz to preserve edge)

# Rest tremor analysis band (matching filter band)
FREQ_REST_LOW = 2.0     # Rest tremor analysis lower bound (= filter low)
FREQ_REST_HIGH = 8.0    # Rest tremor analysis upper bound (= filter high)

# PSD parameters
WINDOW_SEC = 4          # Welch window size (seconds)
PSD_OVERLAP = 0.5       # 50% overlap

# Validation tolerance
FREQ_TOLERANCE_HZ = 0.5 # Acceptable deviation from expected frequency

# Visual styling
COL_RAW = '#2F4F4F'         # Dark Slate Gray - Raw signal
COL_FILTERED = '#FF6347'    # Tomato - Filtered signal
COL_PASS = '#2ECC71'        # Green - Validation pass
COL_FAIL = '#E74C3C'        # Red - Validation fail

class TremorAnalyzerResearch:
    def __init__(self, root):
        self.root = root
        self.root.title("Rest Tremor Analyzer - Input/Output Validation (2-8 Hz)")
        self.root.geometry("1600x1000")

        # Data storage
        self.csv_path = None
        self.data = None

        # PWM frequency (from motor input)
        self.pwm_freq = None

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

        ttk.Button(control_frame, text="Load CSV Data",
                   command=self.load_and_process).pack(side=tk.LEFT, padx=10)

        self.lbl_file = ttk.Label(control_frame, text="No file loaded",
                                  font=("Arial", 9), foreground="gray")
        self.lbl_file.pack(side=tk.LEFT, padx=10)

        self.lbl_status = ttk.Label(control_frame, text="Ready",
                                    font=("Arial", 10, "bold"))
        self.lbl_status.pack(side=tk.LEFT, padx=20)

        # PWM frequency input (from motor)
        freq_frame = ttk.LabelFrame(control_frame, text="PWM Frequency (Motor Input)",
                                    padding="5")
        freq_frame.pack(side=tk.RIGHT, padx=10)

        ttk.Label(freq_frame, text="PWM Freq (Hz):").pack(side=tk.LEFT)
        self.entry_pwm_freq = ttk.Entry(freq_frame, width=8)
        self.entry_pwm_freq.pack(side=tk.LEFT, padx=2)
        self.entry_pwm_freq.insert(0, "5.0")

        # Validation result panel
        self.result_frame = ttk.LabelFrame(control_frame, text="Validation Result",
                                           padding="5")
        self.result_frame.pack(side=tk.RIGHT, padx=10)

        self.lbl_measured_freq = ttk.Label(self.result_frame, text="Measured: N/A",
                                           font=("Arial", 10))
        self.lbl_measured_freq.pack()

        self.lbl_validation = ttk.Label(self.result_frame, text="Status: N/A",
                                        font=("Arial", 11, "bold"))
        self.lbl_validation.pack()

    def create_analysis_dashboard(self):
        """Create research-based analysis dashboard - MATLAB style separate figures"""
        # Main container with notebook for separate figures
        main_frame = ttk.Frame(self.root)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create notebook (tabbed interface) for MATLAB-style figures
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Store figures, canvases, and axes
        self.figures = []
        self.canvases = []
        self.all_axes = []

        # ==================== FIGURE 1: FILTER CHARACTERISTICS ====================
        fig1_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig1_frame, text="Figure 1 - Filters")

        self.fig1 = plt.figure(figsize=(15, 4))
        gs1 = GridSpec(1, 2, figure=self.fig1, hspace=0.3, wspace=0.3)

        self.ax_bode_mag = self.fig1.add_subplot(gs1[0, 0])
        self.ax_bode_phase = self.fig1.add_subplot(gs1[0, 1])

        canvas1 = FigureCanvasTkAgg(self.fig1, master=fig1_frame)
        canvas1.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar1 = NavigationToolbar2Tk(canvas1, fig1_frame)
        toolbar1.update()

        self.figures.append(self.fig1)
        self.canvases.append(canvas1)
        self.all_axes.extend([self.ax_bode_mag, self.ax_bode_phase])

        # ==================== FIGURE 2: RESULTANT VECTOR ANALYSIS ====================
        fig2_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig2_frame, text="Figure 2 - Resultant Vector")

        self.fig2 = plt.figure(figsize=(15, 4))
        gs2 = GridSpec(1, 3, figure=self.fig2, hspace=0.3, wspace=0.3)

        self.ax_result_raw = self.fig2.add_subplot(gs2[0, 0])
        self.ax_result_filtered = self.fig2.add_subplot(gs2[0, 1])
        self.ax_result_overlay = self.fig2.add_subplot(gs2[0, 2])

        canvas2 = FigureCanvasTkAgg(self.fig2, master=fig2_frame)
        canvas2.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar2 = NavigationToolbar2Tk(canvas2, fig2_frame)
        toolbar2.update()

        self.figures.append(self.fig2)
        self.canvases.append(canvas2)
        self.all_axes.extend([self.ax_result_raw, self.ax_result_filtered, self.ax_result_overlay])

        # ==================== FIGURE 3: PSD ANALYSIS ====================
        fig3_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig3_frame, text="Figure 3 - PSD Analysis")

        self.fig3 = plt.figure(figsize=(15, 4))
        gs3 = GridSpec(1, 3, figure=self.fig3, hspace=0.3, wspace=0.3)

        self.ax_psd_full = self.fig3.add_subplot(gs3[0, 0])
        self.ax_psd_zoom = self.fig3.add_subplot(gs3[0, 1])
        self.ax_metrics = self.fig3.add_subplot(gs3[0, 2])

        canvas3 = FigureCanvasTkAgg(self.fig3, master=fig3_frame)
        canvas3.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar3 = NavigationToolbar2Tk(canvas3, fig3_frame)
        toolbar3.update()

        self.figures.append(self.fig3)
        self.canvases.append(canvas3)
        self.all_axes.extend([self.ax_psd_full, self.ax_psd_zoom, self.ax_metrics])

        # Initialize plots
        self.clear_all_plots()

    def clear_all_plots(self):
        """Clear all plots and show instructions"""
        for ax in self.all_axes:
            ax.clear()
            ax.text(0.5, 0.5, 'Load CSV data to begin analysis',
                   ha='center', va='center', transform=ax.transAxes,
                   fontsize=10, color='gray')
            ax.set_xticks([])
            ax.set_yticks([])

        # Draw all canvases
        for canvas in self.canvases:
            canvas.draw()

    def load_and_process(self):
        """Load CSV file and process data"""
        # Get PWM frequency from input field
        try:
            self.pwm_freq = float(self.entry_pwm_freq.get())
            if self.pwm_freq <= 0:
                messagebox.showerror("Error", "PWM frequency must be positive")
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid PWM frequency. Please enter a number.")
            return

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

            self.lbl_status.config(text="Analysis Complete", foreground="green")

            # Enable interactive cursors
            mplcursors.cursor(hover=True)

        except Exception as e:
            messagebox.showerror("Error", f"Processing failed:\n{str(e)}")
            self.lbl_status.config(text="Error", foreground="red")
            import traceback
            traceback.print_exc()

    def load_csv_data(self, filepath):
        """Load CSV data from file"""
        data = {'Timestamp': [], 'Ax': [], 'Ay': [], 'Az': []}

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
                    if len(parts) >= 4:  # Only need timestamp + Ax, Ay, Az
                        data['Timestamp'].append(int(parts[0]))
                        data['Ax'].append(float(parts[1]))
                        data['Ay'].append(float(parts[2]))
                        data['Az'].append(float(parts[3]))
                except (ValueError, IndexError):
                    continue

        # Convert to numpy arrays
        for key in data:
            data[key] = np.array(data[key])

        return data

    def process_tremor_analysis(self):
        """Main tremor analysis pipeline - Resultant vector only"""

        # Extract data
        ax = self.data['Ax']
        ay = self.data['Ay']
        az = self.data['Az']
        t = self.data['Timestamp'] / 1000.0  # Convert to seconds

        # Remove DC offset per axis (gravity removal)
        ax_clean = ax - np.mean(ax)
        ay_clean = ay - np.mean(ay)
        az_clean = az - np.mean(az)

        # Calculate resultant vector (magnitude)
        accel_mag = np.sqrt(ax_clean**2 + ay_clean**2 + az_clean**2)

        # Create single tremor filter (2-8 Hz)
        nyquist = 0.5 * FS
        b_tremor, a_tremor = butter(FILTER_ORDER,
                                    [FREQ_TREMOR_LOW/nyquist, FREQ_TREMOR_HIGH/nyquist],
                                    btype='band')

        # Apply filter to resultant vector
        result_filtered = filtfilt(b_tremor, a_tremor, accel_mag)

        # Calculate PSDs
        nperseg = min(len(accel_mag), int(FS * WINDOW_SEC))
        noverlap = int(nperseg * PSD_OVERLAP)

        # PSD for resultant (raw and filtered)
        f_psd, psd_raw = welch(accel_mag, FS, nperseg=nperseg, noverlap=noverlap)
        _, psd_filt = welch(result_filtered, FS, nperseg=nperseg, noverlap=noverlap)

        # Calculate metrics - peak detection on FILTERED PSD
        metrics = self.calculate_metrics(accel_mag, result_filtered, f_psd, psd_filt)

        # Visualize everything
        self.plot_analysis(
            t, accel_mag, result_filtered,
            f_psd, psd_raw, psd_filt,
            b_tremor, a_tremor, metrics
        )

    def calculate_metrics(self, accel_raw, accel_filt, freq, psd_filt):
        """Calculate tremor metrics and validate against PWM frequency.
        Peak detection uses the FILTERED PSD within 2-8 Hz band."""
        metrics = {}

        # Resultant vector features
        metrics['accel_rms'] = np.sqrt(np.mean(accel_filt**2))
        metrics['accel_mean'] = np.mean(np.abs(accel_filt))
        metrics['accel_max'] = np.max(np.abs(accel_filt))

        # Total power in rest tremor band (2-8 Hz) from filtered PSD
        rest_mask = (freq >= FREQ_REST_LOW) & (freq <= FREQ_REST_HIGH)
        metrics['total_power'] = np.trapz(psd_filt[rest_mask], freq[rest_mask])

        # Dominant frequency and peak spectral density (within 2-8 Hz on filtered PSD)
        if np.sum(rest_mask) > 0:
            peak_idx = np.argmax(psd_filt[rest_mask])
            metrics['dominant_freq'] = freq[rest_mask][peak_idx]
            metrics['peak_power_density'] = psd_filt[rest_mask][peak_idx]
        else:
            metrics['dominant_freq'] = 0
            metrics['peak_power_density'] = 0

        # Input-Output Validation: |PSD_peak - PWM_freq| <= 2 * freq_resolution (0.5 Hz)
        measured_freq = metrics['dominant_freq']
        pwm_freq = self.pwm_freq
        deviation = abs(measured_freq - pwm_freq)

        if deviation <= FREQ_TOLERANCE_HZ:
            metrics['validation_status'] = "PASS"
            metrics['validation_color'] = COL_PASS
        else:
            metrics['validation_status'] = "FAIL"
            metrics['validation_color'] = COL_FAIL

        metrics['deviation'] = deviation
        metrics['pwm_freq'] = pwm_freq

        # Update UI
        self.lbl_measured_freq.config(text=f"Measured: {measured_freq:.2f} Hz")
        self.lbl_validation.config(
            text=f"Status: {metrics['validation_status']}",
            foreground=metrics['validation_color']
        )

        return metrics

    def plot_analysis(self, t, result_raw, result_filt,
                     f_psd, psd_raw, psd_filt,
                     b_tremor, a_tremor, metrics):
        """Plot complete analysis - resultant vector only"""

        # ============================================================
        # FIGURE 1: FILTER CHARACTERISTICS
        # ============================================================

        # Bode Magnitude - Show both single-pass and filtfilt (double attenuation)
        self.ax_bode_mag.clear()
        w, h = freqz(b_tremor, a_tremor, worN=4096, fs=FS)
        mag_single = 20*np.log10(abs(h))
        mag_filtfilt = 2 * mag_single  # filtfilt = forward + backward = 2x in dB

        # Single-pass (for reference)
        self.ax_bode_mag.plot(w, mag_single, color='gray', linewidth=1.5,
                             linestyle='--', alpha=0.6, label='Single-pass (O4)')

        # filtfilt = equivalent to Order 8 (double attenuation)
        self.ax_bode_mag.plot(w, mag_filtfilt, color='purple', linewidth=2,
                             label='filtfilt (effective O8)')

        self.ax_bode_mag.axvline(FREQ_TREMOR_LOW, color='red', linestyle=':', alpha=0.5, label=f'{FREQ_TREMOR_LOW} Hz')
        self.ax_bode_mag.axvline(FREQ_TREMOR_HIGH, color='blue', linestyle=':', alpha=0.5, label=f'{FREQ_TREMOR_HIGH} Hz')
        self.ax_bode_mag.axhline(-3, color='green', linestyle='--', alpha=0.5, label='-3 dB')
        self.ax_bode_mag.axhline(-6, color='orange', linestyle='--', alpha=0.5, label='-6 dB (filtfilt)')

        self.ax_bode_mag.set_title('Fig 1.1 - Magnitude: filtfilt doubles attenuation', fontweight='bold')
        self.ax_bode_mag.set_xlabel('Frequency (Hz)')
        self.ax_bode_mag.set_ylabel('Magnitude (dB)')
        self.ax_bode_mag.set_xlim(0, 20)
        self.ax_bode_mag.set_ylim(-60, 5)
        self.ax_bode_mag.grid(True, alpha=0.3)
        self.ax_bode_mag.legend(fontsize=7, loc='lower left')

        # Bode Phase - Show both single-pass and filtfilt (zero-phase)
        self.ax_bode_phase.clear()
        single_pass_phase = np.unwrap(np.angle(h)) * 180/np.pi

        # Single-pass phase (theoretical - for reference)
        self.ax_bode_phase.plot(w, single_pass_phase,
                               color='gray', linewidth=1.5, linestyle='--', alpha=0.6,
                               label='Single-pass (lfilter)')

        # Zero-phase line (filtfilt result)
        self.ax_bode_phase.axhline(0, color='green', linewidth=2.5,
                                   label='Zero-phase (filtfilt) ✓')

        self.ax_bode_phase.axvline(FREQ_TREMOR_LOW, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_phase.axvline(FREQ_TREMOR_HIGH, color='blue', linestyle=':', alpha=0.5)

        self.ax_bode_phase.set_title('Fig 1.2 - Phase Response: filtfilt = Zero Phase', fontweight='bold')
        self.ax_bode_phase.set_xlabel('Frequency (Hz)')
        self.ax_bode_phase.set_ylabel('Phase (degrees)')
        self.ax_bode_phase.set_xlim(0, 20)
        self.ax_bode_phase.set_ylim(-800, 100)
        self.ax_bode_phase.legend(loc='lower left', fontsize=8)
        self.ax_bode_phase.grid(True, alpha=0.3)

        # ============================================================
        # FIGURE 2: RESULTANT VECTOR ANALYSIS
        # ============================================================

        # Raw resultant
        self.ax_result_raw.clear()
        self.ax_result_raw.plot(t, result_raw, color=COL_RAW, linewidth=0.8, alpha=0.7)
        self.ax_result_raw.set_title(f'Fig 2.1 - Resultant Vector Raw | RMS: {np.sqrt(np.mean(result_raw**2)):.4f} m/s^2',
                                    fontweight='bold')
        self.ax_result_raw.set_ylabel('Magnitude (m/s^2)')
        self.ax_result_raw.set_xlabel('Time (s)')
        self.ax_result_raw.grid(True, alpha=0.3)
        self.ax_result_raw.margins(x=0)

        # Filtered resultant
        self.ax_result_filtered.clear()
        self.ax_result_filtered.plot(t, result_filt, color=COL_FILTERED, linewidth=1.2)

        # Add envelope
        envelope_result = np.abs(hilbert(result_filt))
        self.ax_result_filtered.plot(t, envelope_result, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)
        self.ax_result_filtered.plot(t, -envelope_result, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)

        self.ax_result_filtered.set_title(f'Fig 2.2 - Resultant Filtered (2-8 Hz) | RMS: {metrics["accel_rms"]:.4f} m/s^2',
                                         fontweight='bold')
        self.ax_result_filtered.set_ylabel('Magnitude (m/s^2)')
        self.ax_result_filtered.set_xlabel('Time (s)')
        self.ax_result_filtered.grid(True, alpha=0.3)
        self.ax_result_filtered.margins(x=0)

        # Overlay comparison
        self.ax_result_overlay.clear()
        self.ax_result_overlay.plot(t, result_raw, color=COL_RAW, linewidth=1,
                                   alpha=0.5, label='Raw')
        self.ax_result_overlay.plot(t, result_filt, color=COL_FILTERED, linewidth=1.5,
                                   label='Filtered (2-8 Hz)')

        self.ax_result_overlay.set_title('Fig 2.3 - Resultant: Raw vs Filtered', fontweight='bold')
        self.ax_result_overlay.set_ylabel('Magnitude (m/s^2)')
        self.ax_result_overlay.set_xlabel('Time (s)')
        self.ax_result_overlay.grid(True, alpha=0.3)
        self.ax_result_overlay.margins(x=0)
        self.ax_result_overlay.legend(fontsize=8)

        # ============================================================
        # FIGURE 3: PSD ANALYSIS
        # ============================================================

        expected_color = metrics['validation_color']

        # PSD full range (0-20 Hz)
        self.ax_psd_full.clear()
        psd_raw_db = 10*np.log10(psd_raw + 1e-12)
        psd_filt_db = 10*np.log10(psd_filt + 1e-12)

        self.ax_psd_full.plot(f_psd, psd_raw_db, color=COL_RAW,
                             linewidth=1, alpha=0.6, label='Raw')
        self.ax_psd_full.plot(f_psd, psd_filt_db, color=COL_FILTERED,
                             linewidth=1.5, label='Filtered')

        # Mark dominant frequency on FILTERED curve
        if metrics['dominant_freq'] > 0:
            peak_db = 10*np.log10(metrics['peak_power_density'] + 1e-12)
            self.ax_psd_full.plot(metrics['dominant_freq'], peak_db, 'o',
                                color='red', markersize=8,
                                label=f"Peak: {metrics['dominant_freq']:.2f} Hz")

        # Highlight analysis band (2-8 Hz)
        self.ax_psd_full.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH,
                                color='yellow', alpha=0.15, label='Analysis 2-8 Hz')

        self.ax_psd_full.set_title('Fig 3.1 - PSD: Resultant Vector (0-20 Hz)', fontweight='bold')
        self.ax_psd_full.set_xlabel('Frequency (Hz)')
        self.ax_psd_full.set_ylabel('Power (dB)')
        self.ax_psd_full.set_xlim(0, 20)
        self.ax_psd_full.grid(True, alpha=0.3)
        self.ax_psd_full.legend(fontsize=7)

        # PSD zoomed to tremor range (1-12 Hz)
        self.ax_psd_zoom.clear()

        self.ax_psd_zoom.plot(f_psd, psd_filt_db, color=COL_FILTERED,
                             linewidth=1.5, label='Filtered PSD')

        # Show PWM frequency and tolerance band (±0.5 Hz)
        pwm_freq = metrics['pwm_freq']
        self.ax_psd_zoom.axvline(pwm_freq, color='blue', linestyle='-', alpha=0.7,
                                linewidth=1.5, label=f'PWM Freq: {pwm_freq:.1f} Hz')
        self.ax_psd_zoom.axvspan(pwm_freq - FREQ_TOLERANCE_HZ, pwm_freq + FREQ_TOLERANCE_HZ,
                               color=expected_color, alpha=0.2,
                               label=f'Tolerance \u00b1{FREQ_TOLERANCE_HZ} Hz')

        # Highlight analysis band (2-8 Hz)
        self.ax_psd_zoom.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH,
                                color='yellow', alpha=0.1, label='Analysis 2-8 Hz')

        # Mark dominant frequency on FILTERED curve
        if metrics['dominant_freq'] > 0:
            peak_db = 10*np.log10(metrics['peak_power_density'] + 1e-12)
            self.ax_psd_zoom.plot(metrics['dominant_freq'], peak_db, 'o',
                                color='red', markersize=10,
                                label=f"Peak: {metrics['dominant_freq']:.2f} Hz")

        self.ax_psd_zoom.set_title('Fig 3.2 - PSD Zoomed: Filtered (1-12 Hz)', fontweight='bold')
        self.ax_psd_zoom.set_xlabel('Frequency (Hz)')
        self.ax_psd_zoom.set_ylabel('Power (dB)')
        self.ax_psd_zoom.set_xlim(1, 12)
        self.ax_psd_zoom.grid(True, alpha=0.3)
        self.ax_psd_zoom.legend(fontsize=7)

        # Metrics & Validation Table (new Fig 3.3)
        self.ax_metrics.clear()
        self.ax_metrics.axis('off')

        status_symbol = "V" if metrics['validation_status'] == "PASS" else "X"

        metrics_text = f"""INPUT-OUTPUT VALIDATION
{'='*40}
PWM Frequency:  {metrics['pwm_freq']:.2f} Hz
PSD Peak Freq:  {metrics['dominant_freq']:.2f} Hz
Deviation:      {metrics['deviation']:.2f} Hz
Tolerance:      +/-{FREQ_TOLERANCE_HZ:.2f} Hz (2 x 0.25 Hz)
Status:         [{status_symbol}] {metrics['validation_status']}

RESULTANT VECTOR METRICS
{'='*40}
RMS Amplitude:  {metrics['accel_rms']:.4f} m/s^2
Mean Amplitude: {metrics['accel_mean']:.4f} m/s^2
Max Amplitude:  {metrics['accel_max']:.4f} m/s^2

REST TREMOR ANALYSIS (2-8 Hz)
{'='*40}
Dominant Freq:  {metrics['dominant_freq']:.2f} Hz
Peak PSD:       {metrics['peak_power_density']:.6f} (m/s^2)^2/Hz
Band Power:     {metrics['total_power']:.6f} (m/s^2)^2
Filter:         2-8 Hz (Butterworth O4, filtfilt)
"""

        bg_color = metrics['validation_color']
        self.ax_metrics.text(0.05, 0.95, metrics_text,
                            transform=self.ax_metrics.transAxes,
                            fontfamily='monospace', fontsize=8,
                            verticalalignment='top',
                            bbox=dict(boxstyle='round,pad=0.5', facecolor=bg_color, alpha=0.15))
        self.ax_metrics.set_title('Fig 3.3 - Metrics & Validation', fontweight='bold', loc='left')

        # Draw all canvases
        for canvas in self.canvases:
            canvas.draw()

        # Print to console
        print("\n" + "="*70)
        print("INPUT-OUTPUT VALIDATION RESULTS")
        print("="*70)
        print(f"\nVALIDATION:")
        print(f"  PWM Frequency:  {metrics['pwm_freq']:.2f} Hz")
        print(f"  PSD Peak Freq:  {metrics['dominant_freq']:.2f} Hz")
        print(f"  Deviation:      {metrics['deviation']:.2f} Hz")
        print(f"  Tolerance:      +/-{FREQ_TOLERANCE_HZ:.2f} Hz (2 x 0.25 Hz)")
        print(f"  Status:         {metrics['validation_status']}")
        print(f"\nRESULTANT VECTOR METRICS:")
        print(f"  RMS Amplitude:  {metrics['accel_rms']:.4f} m/s^2")
        print(f"  Mean Amplitude: {metrics['accel_mean']:.4f} m/s^2")
        print(f"  Max Amplitude:  {metrics['accel_max']:.4f} m/s^2")
        print(f"\nREST TREMOR ANALYSIS (2-8 Hz):")
        print(f"  Filter:         2-8 Hz (Butterworth Order 4, filtfilt)")
        print(f"  Dominant Freq:  {metrics['dominant_freq']:.2f} Hz")
        print(f"  Peak PSD:       {metrics['peak_power_density']:.6f} (m/s^2)^2/Hz")
        print(f"  Band Power:     {metrics['total_power']:.6f} (m/s^2)^2")
        print("="*70 + "\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = TremorAnalyzerResearch(root)
    root.mainloop()
