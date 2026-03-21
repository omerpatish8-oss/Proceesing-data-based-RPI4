#!/usr/bin/env python3
"""
Rest Tremor Analysis Tool - EXPERIMENTAL Version
Based on offline_analyzer.py with the following changes:
  - No pass/fail criteria: frequency deviation and peak SNR are reported
    as informational metrics only (no PASS/FAIL judgment).
  - Peak SNR is calculated and Dominant Power Ratio (DPR) is derived from
    peak PSD vs total band power — shows how concentrated the energy is.
  - Fig 2: Raw and filtered resultant vector (2 broader plots, no overlay).
  - Fig 3.3: Enlarged metrics panel with larger font.
  - Fig 4: Zoomed filtered signal for a 5-second window (first half of a
    10-second block taken from the middle of the recording).
  - Fig 5: Zoomed filtered signal for the next consecutive 5-second window
    (second half of the same 10-second block, directly after Fig 4).
  - Fig 6: Single full-width FFT magnitude plot (1-12 Hz) over the full
    120-second recording.
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

# Validation tolerance (kept for deviation reporting, NOT for pass/fail)
FREQ_TOLERANCE_HZ = 0.5 # Deviation reference from expected frequency

# Visual styling
COL_RAW = '#2F4F4F'         # Dark Slate Gray - Raw signal
COL_FILTERED = '#FF6347'    # Tomato - Filtered signal
COL_INFO = '#3498DB'        # Blue - Informational (replaces pass/fail colors)

# Zoomed window duration for Fig 4 and Fig 5
ZOOM_DURATION_SEC = 5.0     # Each zoomed window is 5 seconds

# MPU6050 accelerometer sensor noise floor
# Datasheet: 400 µg/√Hz noise spectral density (at ±2g range)
MPU6050_NOISE_DENSITY = 400e-6 * 9.81   # Convert to m/s²/√Hz
MPU6050_NOISE_PSD = MPU6050_NOISE_DENSITY**2  # Per-axis PSD noise floor (m/s²)²/Hz


class TremorAnalyzerExperimental:
    def __init__(self, root):
        self.root = root
        self.root.title("Rest Tremor Analyzer - EXPERIMENTAL (No Pass/Fail)")
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

        # Info panel (replaces "Validation Result" - no pass/fail)
        self.result_frame = ttk.LabelFrame(control_frame, text="Measurement Info",
                                           padding="5")
        self.result_frame.pack(side=tk.RIGHT, padx=10)

        self.lbl_measured_freq = ttk.Label(self.result_frame, text="Measured: N/A",
                                           font=("Arial", 10))
        self.lbl_measured_freq.pack()

        self.lbl_validation = ttk.Label(self.result_frame, text="Deviation: N/A",
                                        font=("Arial", 11, "bold"))
        self.lbl_validation.pack()

    def create_analysis_dashboard(self):
        """Create research-based analysis dashboard - 6 figure tabs"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Storage for figures, canvases, axes
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

        # ==================== FIGURE 2: RESULTANT VECTOR ANALYSIS (2 broader plots) ====================
        fig2_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig2_frame, text="Figure 2 - Resultant Vector")

        self.fig2 = plt.figure(figsize=(15, 4))
        gs2 = GridSpec(1, 2, figure=self.fig2, hspace=0.3, wspace=0.3)

        self.ax_result_raw = self.fig2.add_subplot(gs2[0, 0])
        self.ax_result_filtered = self.fig2.add_subplot(gs2[0, 1])

        canvas2 = FigureCanvasTkAgg(self.fig2, master=fig2_frame)
        canvas2.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar2 = NavigationToolbar2Tk(canvas2, fig2_frame)
        toolbar2.update()

        self.figures.append(self.fig2)
        self.canvases.append(canvas2)
        self.all_axes.extend([self.ax_result_raw, self.ax_result_filtered])

        # ==================== FIGURE 3: PSD ANALYSIS ====================
        fig3_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig3_frame, text="Figure 3 - PSD Analysis")

        self.fig3 = plt.figure(figsize=(15, 5))
        # width_ratios: PSD full (2) | PSD zoom (2) | Metrics panel (3) — metrics gets more space
        gs3 = GridSpec(1, 3, figure=self.fig3, hspace=0.3, wspace=0.35,
                       width_ratios=[2, 2, 3])

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

        # ==================== FIGURE 4: ZOOMED FIRST 5s WINDOW ====================
        fig4_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig4_frame, text="Figure 4 - Zoomed 5s (A)")

        self.fig4 = plt.figure(figsize=(15, 4))
        gs4 = GridSpec(1, 2, figure=self.fig4, hspace=0.3, wspace=0.3)

        self.ax_zoom_a_filt = self.fig4.add_subplot(gs4[0, 0])
        self.ax_zoom_a_overlay = self.fig4.add_subplot(gs4[0, 1])

        canvas4 = FigureCanvasTkAgg(self.fig4, master=fig4_frame)
        canvas4.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar4 = NavigationToolbar2Tk(canvas4, fig4_frame)
        toolbar4.update()

        self.figures.append(self.fig4)
        self.canvases.append(canvas4)
        self.all_axes.extend([self.ax_zoom_a_filt, self.ax_zoom_a_overlay])

        # ==================== FIGURE 5: ZOOMED NEXT 5s WINDOW ====================
        fig5_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig5_frame, text="Figure 5 - Zoomed 5s (B)")

        self.fig5 = plt.figure(figsize=(15, 4))
        gs5 = GridSpec(1, 2, figure=self.fig5, hspace=0.3, wspace=0.3)

        self.ax_zoom_b_filt = self.fig5.add_subplot(gs5[0, 0])
        self.ax_zoom_b_overlay = self.fig5.add_subplot(gs5[0, 1])

        canvas5 = FigureCanvasTkAgg(self.fig5, master=fig5_frame)
        canvas5.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar5 = NavigationToolbar2Tk(canvas5, fig5_frame)
        toolbar5.update()

        self.figures.append(self.fig5)
        self.canvases.append(canvas5)
        self.all_axes.extend([self.ax_zoom_b_filt, self.ax_zoom_b_overlay])

        # ==================== FIGURE 6: FFT OVER FULL 120s (single full-width plot) ====================
        fig6_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig6_frame, text="Figure 6 - FFT (Full 120s)")

        self.fig6 = plt.figure(figsize=(15, 4))
        gs6 = GridSpec(1, 1, figure=self.fig6)

        self.ax_fft_zoom = self.fig6.add_subplot(gs6[0, 0])

        canvas6 = FigureCanvasTkAgg(self.fig6, master=fig6_frame)
        canvas6.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar6 = NavigationToolbar2Tk(canvas6, fig6_frame)
        toolbar6.update()

        self.figures.append(self.fig6)
        self.canvases.append(canvas6)
        self.all_axes.extend([self.ax_fft_zoom])

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

        for canvas in self.canvases:
            canvas.draw()

    def load_and_process(self):
        """Load CSV file and process data"""
        try:
            self.pwm_freq = float(self.entry_pwm_freq.get())
            if self.pwm_freq <= 0:
                messagebox.showerror("Error", "PWM frequency must be positive")
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid PWM frequency. Please enter a number.")
            return

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
            self.data = self.load_csv_data(filepath)
            self.process_tremor_analysis()
            self.lbl_status.config(text="Analysis Complete", foreground="green")
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

            header_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('Timestamp,'):
                    header_idx = i
                    break

            for line in lines[header_idx + 1:]:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                try:
                    parts = line.split(',')
                    if len(parts) >= 4:
                        data['Timestamp'].append(int(parts[0]))
                        data['Ax'].append(float(parts[1]))
                        data['Ay'].append(float(parts[2]))
                        data['Az'].append(float(parts[3]))
                except (ValueError, IndexError):
                    continue

        for key in data:
            data[key] = np.array(data[key])

        return data

    def process_tremor_analysis(self):
        """Main tremor analysis pipeline - Independent axis filtering"""

        ax = self.data['Ax']
        ay = self.data['Ay']
        az = self.data['Az']
        t = self.data['Timestamp'] / 1000.0  # Convert to seconds

        # Step 1: Create tremor bandpass filter (2-8 Hz)
        nyquist = 0.5 * FS
        b_tremor, a_tremor = butter(FILTER_ORDER,
                                    [FREQ_TREMOR_LOW/nyquist, FREQ_TREMOR_HIGH/nyquist],
                                    btype='band')

        # Step 2: Filter each axis independently
        # Bandpass inherently removes DC (gravity) and high-freq noise in one step
        ax_filt = filtfilt(b_tremor, a_tremor, ax)
        ay_filt = filtfilt(b_tremor, a_tremor, ay)
        az_filt = filtfilt(b_tremor, a_tremor, az)

        # Step 3: Resultant vector from filtered axes
        result_filtered = np.sqrt(ax_filt**2 + ay_filt**2 + az_filt**2)

        # Raw resultant for display (DC removed for visualization)
        result_raw = np.sqrt(ax**2 + ay**2 + az**2)
        result_raw = result_raw - np.mean(result_raw)

        # Step 4: PSD on individual filtered axes (avoids frequency doubling
        # that would occur from the nonlinear sqrt in the resultant vector)
        nperseg = min(len(ax_filt), int(FS * WINDOW_SEC))
        noverlap = int(nperseg * PSD_OVERLAP)

        f_psd, psd_ax = welch(ax_filt, FS, nperseg=nperseg, noverlap=noverlap)
        _, psd_ay = welch(ay_filt, FS, nperseg=nperseg, noverlap=noverlap)
        _, psd_az = welch(az_filt, FS, nperseg=nperseg, noverlap=noverlap)
        psd_filt = psd_ax + psd_ay + psd_az  # Sum of per-axis PSDs

        # Raw PSD for comparison display
        _, psd_raw = welch(result_raw, FS, nperseg=nperseg, noverlap=noverlap)

        # Store filtered axes for per-axis FFT computation
        self._filtered_axes = (ax_filt, ay_filt, az_filt)

        # Step 5: Calculate metrics
        metrics = self.calculate_metrics(result_raw, result_filtered, f_psd, psd_filt)

        # Visualize everything
        self.plot_analysis(
            t, result_raw, result_filtered,
            f_psd, psd_raw, psd_filt,
            b_tremor, a_tremor, metrics
        )

    def calculate_metrics(self, accel_raw, accel_filt, freq, psd_filt):
        """Calculate tremor metrics - INFORMATIONAL ONLY (no pass/fail).
        Reports frequency deviation, peak SNR, and dominant power ratio."""
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
            band_psd = psd_filt[rest_mask]
            band_freq = freq[rest_mask]
            peak_idx = np.argmax(band_psd)
            metrics['dominant_freq'] = band_freq[peak_idx]
            metrics['peak_power_density'] = band_psd[peak_idx]

            # SNR: peak PSD vs MPU6050 sensor noise floor
            # 3-axis sum → noise floor is 3x per-axis noise PSD
            sensor_noise_floor = 3 * MPU6050_NOISE_PSD
            metrics['snr_db'] = 10.0 * np.log10(band_psd[peak_idx] / sensor_noise_floor)
            metrics['noise_floor'] = sensor_noise_floor

            # Dominant Power Ratio (DPR): integrated power in a small window
            # around the peak (+/-1 bin = +/-0.25 Hz), divided by total band
            # power. Both use trapz for consistent area-under-curve integration.
            # DPR = trapz(PSD[peak-1..peak+1]) / trapz(PSD[2-8 Hz])
            pk_lo = max(0, peak_idx - 1)
            pk_hi = min(len(band_psd), peak_idx + 2)  # exclusive end
            peak_power = np.trapz(band_psd[pk_lo:pk_hi], band_freq[pk_lo:pk_hi])
            # total_power already computed above via trapz over the full band
            metrics['dominant_power_ratio'] = (
                peak_power / metrics['total_power']
                if metrics['total_power'] > 0 else 0.0
            )

        else:
            metrics['dominant_freq'] = 0
            metrics['peak_power_density'] = 0
            metrics['snr_db'] = 0.0
            metrics['noise_floor'] = 0.0
            metrics['dominant_power_ratio'] = 0.0

        # Frequency deviation from PWM (informational, no pass/fail)
        measured_freq = metrics['dominant_freq']
        pwm_freq = self.pwm_freq
        deviation = abs(measured_freq - pwm_freq)
        metrics['deviation'] = deviation
        metrics['pwm_freq'] = pwm_freq

        # Update UI labels - informational only
        self.lbl_measured_freq.config(
            text=f"Measured: {measured_freq:.2f} Hz | SNR: {metrics['snr_db']:.1f} dB"
        )
        self.lbl_validation.config(
            text=f"Deviation: {deviation:.2f} Hz | DPR: {metrics['dominant_power_ratio']:.1%}",
            foreground=COL_INFO
        )

        return metrics

    def plot_analysis(self, t, result_raw, result_filt,
                     f_psd, psd_raw, psd_filt,
                     b_tremor, a_tremor, metrics):
        """Plot complete analysis - 6 figure tabs, no pass/fail coloring"""

        # ============================================================
        # FIGURE 1: FILTER CHARACTERISTICS
        # ============================================================

        self.ax_bode_mag.clear()
        w, h = freqz(b_tremor, a_tremor, worN=4096, fs=FS)
        mag_single = 20*np.log10(abs(h))
        mag_filtfilt = 2 * mag_single  # filtfilt doubles attenuation in dB

        self.ax_bode_mag.plot(w, mag_single, color='gray', linewidth=1.5,
                             linestyle='--', alpha=0.6, label='Single-pass (O4)')
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

        self.ax_bode_phase.clear()
        single_pass_phase = np.unwrap(np.angle(h)) * 180/np.pi

        self.ax_bode_phase.plot(w, single_pass_phase,
                               color='gray', linewidth=1.5, linestyle='--', alpha=0.6,
                               label='Single-pass (lfilter)')
        self.ax_bode_phase.axhline(0, color='green', linewidth=2.5,
                                   label='Zero-phase (filtfilt)')

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

        self.ax_result_raw.clear()
        self.ax_result_raw.plot(t, result_raw, color=COL_RAW, linewidth=0.8, alpha=0.7)
        self.ax_result_raw.set_title(f'Fig 2.1 - Resultant Vector Raw | RMS: {np.sqrt(np.mean(result_raw**2)):.4f} m/s^2',
                                    fontweight='bold')
        self.ax_result_raw.set_ylabel('Magnitude (m/s^2)')
        self.ax_result_raw.set_xlabel('Time (s)')
        self.ax_result_raw.grid(True, alpha=0.3)
        self.ax_result_raw.margins(x=0)

        self.ax_result_filtered.clear()
        self.ax_result_filtered.plot(t, result_filt, color=COL_FILTERED, linewidth=1.2)

        envelope_result = np.abs(hilbert(result_filt))
        self.ax_result_filtered.plot(t, envelope_result, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)
        self.ax_result_filtered.plot(t, -envelope_result, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)

        self.ax_result_filtered.set_title(f'Fig 2.2 - Resultant Filtered (2-8 Hz) | RMS: {metrics["accel_rms"]:.4f} m/s^2',
                                         fontweight='bold')
        self.ax_result_filtered.set_ylabel('Magnitude (m/s^2)')
        self.ax_result_filtered.set_xlabel('Time (s)')
        self.ax_result_filtered.grid(True, alpha=0.3)
        self.ax_result_filtered.margins(x=0)

        # ============================================================
        # FIGURE 3: PSD ANALYSIS (no pass/fail coloring)
        # ============================================================

        self.ax_psd_full.clear()
        psd_raw_db = 10*np.log10(psd_raw + 1e-12)
        psd_filt_db = 10*np.log10(psd_filt + 1e-12)

        self.ax_psd_full.plot(f_psd, psd_raw_db, color=COL_RAW,
                             linewidth=1, alpha=0.6, label='Raw')
        self.ax_psd_full.plot(f_psd, psd_filt_db, color=COL_FILTERED,
                             linewidth=1.5, label='Filtered')

        if metrics['dominant_freq'] > 0:
            peak_db = 10*np.log10(metrics['peak_power_density'] + 1e-12)
            self.ax_psd_full.plot(metrics['dominant_freq'], peak_db, 'o',
                                color='red', markersize=8,
                                label=f"Peak: {metrics['dominant_freq']:.2f} Hz")

        self.ax_psd_full.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH,
                                color='yellow', alpha=0.15, label='Analysis 2-8 Hz')

        self.ax_psd_full.set_title('Fig 3.1 - PSD: Resultant Vector (0-20 Hz)', fontweight='bold')
        self.ax_psd_full.set_xlabel('Frequency (Hz)')
        self.ax_psd_full.set_ylabel('Power (dB)')
        self.ax_psd_full.set_xlim(0, 20)
        self.ax_psd_full.grid(True, alpha=0.3)
        self.ax_psd_full.legend(fontsize=7)

        # PSD zoomed to tremor range (1-12 Hz) - informational deviation band
        self.ax_psd_zoom.clear()

        self.ax_psd_zoom.plot(f_psd, psd_filt_db, color=COL_FILTERED,
                             linewidth=1.5, label='Filtered PSD')

        pwm_freq = metrics['pwm_freq']
        self.ax_psd_zoom.axvline(pwm_freq, color='blue', linestyle='-', alpha=0.7,
                                linewidth=1.5, label=f'PWM Freq: {pwm_freq:.1f} Hz')
        # Informational reference band (no pass/fail color)
        self.ax_psd_zoom.axvspan(pwm_freq - FREQ_TOLERANCE_HZ, pwm_freq + FREQ_TOLERANCE_HZ,
                               color=COL_INFO, alpha=0.15,
                               label=f'Reference \u00b1{FREQ_TOLERANCE_HZ} Hz')

        self.ax_psd_zoom.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH,
                                color='yellow', alpha=0.1, label='Analysis 2-8 Hz')

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

        # Metrics table - informational only, no pass/fail
        self.ax_metrics.clear()
        self.ax_metrics.axis('off')

        metrics_text = f"""MEASUREMENT INFO (No Pass/Fail)
{'='*44}
PWM Frequency:       {metrics['pwm_freq']:.2f} Hz
PSD Peak Freq:       {metrics['dominant_freq']:.2f} Hz
Deviation:           {metrics['deviation']:.2f} Hz
Reference:           +/-{FREQ_TOLERANCE_HZ:.2f} Hz
Peak SNR:            {metrics['snr_db']:.1f} dB
Noise Floor:         {metrics['noise_floor']:.6f} (m/s^2)^2/Hz
Dom. Power Ratio:    {metrics['dominant_power_ratio']:.1%}

RESULTANT VECTOR METRICS
{'='*44}
RMS Amplitude:       {metrics['accel_rms']:.4f} m/s^2
Mean Amplitude:      {metrics['accel_mean']:.4f} m/s^2
Max Amplitude:       {metrics['accel_max']:.4f} m/s^2

REST TREMOR ANALYSIS (2-8 Hz)
{'='*44}
Dominant Freq:       {metrics['dominant_freq']:.2f} Hz
Peak PSD:            {metrics['peak_power_density']:.6f} (m/s^2)^2/Hz
Band Power:          {metrics['total_power']:.6f} (m/s^2)^2
Filter:              2-8 Hz (Butterworth O4, filtfilt)
"""

        self.ax_metrics.text(0.03, 0.97, metrics_text,
                            transform=self.ax_metrics.transAxes,
                            fontfamily='monospace', fontsize=9.5,
                            verticalalignment='top',
                            bbox=dict(boxstyle='round,pad=0.5', facecolor=COL_INFO, alpha=0.15))
        self.ax_metrics.set_title('Fig 3.3 - Metrics (Informational)', fontweight='bold', loc='left')

        # ============================================================
        # FIGURE 4 & 5: TWO CONSECUTIVE 5-SECOND WINDOWS
        # ============================================================
        # Pick two sequential 5s windows from the middle of the recording.
        # Window A starts at t_mid - 5s, ends at t_mid.
        # Window B starts at t_mid,     ends at t_mid + 5s.
        # This gives 10 consecutive seconds split into two tabs.

        t_mid = t[len(t) // 2]
        zoom_a_start = t_mid - ZOOM_DURATION_SEC
        zoom_a_end = t_mid
        zoom_b_start = t_mid
        zoom_b_end = t_mid + ZOOM_DURATION_SEC

        # Fig 4: first 5s window (A)
        self._plot_zoomed_window(
            t, result_raw, result_filt, metrics,
            ax_filt=self.ax_zoom_a_filt,
            ax_overlay=self.ax_zoom_a_overlay,
            zoom_start=zoom_a_start,
            zoom_end=zoom_a_end,
            fig_prefix='4',
            window_label='A'
        )

        # Fig 5: next consecutive 5s window (B)
        self._plot_zoomed_window(
            t, result_raw, result_filt, metrics,
            ax_filt=self.ax_zoom_b_filt,
            ax_overlay=self.ax_zoom_b_overlay,
            zoom_start=zoom_b_start,
            zoom_end=zoom_b_end,
            fig_prefix='5',
            window_label='B'
        )

        # ============================================================
        # FIGURE 6: FFT OVER FULL 120s
        # ============================================================
        self._plot_fft_full(result_filt, result_raw, metrics)

        # Draw all canvases
        for canvas in self.canvases:
            canvas.draw()

        # Print informational summary to console
        print("\n" + "="*70)
        print("MEASUREMENT RESULTS (EXPERIMENTAL - NO PASS/FAIL)")
        print("="*70)
        print(f"\nFREQUENCY INFO:")
        print(f"  PWM Frequency:     {metrics['pwm_freq']:.2f} Hz")
        print(f"  PSD Peak Freq:     {metrics['dominant_freq']:.2f} Hz")
        print(f"  Deviation:         {metrics['deviation']:.2f} Hz")
        print(f"  Reference:         +/-{FREQ_TOLERANCE_HZ:.2f} Hz")
        print(f"  Peak SNR:          {metrics['snr_db']:.1f} dB")
        print(f"  Noise Floor:       {metrics['noise_floor']:.6f} (m/s^2)^2/Hz")
        print(f"  Dom. Power Ratio:  {metrics['dominant_power_ratio']:.1%}")
        print(f"\nRESULTANT VECTOR METRICS:")
        print(f"  RMS Amplitude:     {metrics['accel_rms']:.4f} m/s^2")
        print(f"  Mean Amplitude:    {metrics['accel_mean']:.4f} m/s^2")
        print(f"  Max Amplitude:     {metrics['accel_max']:.4f} m/s^2")
        print(f"\nREST TREMOR ANALYSIS (2-8 Hz):")
        print(f"  Filter:            2-8 Hz (Butterworth Order 4, filtfilt)")
        print(f"  Dominant Freq:     {metrics['dominant_freq']:.2f} Hz")
        print(f"  Peak PSD:          {metrics['peak_power_density']:.6f} (m/s^2)^2/Hz")
        print(f"  Band Power:        {metrics['total_power']:.6f} (m/s^2)^2")
        print("="*70 + "\n")

    # ------------------------------------------------------------------
    # Helper: plot a 5-second zoomed window (reused for Fig 4 and Fig 5)
    # ------------------------------------------------------------------
    def _plot_zoomed_window(self, t, result_raw, result_filt, metrics,
                            ax_filt, ax_overlay,
                            zoom_start, zoom_end,
                            fig_prefix, window_label):
        """Plot a 5-second zoomed window with Hilbert envelope and cycle markers.

        Args:
            zoom_start: start time of the window (seconds).
            zoom_end:   end time of the window (seconds).
            fig_prefix: '4' or '5' for title numbering.
            window_label: 'A' or 'B' to distinguish the two consecutive windows.
        """
        zoom_mask = (t >= zoom_start) & (t <= zoom_end)
        t_zoom = t[zoom_mask]
        filt_zoom = result_filt[zoom_mask]
        raw_zoom = result_raw[zoom_mask]

        dom_freq = metrics['dominant_freq']

        # Actual duration of this window (accounts for sample boundaries)
        actual_duration = t_zoom[-1] - t_zoom[0] if len(t_zoom) > 1 else ZOOM_DURATION_SEC

        # Count complete cycles via rising zero-crossings
        cycle_count = 0
        crossing_times = []
        if len(filt_zoom) > 1:
            for i in range(1, len(filt_zoom)):
                if filt_zoom[i - 1] < 0 and filt_zoom[i] >= 0:
                    # Linear interpolation for precise crossing time
                    frac = -filt_zoom[i - 1] / (filt_zoom[i] - filt_zoom[i - 1])
                    t_cross = t_zoom[i - 1] + frac * (t_zoom[i] - t_zoom[i - 1])
                    crossing_times.append(t_cross)
                    cycle_count += 1

        # Measured frequency from zero-crossing count
        measured_freq_zc = cycle_count / actual_duration if actual_duration > 0 else 0

        # -- Subplot 1: Filtered signal with Hilbert envelope and cycle markers --
        ax_filt.clear()
        ax_filt.plot(t_zoom, filt_zoom, color=COL_FILTERED, linewidth=1.5)

        # Hilbert envelope
        if len(filt_zoom) > 10:
            env_zoom = np.abs(hilbert(filt_zoom))
            ax_filt.plot(t_zoom, env_zoom, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)
            ax_filt.plot(t_zoom, -env_zoom, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)

        # Mark each rising zero-crossing with a numbered blue marker
        for idx, t_cross in enumerate(crossing_times):
            ax_filt.axvline(x=t_cross, color='#2196F3', linewidth=0.8, alpha=0.5)
            ax_filt.text(t_cross, ax_filt.get_ylim()[1] * 0.85,
                         str(idx + 1), ha='center', fontsize=7, fontweight='bold',
                         color='#1565C0')

        ax_filt.set_title(
            f'Fig {fig_prefix}.1 - Filtered Zoomed {window_label} '
            f'[{zoom_start:.1f}s-{zoom_end:.1f}s] | '
            f'Cycles: {cycle_count} | '
            f'{cycle_count}/{actual_duration:.1f}s = {measured_freq_zc:.2f} Hz '
            f'(PSD: {dom_freq:.2f} Hz)',
            fontweight='bold', fontsize=9)
        ax_filt.set_ylabel('Magnitude (m/s\u00b2)')
        ax_filt.set_xlabel('Time (s)')
        ax_filt.grid(True, alpha=0.3)

        # -- Subplot 2: Raw vs filtered overlay --
        ax_overlay.clear()
        ax_overlay.plot(t_zoom, raw_zoom, color=COL_RAW, linewidth=1,
                        alpha=0.5, label='Raw')
        ax_overlay.plot(t_zoom, filt_zoom, color=COL_FILTERED, linewidth=1.5,
                        label='Filtered (2-8 Hz)')

        for t_cross in crossing_times:
            ax_overlay.axvline(x=t_cross, color='#2196F3', linewidth=0.5, alpha=0.3)

        ax_overlay.set_title(
            f'Fig {fig_prefix}.2 - Raw vs Filtered {window_label} '
            f'[{zoom_start:.1f}s-{zoom_end:.1f}s]',
            fontweight='bold', fontsize=9)
        ax_overlay.set_ylabel('Magnitude (m/s\u00b2)')
        ax_overlay.set_xlabel('Time (s)')
        ax_overlay.grid(True, alpha=0.3)
        ax_overlay.legend(fontsize=8)

    # ------------------------------------------------------------------
    # Helper: FFT over full recording
    # ------------------------------------------------------------------
    def _plot_fft_full(self, result_filt, result_raw, metrics):
        """Compute and plot FFT magnitude spectrum over the full recording.

        Uses per-axis FFT (RSS) to avoid frequency doubling from nonlinear sqrt.
        Single full-width plot zoomed into the 1-12 Hz range with peak annotation.
        """
        ax_filt, ay_filt, az_filt = self._filtered_axes
        N = len(ax_filt)

        # Per-axis FFT, then RSS (root sum of squares) for total magnitude
        fft_freqs = np.fft.rfftfreq(N, d=1.0/FS)
        fft_mag_ax = np.abs(np.fft.rfft(ax_filt)) / N
        fft_mag_ay = np.abs(np.fft.rfft(ay_filt)) / N
        fft_mag_az = np.abs(np.fft.rfft(az_filt)) / N
        fft_magnitude = np.sqrt(fft_mag_ax**2 + fft_mag_ay**2 + fft_mag_az**2)

        # Find peak in the 2-8 Hz band on the filtered FFT
        band_mask = (fft_freqs >= FREQ_REST_LOW) & (fft_freqs <= FREQ_REST_HIGH)
        if np.sum(band_mask) > 0:
            band_mag = fft_magnitude[band_mask]
            band_freq = fft_freqs[band_mask]
            fft_peak_idx = np.argmax(band_mag)
            fft_peak_freq = band_freq[fft_peak_idx]
            fft_peak_mag = band_mag[fft_peak_idx]
        else:
            fft_peak_freq = 0
            fft_peak_mag = 0

        # -- Fig 6: FFT zoomed into 1-12 Hz (full-width single plot) --
        self.ax_fft_zoom.clear()
        self.ax_fft_zoom.plot(fft_freqs, fft_magnitude, color=COL_FILTERED,
                             linewidth=1.5, label='Filtered FFT')

        pwm_freq = metrics['pwm_freq']
        self.ax_fft_zoom.axvline(pwm_freq, color='blue', linestyle='-', alpha=0.7,
                                linewidth=1.5, label=f'PWM Freq: {pwm_freq:.1f} Hz')

        self.ax_fft_zoom.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH,
                                color='yellow', alpha=0.1, label='2-8 Hz band')

        if fft_peak_freq > 0:
            self.ax_fft_zoom.plot(fft_peak_freq, fft_peak_mag, 'o',
                                color='red', markersize=10,
                                label=f'Peak: {fft_peak_freq:.2f} Hz ({fft_peak_mag:.4f})')

        self.ax_fft_zoom.set_title(
            f'Fig 6 - FFT (1-12 Hz, Full {N/FS:.0f}s) | Peak: {fft_peak_freq:.2f} Hz',
            fontweight='bold')
        self.ax_fft_zoom.set_xlabel('Frequency (Hz)')
        self.ax_fft_zoom.set_ylabel('Magnitude (m/s\u00b2)')
        self.ax_fft_zoom.set_xlim(1, 12)
        self.ax_fft_zoom.grid(True, alpha=0.3)
        self.ax_fft_zoom.legend(fontsize=7)


if __name__ == "__main__":
    root = tk.Tk()
    app = TremorAnalyzerExperimental(root)
    root.mainloop()
