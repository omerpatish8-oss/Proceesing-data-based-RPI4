#!/usr/bin/env python3
"""
Tremor Analysis Tool - Research-Based Implementation
Focused on accelerometer analysis with axis-specific and resultant vector views
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

# Tremor band filter (single filter - covers all tremor frequencies)
FREQ_TREMOR_LOW = 3.0   # Lower bound
FREQ_TREMOR_HIGH = 12.0 # Upper bound

# PSD parameters
WINDOW_SEC = 4          # Welch window size (seconds)
PSD_OVERLAP = 0.5       # 50% overlap

# Validation tolerance
FREQ_TOLERANCE_HZ = 0.5 # Acceptable deviation from expected frequency

# Visual styling
COL_RAW = '#2F4F4F'         # Dark Slate Gray - Raw signal
COL_FILTERED = '#FF6347'    # Tomato - Filtered signal
COL_X = '#E74C3C'           # Red - X axis
COL_Y = '#808080'           # Gray - Y axis
COL_Z = '#3498DB'           # Blue - Z axis
COL_PASS = '#2ECC71'        # Green - Validation pass
COL_FAIL = '#E74C3C'        # Red - Validation fail

class TremorAnalyzerResearch:
    def __init__(self, root):
        self.root = root
        self.root.title("Tremor Analyzer - Input/Output Validation")
        self.root.geometry("1600x1000")

        # Data storage
        self.csv_path = None
        self.data = None

        # Expected frequency (from motor input)
        self.expected_freq_min = None
        self.expected_freq_max = None

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

        # Expected frequency input (from motor)
        freq_frame = ttk.LabelFrame(control_frame, text="Expected Frequency (Motor Input)",
                                    padding="5")
        freq_frame.pack(side=tk.RIGHT, padx=10)

        ttk.Label(freq_frame, text="Min (Hz):").pack(side=tk.LEFT)
        self.entry_freq_min = ttk.Entry(freq_frame, width=6)
        self.entry_freq_min.pack(side=tk.LEFT, padx=2)
        self.entry_freq_min.insert(0, "4.0")

        ttk.Label(freq_frame, text="Max (Hz):").pack(side=tk.LEFT, padx=(10, 0))
        self.entry_freq_max = ttk.Entry(freq_frame, width=6)
        self.entry_freq_max.pack(side=tk.LEFT, padx=2)
        self.entry_freq_max.insert(0, "6.0")

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
        self.notebook.add(fig1_frame, text="Figure 1 - Filters & Metrics")

        self.fig1 = plt.figure(figsize=(15, 4))
        gs1 = GridSpec(1, 3, figure=self.fig1, hspace=0.3, wspace=0.3)

        self.ax_bode_mag = self.fig1.add_subplot(gs1[0, 0])
        self.ax_bode_phase = self.fig1.add_subplot(gs1[0, 1])
        self.ax_metrics = self.fig1.add_subplot(gs1[0, 2])

        canvas1 = FigureCanvasTkAgg(self.fig1, master=fig1_frame)
        canvas1.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar1 = NavigationToolbar2Tk(canvas1, fig1_frame)
        toolbar1.update()

        self.figures.append(self.fig1)
        self.canvases.append(canvas1)
        self.all_axes.extend([self.ax_bode_mag, self.ax_bode_phase, self.ax_metrics])

        # ==================== FIGURE 2: DOMINANT AXIS ANALYSIS ====================
        fig2_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig2_frame, text="Figure 2 - Dominant Axis")

        self.fig2 = plt.figure(figsize=(15, 4))
        gs2 = GridSpec(1, 3, figure=self.fig2, hspace=0.3, wspace=0.3)

        self.ax_axis_raw = self.fig2.add_subplot(gs2[0, 0])
        self.ax_axis_filtered = self.fig2.add_subplot(gs2[0, 1])
        self.ax_axis_overlay = self.fig2.add_subplot(gs2[0, 2])

        canvas2 = FigureCanvasTkAgg(self.fig2, master=fig2_frame)
        canvas2.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar2 = NavigationToolbar2Tk(canvas2, fig2_frame)
        toolbar2.update()

        self.figures.append(self.fig2)
        self.canvases.append(canvas2)
        self.all_axes.extend([self.ax_axis_raw, self.ax_axis_filtered, self.ax_axis_overlay])

        # ==================== FIGURE 3: RESULTANT VECTOR ANALYSIS ====================
        fig3_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig3_frame, text="Figure 3 - Resultant Vector")

        self.fig3 = plt.figure(figsize=(15, 4))
        gs3 = GridSpec(1, 3, figure=self.fig3, hspace=0.3, wspace=0.3)

        self.ax_result_raw = self.fig3.add_subplot(gs3[0, 0])
        self.ax_result_filtered = self.fig3.add_subplot(gs3[0, 1])
        self.ax_result_overlay = self.fig3.add_subplot(gs3[0, 2])

        canvas3 = FigureCanvasTkAgg(self.fig3, master=fig3_frame)
        canvas3.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar3 = NavigationToolbar2Tk(canvas3, fig3_frame)
        toolbar3.update()

        self.figures.append(self.fig3)
        self.canvases.append(canvas3)
        self.all_axes.extend([self.ax_result_raw, self.ax_result_filtered, self.ax_result_overlay])

        # ==================== FIGURE 4: PSD ANALYSIS ====================
        fig4_frame = ttk.Frame(self.notebook)
        self.notebook.add(fig4_frame, text="Figure 4 - PSD Analysis")

        self.fig4 = plt.figure(figsize=(15, 4))
        gs4 = GridSpec(1, 3, figure=self.fig4, hspace=0.3, wspace=0.3)

        self.ax_psd_axis = self.fig4.add_subplot(gs4[0, 0])
        self.ax_psd_all = self.fig4.add_subplot(gs4[0, 1])
        self.ax_bands = self.fig4.add_subplot(gs4[0, 2])

        canvas4 = FigureCanvasTkAgg(self.fig4, master=fig4_frame)
        canvas4.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        toolbar4 = NavigationToolbar2Tk(canvas4, fig4_frame)
        toolbar4.update()

        self.figures.append(self.fig4)
        self.canvases.append(canvas4)
        self.all_axes.extend([self.ax_psd_axis, self.ax_psd_all, self.ax_bands])

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
        # Get expected frequency from input fields
        try:
            self.expected_freq_min = float(self.entry_freq_min.get())
            self.expected_freq_max = float(self.entry_freq_max.get())
            if self.expected_freq_min >= self.expected_freq_max:
                messagebox.showerror("Error", "Min frequency must be less than Max frequency")
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid frequency values. Please enter numbers.")
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
        """Main tremor analysis pipeline - Simplified with single filter"""

        # Extract data
        ax = self.data['Ax']
        ay = self.data['Ay']
        az = self.data['Az']
        t = self.data['Timestamp'] / 1000.0  # Convert to seconds

        # Remove DC offset per axis (gravity removal)
        ax_clean = ax - np.mean(ax)
        ay_clean = ay - np.mean(ay)
        az_clean = az - np.mean(az)

        # Find highest energy axis
        energy_x = np.sum(ax_clean**2)
        energy_y = np.sum(ay_clean**2)
        energy_z = np.sum(az_clean**2)

        energies = {'X': energy_x, 'Y': energy_y, 'Z': energy_z}
        max_axis = max(energies, key=energies.get)

        if max_axis == 'X':
            dominant_axis = ax_clean
            axis_color = COL_X
        elif max_axis == 'Y':
            dominant_axis = ay_clean
            axis_color = COL_Y
        else:
            dominant_axis = az_clean
            axis_color = COL_Z

        # Calculate resultant vector (magnitude)
        accel_mag = np.sqrt(ax_clean**2 + ay_clean**2 + az_clean**2)

        # Create single tremor filter (3-12 Hz)
        nyquist = 0.5 * FS
        b_tremor, a_tremor = butter(FILTER_ORDER,
                                    [FREQ_TREMOR_LOW/nyquist, FREQ_TREMOR_HIGH/nyquist],
                                    btype='band')

        # Apply filter to dominant axis and resultant
        axis_filtered = filtfilt(b_tremor, a_tremor, dominant_axis)
        result_filtered = filtfilt(b_tremor, a_tremor, accel_mag)

        # Calculate PSDs
        nperseg = min(len(accel_mag), int(FS * WINDOW_SEC))
        noverlap = int(nperseg * PSD_OVERLAP)

        # PSD for dominant axis
        f_axis, psd_axis_raw = welch(dominant_axis, FS, nperseg=nperseg, noverlap=noverlap)
        _, psd_axis_filt = welch(axis_filtered, FS, nperseg=nperseg, noverlap=noverlap)

        # PSD for resultant
        f_result, psd_result_raw = welch(accel_mag, FS, nperseg=nperseg, noverlap=noverlap)
        _, psd_result_filt = welch(result_filtered, FS, nperseg=nperseg, noverlap=noverlap)

        # Calculate metrics with validation
        metrics = self.calculate_metrics(
            accel_mag, result_filtered,
            f_result, psd_result_raw, max_axis, axis_color, axis_filtered
        )

        # Visualize everything
        self.plot_analysis(
            t, dominant_axis, axis_filtered, accel_mag, result_filtered,
            ax_clean, ay_clean, az_clean,
            f_axis, psd_axis_raw, psd_axis_filt,
            f_result, psd_result_raw, psd_result_filt,
            b_tremor, a_tremor,
            metrics, max_axis, axis_color
        )

    def calculate_metrics(self, accel_raw, accel_filt,
                          freq, psd, max_axis, axis_color, axis_filt):
        """Calculate tremor metrics and validate against expected frequency"""
        metrics = {}

        # Store axis info
        metrics['max_axis'] = max_axis
        metrics['axis_color'] = axis_color

        # Accelerometer features (using resultant vector)
        metrics['accel_mean'] = np.mean(accel_filt)
        metrics['accel_rms'] = np.sqrt(np.mean(accel_filt**2))
        metrics['accel_max'] = np.max(np.abs(accel_filt))

        # Dominant axis RMS
        metrics['axis_rms'] = np.sqrt(np.mean(axis_filt**2))

        # Total power in tremor band
        tremor_mask = (freq >= FREQ_TREMOR_LOW) & (freq <= FREQ_TREMOR_HIGH)
        metrics['total_power'] = np.trapz(psd[tremor_mask], freq[tremor_mask])

        # Dominant frequency and peak spectral density
        if np.sum(tremor_mask) > 0:
            peak_idx = np.argmax(psd[tremor_mask])
            metrics['dominant_freq'] = freq[tremor_mask][peak_idx]
            metrics['peak_power_density'] = psd[tremor_mask][peak_idx]
        else:
            metrics['dominant_freq'] = 0
            metrics['peak_power_density'] = 0

        # Input-Output Validation
        measured_freq = metrics['dominant_freq']
        expected_min = self.expected_freq_min
        expected_max = self.expected_freq_max

        # Check if measured frequency is within expected range
        in_range = (measured_freq >= expected_min) and (measured_freq <= expected_max)

        if in_range:
            metrics['validation_status'] = "PASS"
            metrics['deviation'] = 0.0
            metrics['validation_color'] = COL_PASS
        else:
            metrics['validation_status'] = "FAIL"
            # Calculate deviation from nearest boundary
            if measured_freq < expected_min:
                metrics['deviation'] = expected_min - measured_freq
            else:
                metrics['deviation'] = measured_freq - expected_max
            metrics['validation_color'] = COL_FAIL

        metrics['expected_min'] = expected_min
        metrics['expected_max'] = expected_max

        # Update UI
        self.lbl_measured_freq.config(text=f"Measured: {measured_freq:.2f} Hz")
        self.lbl_validation.config(
            text=f"Status: {metrics['validation_status']}",
            foreground=metrics['validation_color']
        )

        return metrics

    def plot_analysis(self, t, axis_raw, axis_filt, result_raw, result_filt,
                     ax, ay, az, f_axis, psd_axis_raw, psd_axis_filt,
                     f_result, psd_result_raw, psd_result_filt,
                     b_tremor, a_tremor, metrics, max_axis, axis_color):
        """Plot complete analysis"""

        # ============================================================
        # ROW 1: FILTER CHARACTERISTICS
        # ============================================================

        # Bode Magnitude
        self.ax_bode_mag.clear()
        w, h = freqz(b_tremor, a_tremor, worN=4096, fs=FS)

        self.ax_bode_mag.plot(w, 20*np.log10(abs(h)), color='purple', linewidth=2)
        self.ax_bode_mag.axvline(FREQ_TREMOR_LOW, color='red', linestyle=':', alpha=0.5, label=f'{FREQ_TREMOR_LOW} Hz')
        self.ax_bode_mag.axvline(FREQ_TREMOR_HIGH, color='blue', linestyle=':', alpha=0.5, label=f'{FREQ_TREMOR_HIGH} Hz')
        self.ax_bode_mag.axhline(-3, color='green', linestyle='--', alpha=0.5, label='-3 dB')

        self.ax_bode_mag.set_title('Fig 1.1 - Filter Magnitude Response (Butterworth Order 4)', fontweight='bold')
        self.ax_bode_mag.set_xlabel('Frequency (Hz)')
        self.ax_bode_mag.set_ylabel('Magnitude (dB)')
        self.ax_bode_mag.set_xlim(0, 20)
        self.ax_bode_mag.set_ylim(-60, 5)
        self.ax_bode_mag.grid(True, alpha=0.3)
        self.ax_bode_mag.legend(fontsize=8)

        # Bode Phase
        self.ax_bode_phase.clear()
        self.ax_bode_phase.plot(w, np.unwrap(np.angle(h)) * 180/np.pi,
                               color='purple', linewidth=2)
        self.ax_bode_phase.axvline(FREQ_TREMOR_LOW, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_phase.axvline(FREQ_TREMOR_HIGH, color='blue', linestyle=':', alpha=0.5)

        self.ax_bode_phase.set_title('Fig 1.2 - Filter Phase Response', fontweight='bold')
        self.ax_bode_phase.set_xlabel('Frequency (Hz)')
        self.ax_bode_phase.set_ylabel('Phase (degrees)')
        self.ax_bode_phase.set_xlim(0, 20)
        self.ax_bode_phase.grid(True, alpha=0.3)

        # Metrics and Validation Table
        self.ax_metrics.clear()
        self.ax_metrics.axis('off')

        # Validation status indicator
        status_symbol = "V" if metrics['validation_status'] == "PASS" else "X"
        deviation_text = f"Deviation: {metrics['deviation']:.2f} Hz" if metrics['deviation'] > 0 else "Deviation: 0 Hz"

        metrics_text = f"""INPUT-OUTPUT VALIDATION
{'─'*35}
Expected:    {metrics['expected_min']:.1f} - {metrics['expected_max']:.1f} Hz
Measured:    {metrics['dominant_freq']:.2f} Hz
Status:      [{status_symbol}] {metrics['validation_status']}
{deviation_text}

