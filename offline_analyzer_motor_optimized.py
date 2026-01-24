#!/usr/bin/env python3
"""
Tremor Analysis Tool - Optimized for Motor-Holding Test Scenario
Analyzes rest tremor (PD) vs essential tremor (postural) from accelerometer data
Patient seated, holding rotating motor - gyroscope contaminated by motor rotation
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
from scipy.signal import butter, filtfilt, welch, hilbert
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import mplcursors

# ==========================================
# CONFIGURATION PARAMETERS
# ==========================================
FS = 98.0               # Actual sampling rate (from validation)
FILTER_ORDER = 4        # Butterworth filter order

# Tremor frequency bands (research-based)
FREQ_REST_LOW = 3.0     # Rest tremor (Parkinson's): 3-6 Hz
FREQ_REST_HIGH = 6.0
FREQ_ESSENTIAL_LOW = 6.0   # Essential tremor: 6-12 Hz
FREQ_ESSENTIAL_HIGH = 12.0

# PSD parameters
WINDOW_SEC = 4          # Welch window size (seconds)
PSD_OVERLAP = 0.5       # 50% overlap

# Tremor detection thresholds
TREMOR_POWER_THRESHOLD = 0.01  # Minimum power to detect tremor
CLASSIFICATION_RATIO = 2.0      # Power ratio for tremor type classification

# Visual styling
COL_REST = '#DC143C'        # Crimson - Rest tremor (PD)
COL_ESSENTIAL = '#4169E1'   # Royal Blue - Essential tremor
COL_MIXED = '#9370DB'       # Medium Purple - Mixed
COL_ACCEL_X = '#FF6347'     # Tomato
COL_ACCEL_Y = '#32CD32'     # Lime Green
COL_ACCEL_Z = '#1E90FF'     # Dodger Blue

class TremorAnalyzerMotor:
    def __init__(self, root):
        self.root = root
        self.root.title("Tremor Analyzer - Motor Test Optimized (Rest vs Essential)")
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
        """Create comprehensive analysis dashboard"""
        # Main canvas frame
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create figure with subplots
        self.fig = plt.figure(figsize=(16, 10))
        gs = self.fig.add_gridspec(4, 3, hspace=0.35, wspace=0.3)

        # Row 1: Raw accelerometer axes (X, Y, Z)
        self.ax_raw_x = self.fig.add_subplot(gs[0, 0])
        self.ax_raw_y = self.fig.add_subplot(gs[0, 1])
        self.ax_raw_z = self.fig.add_subplot(gs[0, 2])

        # Row 2: Filtered tremor signals (Rest band 3-6 Hz)
        self.ax_rest_x = self.fig.add_subplot(gs[1, 0])
        self.ax_rest_y = self.fig.add_subplot(gs[1, 1])
        self.ax_rest_z = self.fig.add_subplot(gs[1, 2])

        # Row 3: Filtered tremor signals (Essential band 6-12 Hz)
        self.ax_ess_x = self.fig.add_subplot(gs[2, 0])
        self.ax_ess_y = self.fig.add_subplot(gs[2, 1])
        self.ax_ess_z = self.fig.add_subplot(gs[2, 2])

        # Row 4: PSD analysis and summary
        self.ax_psd_x = self.fig.add_subplot(gs[3, 0])
        self.ax_psd_y = self.fig.add_subplot(gs[3, 1])
        self.ax_psd_z = self.fig.add_subplot(gs[3, 2])

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
        for ax in [self.ax_raw_x, self.ax_raw_y, self.ax_raw_z,
                   self.ax_rest_x, self.ax_rest_y, self.ax_rest_z,
                   self.ax_ess_x, self.ax_ess_y, self.ax_ess_z,
                   self.ax_psd_x, self.ax_psd_y, self.ax_psd_z]:
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
        """Main tremor analysis pipeline"""
        # Extract accelerometer data
        ax = self.data['Ax']
        ay = self.data['Ay']
        az = self.data['Az']
        t = self.data['Timestamp'] / 1000.0  # Convert to seconds

        # Step 1: Remove DC offset (gravity + bias)
        ax_clean = ax - np.mean(ax)
        ay_clean = ay - np.mean(ay)
        az_clean = az - np.mean(az)

        # Step 2: Create filters
        nyquist = 0.5 * FS

        # Rest tremor filter (3-6 Hz - Parkinson's)
        b_rest, a_rest = butter(FILTER_ORDER,
                                [FREQ_REST_LOW/nyquist, FREQ_REST_HIGH/nyquist],
                                btype='band')

        # Essential tremor filter (6-12 Hz)
        b_ess, a_ess = butter(FILTER_ORDER,
                              [FREQ_ESSENTIAL_LOW/nyquist, FREQ_ESSENTIAL_HIGH/nyquist],
                              btype='band')

        # Step 3: Apply filters to each axis
        # Rest tremor band (3-6 Hz)
        rest_x = filtfilt(b_rest, a_rest, ax_clean)
        rest_y = filtfilt(b_rest, a_rest, ay_clean)
        rest_z = filtfilt(b_rest, a_rest, az_clean)

        # Essential tremor band (6-12 Hz)
        ess_x = filtfilt(b_ess, a_ess, ax_clean)
        ess_y = filtfilt(b_ess, a_ess, ay_clean)
        ess_z = filtfilt(b_ess, a_ess, az_clean)

        # Step 4: Calculate PSDs
        psd_data = {}
        for axis_name, signal in [('X', ax_clean), ('Y', ay_clean), ('Z', az_clean)]:
            nperseg = min(len(signal), int(FS * WINDOW_SEC))
            noverlap = int(nperseg * PSD_OVERLAP)
            f, psd = welch(signal, FS, nperseg=nperseg, noverlap=noverlap)
            psd_data[axis_name] = {'freq': f, 'psd': psd}

        # Step 5: Analyze tremor characteristics
        tremor_metrics = self.analyze_tremor_metrics(
            rest_x, rest_y, rest_z,
            ess_x, ess_y, ess_z,
            psd_data
        )

        # Step 6: Visualize results
        self.plot_analysis(
            t, ax, ay, az,
            rest_x, rest_y, rest_z,
            ess_x, ess_y, ess_z,
            psd_data,
            tremor_metrics
        )

    def analyze_tremor_metrics(self, rest_x, rest_y, rest_z,
                                ess_x, ess_y, ess_z, psd_data):
        """Calculate tremor quantification metrics"""
        metrics = {}

        # Calculate RMS amplitude for each axis and band
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

        # Calculate total power in each band
        metrics['rest_power_total'] = sum(metrics['rest_rms'].values())
        metrics['ess_power_total'] = sum(metrics['ess_rms'].values())

        # Find dominant frequency per axis from PSD
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

        # Calculate power in specific frequency bands from PSD
        for axis in ['X', 'Y', 'Z']:
            f = psd_data[axis]['freq']
            psd = psd_data[axis]['psd']

            # Rest tremor power (3-6 Hz)
            rest_mask = (f >= FREQ_REST_LOW) & (f <= FREQ_REST_HIGH)
            metrics['rest_rms'][f'{axis}_psd_power'] = np.sum(psd[rest_mask])

            # Essential tremor power (6-12 Hz)
            ess_mask = (f >= FREQ_ESSENTIAL_LOW) & (f <= FREQ_ESSENTIAL_HIGH)
            metrics['ess_rms'][f'{axis}_psd_power'] = np.sum(psd[ess_mask])

        # Classify tremor type based on power ratio
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

        # Update UI
        self.lbl_tremor_type.config(text=f"Type: {metrics['tremor_type']}")
        self.lbl_confidence.config(text=f"Confidence: {metrics['confidence']}")

        # Color-code tremor type
        if "Rest" in metrics['tremor_type']:
            self.lbl_tremor_type.config(foreground=COL_REST)
        elif "Essential" in metrics['tremor_type']:
            self.lbl_tremor_type.config(foreground=COL_ESSENTIAL)
        elif "Mixed" in metrics['tremor_type']:
            self.lbl_tremor_type.config(foreground=COL_MIXED)
        else:
            self.lbl_tremor_type.config(foreground="gray")

        return metrics

    def plot_analysis(self, t, ax, ay, az,
                     rest_x, rest_y, rest_z,
                     ess_x, ess_y, ess_z,
                     psd_data, metrics):
        """Plot comprehensive analysis results"""

        # Row 1: Raw accelerometer signals
        for ax_plot, signal, title, color in [
            (self.ax_raw_x, ax, 'X-axis (Lateral)', COL_ACCEL_X),
            (self.ax_raw_y, ay, 'Y-axis (Anterior-Posterior)', COL_ACCEL_Y),
            (self.ax_raw_z, az, 'Z-axis (Vertical)', COL_ACCEL_Z)
        ]:
            ax_plot.clear()
            ax_plot.plot(t, signal, color=color, linewidth=0.8, alpha=0.7)
            ax_plot.set_title(f'Raw Accelerometer - {title}', fontweight='bold')
            ax_plot.set_ylabel('Accel (m/s²)')
            ax_plot.grid(True, alpha=0.3)
            ax_plot.margins(x=0)

        # Row 2: Rest tremor band (3-6 Hz)
        for ax_plot, signal, axis_name, color in [
            (self.ax_rest_x, rest_x, 'X', COL_ACCEL_X),
            (self.ax_rest_y, rest_y, 'Y', COL_ACCEL_Y),
            (self.ax_rest_z, rest_z, 'Z', COL_ACCEL_Z)
        ]:
            ax_plot.clear()
            ax_plot.plot(t, signal, color=color, linewidth=1.2)
            rms = metrics['rest_rms'][axis_name]
            ax_plot.set_title(f'Rest Tremor (3-6 Hz) - {axis_name} | RMS: {rms:.4f} m/s²',
                            fontweight='bold')
            ax_plot.set_ylabel('Filtered (m/s²)')
            ax_plot.grid(True, alpha=0.3)
            ax_plot.margins(x=0)

            # Add envelope
            envelope = np.abs(hilbert(signal))
            ax_plot.plot(t, envelope, '--', color=color, alpha=0.4, linewidth=0.8)
            ax_plot.plot(t, -envelope, '--', color=color, alpha=0.4, linewidth=0.8)

        # Row 3: Essential tremor band (6-12 Hz)
        for ax_plot, signal, axis_name, color in [
            (self.ax_ess_x, ess_x, 'X', COL_ACCEL_X),
            (self.ax_ess_y, ess_y, 'Y', COL_ACCEL_Y),
            (self.ax_ess_z, ess_z, 'Z', COL_ACCEL_Z)
        ]:
            ax_plot.clear()
            ax_plot.plot(t, signal, color=color, linewidth=1.2)
            rms = metrics['ess_rms'][axis_name]
            ax_plot.set_title(f'Essential Tremor (6-12 Hz) - {axis_name} | RMS: {rms:.4f} m/s²',
                            fontweight='bold')
            ax_plot.set_ylabel('Filtered (m/s²)')
            ax_plot.set_xlabel('Time (s)')
            ax_plot.grid(True, alpha=0.3)
            ax_plot.margins(x=0)

            # Add envelope
            envelope = np.abs(hilbert(signal))
            ax_plot.plot(t, envelope, '--', color=color, alpha=0.4, linewidth=0.8)
            ax_plot.plot(t, -envelope, '--', color=color, alpha=0.4, linewidth=0.8)

        # Row 4: PSD analysis
        for ax_plot, axis_name, color in [
            (self.ax_psd_x, 'X', COL_ACCEL_X),
            (self.ax_psd_y, 'Y', COL_ACCEL_Y),
            (self.ax_psd_z, 'Z', COL_ACCEL_Z)
        ]:
            ax_plot.clear()

            f = psd_data[axis_name]['freq']
            psd = psd_data[axis_name]['psd']
            psd_db = 10 * np.log10(psd + 1e-12)

            # Plot PSD
            ax_plot.plot(f, psd_db, color='black', linewidth=1.2)

            # Highlight tremor bands
            ax_plot.fill_between(f, psd_db,
                                where=((f >= FREQ_REST_LOW) & (f <= FREQ_REST_HIGH)),
                                color=COL_REST, alpha=0.3, label='Rest (3-6 Hz)')
            ax_plot.fill_between(f, psd_db,
                                where=((f >= FREQ_ESSENTIAL_LOW) & (f <= FREQ_ESSENTIAL_HIGH)),
                                color=COL_ESSENTIAL, alpha=0.3, label='Essential (6-12 Hz)')

            # Mark dominant frequency
            dom_freq = metrics['dominant_freq'][axis_name]
            if dom_freq > 0:
                dom_psd = 10 * np.log10(metrics['peak_power'][axis_name] + 1e-12)
                ax_plot.plot(dom_freq, dom_psd, 'o', color=color, markersize=8,
                           label=f'Peak: {dom_freq:.2f} Hz')

            ax_plot.set_title(f'Power Spectral Density - {axis_name} axis',
                            fontweight='bold')
            ax_plot.set_ylabel('Power (dB)')
            ax_plot.set_xlabel('Frequency (Hz)')
            ax_plot.set_xlim(0, 15)
            ax_plot.grid(True, alpha=0.3)
            ax_plot.legend(loc='upper right', fontsize=8)

        self.canvas.draw()

        # Print metrics to console
        self.print_metrics(metrics)

    def print_metrics(self, metrics):
        """Print tremor metrics to console"""
        print("\n" + "="*70)
        print("TREMOR ANALYSIS RESULTS")
        print("="*70)

        print(f"\nTremor Classification: {metrics['tremor_type']}")
        print(f"Confidence: {metrics['confidence']}")

        print(f"\nRest Tremor Band (3-6 Hz) - RMS Amplitude:")
        for axis in ['X', 'Y', 'Z']:
            print(f"  {axis}-axis: {metrics['rest_rms'][axis]:.4f} m/s²")
        print(f"  Total Power: {metrics['rest_power_total']:.4f}")

        print(f"\nEssential Tremor Band (6-12 Hz) - RMS Amplitude:")
        for axis in ['X', 'Y', 'Z']:
            print(f"  {axis}-axis: {metrics['ess_rms'][axis]:.4f} m/s²")
        print(f"  Total Power: {metrics['ess_power_total']:.4f}")

        print(f"\nDominant Frequencies:")
        for axis in ['X', 'Y', 'Z']:
            print(f"  {axis}-axis: {metrics['dominant_freq'][axis]:.2f} Hz")

        print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = TremorAnalyzerMotor(root)
    root.mainloop()