ACCELEROMETER METRICS
{'─'*35}
Dominant Axis:      {metrics['max_axis']}
Axis RMS ({metrics['max_axis']}):    {metrics['axis_rms']:.4f} m/s²
Resultant RMS:      {metrics['accel_rms']:.4f} m/s²
Mean Amplitude:     {metrics['accel_mean']:.4f} m/s²
Max Amplitude:      {metrics['accel_max']:.4f} m/s²

FREQUENCY ANALYSIS
{'─'*35}
Dominant Freq:      {metrics['dominant_freq']:.2f} Hz
Peak PSD:           {metrics['peak_power_density']:.6f} m²/s⁴/Hz
Total Power:        {metrics['total_power']:.6f} m²/s⁴
"""

        self.ax_metrics.text(0.05, 0.95, metrics_text,
                            transform=self.ax_metrics.transAxes,
                            fontfamily='monospace', fontsize=8,
                            verticalalignment='top')
        self.ax_metrics.set_title('Fig 1.3 - Metrics & Validation', fontweight='bold', loc='left')

        # ============================================================
        # ROW 2: HIGHEST ENERGY AXIS ANALYSIS
        # ============================================================

        # Raw signal
        self.ax_axis_raw.clear()
        self.ax_axis_raw.plot(t, axis_raw, color=COL_RAW, linewidth=0.8, alpha=0.7)
        self.ax_axis_raw.set_title(f'Fig 2.1 - {max_axis}-Axis Raw | RMS: {np.sqrt(np.mean(axis_raw**2)):.4f} m/s²',
                                  fontweight='bold')
        self.ax_axis_raw.set_ylabel(f'{max_axis} (m/s²)')
        self.ax_axis_raw.set_xlabel('Time (s)')
        self.ax_axis_raw.grid(True, alpha=0.3)
        self.ax_axis_raw.margins(x=0)

        # Filtered signal
        self.ax_axis_filtered.clear()
        self.ax_axis_filtered.plot(t, axis_filt, color=COL_FILTERED, linewidth=1.2)

        # Add envelope
        envelope = np.abs(hilbert(axis_filt))
        self.ax_axis_filtered.plot(t, envelope, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)
        self.ax_axis_filtered.plot(t, -envelope, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)

        self.ax_axis_filtered.set_title(f'Fig 2.2 - {max_axis}-Axis Filtered (3-12 Hz) | RMS: {np.sqrt(np.mean(axis_filt**2)):.4f} m/s²',
                                       fontweight='bold')
        self.ax_axis_filtered.set_ylabel(f'{max_axis} (m/s²)')
        self.ax_axis_filtered.set_xlabel('Time (s)')
        self.ax_axis_filtered.grid(True, alpha=0.3)
        self.ax_axis_filtered.margins(x=0)

        # Overlay comparison
        self.ax_axis_overlay.clear()
        self.ax_axis_overlay.plot(t, axis_raw, color=COL_RAW, linewidth=1,
                                 alpha=0.5, label='Raw')
        self.ax_axis_overlay.plot(t, axis_filt, color=COL_FILTERED, linewidth=1.5,
                                 label='Filtered (3-12 Hz)')

        self.ax_axis_overlay.set_title(f'Fig 2.3 - {max_axis}-Axis: Raw vs Filtered', fontweight='bold')
        self.ax_axis_overlay.set_ylabel(f'{max_axis} (m/s²)')
        self.ax_axis_overlay.set_xlabel('Time (s)')
        self.ax_axis_overlay.grid(True, alpha=0.3)
        self.ax_axis_overlay.margins(x=0)
        self.ax_axis_overlay.legend(fontsize=8)

        # ============================================================
        # ROW 3: RESULTANT VECTOR ANALYSIS
        # ============================================================

        # Raw resultant
        self.ax_result_raw.clear()
        self.ax_result_raw.plot(t, result_raw, color=COL_RAW, linewidth=0.8, alpha=0.7)
        self.ax_result_raw.set_title(f'Fig 3.1 - Resultant Vector Raw | RMS: {np.sqrt(np.mean(result_raw**2)):.4f} m/s²',
                                    fontweight='bold')
        self.ax_result_raw.set_ylabel('Magnitude (m/s²)')
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

        self.ax_result_filtered.set_title(f'Fig 3.2 - Resultant Filtered (3-12 Hz) | RMS: {metrics["accel_rms"]:.4f} m/s²',
                                         fontweight='bold')
        self.ax_result_filtered.set_ylabel('Magnitude (m/s²)')
        self.ax_result_filtered.set_xlabel('Time (s)')
        self.ax_result_filtered.grid(True, alpha=0.3)
        self.ax_result_filtered.margins(x=0)

        # Overlay comparison
        self.ax_result_overlay.clear()
        self.ax_result_overlay.plot(t, result_raw, color=COL_RAW, linewidth=1,
                                   alpha=0.5, label='Raw')
        self.ax_result_overlay.plot(t, result_filt, color=COL_FILTERED, linewidth=1.5,
                                   label='Filtered (3-12 Hz)')

        self.ax_result_overlay.set_title('Fig 3.3 - Resultant: Raw vs Filtered', fontweight='bold')
        self.ax_result_overlay.set_ylabel('Magnitude (m/s²)')
        self.ax_result_overlay.set_xlabel('Time (s)')
        self.ax_result_overlay.grid(True, alpha=0.3)
        self.ax_result_overlay.margins(x=0)
        self.ax_result_overlay.legend(fontsize=8)

        # ============================================================
        # ROW 4: PSD ANALYSIS
        # ============================================================

        # PSD of dominant axis
        self.ax_psd_axis.clear()
        psd_raw_db = 10*np.log10(psd_axis_raw + 1e-12)
        psd_filt_db = 10*np.log10(psd_axis_filt + 1e-12)

        self.ax_psd_axis.plot(f_axis, psd_raw_db, color=COL_RAW,
                             linewidth=1, alpha=0.6, label='Raw')
        self.ax_psd_axis.plot(f_axis, psd_filt_db, color=axis_color,
                             linewidth=1.5, label='Filtered')

        # Show expected frequency range
        expected_color = metrics['validation_color']
        self.ax_psd_axis.axvspan(metrics['expected_min'], metrics['expected_max'],
                                color=expected_color, alpha=0.3,
                                label=f"Expected ({metrics['expected_min']:.1f}-{metrics['expected_max']:.1f} Hz)")

        # Mark dominant frequency for THIS axis PSD
        tremor_mask_axis = (f_axis >= 3) & (f_axis <= 12)
        if np.sum(tremor_mask_axis) > 0:
            peak_idx_axis = np.argmax(psd_axis_raw[tremor_mask_axis])
            axis_dom_freq = f_axis[tremor_mask_axis][peak_idx_axis]
            axis_peak_power = psd_axis_raw[tremor_mask_axis][peak_idx_axis]
            axis_dom_psd_db = 10*np.log10(axis_peak_power + 1e-12)
            self.ax_psd_axis.plot(axis_dom_freq, axis_dom_psd_db, 'o',
                                 color='red', markersize=8,
                                 label=f"Measured: {axis_dom_freq:.2f} Hz")

        self.ax_psd_axis.set_title(f'Fig 4.1 - PSD: {max_axis}-Axis', fontweight='bold')
        self.ax_psd_axis.set_xlabel('Frequency (Hz)')
        self.ax_psd_axis.set_ylabel('Power (dB)')
        self.ax_psd_axis.set_xlim(0, 20)
        self.ax_psd_axis.grid(True, alpha=0.3)
        self.ax_psd_axis.legend(fontsize=7)

        # PSD of resultant vector
        self.ax_psd_all.clear()
        psd_result_raw_db = 10*np.log10(psd_result_raw + 1e-12)
        psd_result_filt_db = 10*np.log10(psd_result_filt + 1e-12)

        self.ax_psd_all.plot(f_result, psd_result_raw_db, color=COL_RAW,
                            linewidth=1, alpha=0.6, label='Raw')
        self.ax_psd_all.plot(f_result, psd_result_filt_db, color=COL_FILTERED,
                            linewidth=1.5, label='Filtered')

        # Show expected frequency range
        self.ax_psd_all.axvspan(metrics['expected_min'], metrics['expected_max'],
                               color=expected_color, alpha=0.3,
                               label=f"Expected ({metrics['expected_min']:.1f}-{metrics['expected_max']:.1f} Hz)")

        # Mark dominant frequency for resultant PSD
        if metrics['dominant_freq'] > 0:
            result_dom_psd_db = 10*np.log10(metrics['peak_power_density'] + 1e-12)
            self.ax_psd_all.plot(metrics['dominant_freq'], result_dom_psd_db, 'o',
                                color='red', markersize=8,
                                label=f"Measured: {metrics['dominant_freq']:.2f} Hz")

        self.ax_psd_all.set_title('Fig 4.2 - PSD: Resultant Vector', fontweight='bold')
        self.ax_psd_all.set_xlabel('Frequency (Hz)')
        self.ax_psd_all.set_ylabel('Power (dB)')
        self.ax_psd_all.set_xlim(0, 20)
        self.ax_psd_all.grid(True, alpha=0.3)
        self.ax_psd_all.legend(fontsize=7)

        # Validation Result Display
        self.ax_bands.clear()

        # Create validation visual
        status = metrics['validation_status']
        measured = metrics['dominant_freq']
        expected_min = metrics['expected_min']
        expected_max = metrics['expected_max']

        # Draw expected range bar
        self.ax_bands.barh(0, expected_max - expected_min, left=expected_min,
                          height=0.4, color=expected_color, alpha=0.5,
                          label='Expected Range')

        # Draw measured frequency marker
        self.ax_bands.plot(measured, 0, 'o', color='red', markersize=15,
                          label=f'Measured: {measured:.2f} Hz', zorder=5)
        self.ax_bands.axvline(measured, color='red', linestyle='--', alpha=0.7)

        # Add text annotation
        if status == "PASS":
            result_text = f"PASS\nMeasured: {measured:.2f} Hz\nExpected: {expected_min:.1f}-{expected_max:.1f} Hz"
        else:
            result_text = f"FAIL\nMeasured: {measured:.2f} Hz\nExpected: {expected_min:.1f}-{expected_max:.1f} Hz\nDeviation: {metrics['deviation']:.2f} Hz"

        self.ax_bands.text(0.98, 0.95, result_text, transform=self.ax_bands.transAxes,
                          fontsize=10, verticalalignment='top', horizontalalignment='right',
                          fontfamily='monospace',
                          bbox=dict(boxstyle='round', facecolor=expected_color, alpha=0.3))

        self.ax_bands.set_xlim(0, 15)
        self.ax_bands.set_ylim(-0.5, 0.5)
        self.ax_bands.set_yticks([])
        self.ax_bands.set_xlabel('Frequency (Hz)')
        self.ax_bands.set_title('Fig 4.3 - Input/Output Validation', fontweight='bold')
        self.ax_bands.grid(True, alpha=0.3, axis='x')
        self.ax_bands.legend(fontsize=8, loc='upper left')

        # Draw all canvases (MATLAB-style separate figures)
        for canvas in self.canvases:
            canvas.draw()

        # Print to console
        print("\n" + "="*70)
        print("INPUT-OUTPUT VALIDATION RESULTS")
        print("="*70)
        print(f"\nVALIDATION:")
        print(f"  Expected Range: {metrics['expected_min']:.1f} - {metrics['expected_max']:.1f} Hz")
        print(f"  Measured Freq:  {metrics['dominant_freq']:.2f} Hz")
        print(f"  Status:         {metrics['validation_status']}")
        if metrics['deviation'] > 0:
            print(f"  Deviation:      {metrics['deviation']:.2f} Hz")
        print(f"\nACCELEROMETER METRICS:")
        print(f"  Dominant Axis:  {metrics['max_axis']}")
        print(f"  Axis RMS:       {metrics['axis_rms']:.4f} m/s²")
        print(f"  Resultant RMS:  {metrics['accel_rms']:.4f} m/s²")
        print(f"  Max Amplitude:  {metrics['accel_max']:.4f} m/s²")
        print(f"\nFREQUENCY ANALYSIS:")
        print(f"  Dominant Freq:  {metrics['dominant_freq']:.2f} Hz")
        print(f"  Peak PSD:       {metrics['peak_power_density']:.6f} m²/s⁴/Hz")
        print(f"  Total Power:    {metrics['total_power']:.6f} m²/s⁴")
        print("="*70 + "\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = TremorAnalyzerResearch(root)
    root.mainloop()
