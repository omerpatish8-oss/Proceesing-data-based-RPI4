#!/usr/bin/env python3
"""
Tremor Analysis Tool - Educational Layout with Filter Verification
Shows complete signal processing chain: Filter design → Application → Results
Focuses on Y-axis (strongest tremor) with Bode plots and residual analysis
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
TREMOR_POWER_THRESHOLD = 0.01
CLASSIFICATION_RATIO = 2.0

# Visual styling
COL_REST = '#DC143C'        # Crimson - Rest tremor
COL_ESSENTIAL = '#4169E1'   # Royal Blue - Essential tremor
COL_RAW = '#2F4F4F'         # Dark Slate Gray - Raw signal
COL_FILTERED = '#FF6347'    # Tomato - Filtered signal
COL_RESIDUAL = '#9370DB'    # Medium Purple - Residual

class TremorAnalyzerEducational:
    def __init__(self, root):
        self.root = root
        self.root.title("Tremor Analyzer - Educational (Filter Verification + Signal Analysis)")
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
        """Create educational analysis dashboard"""
        # Main canvas frame
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create figure with custom layout
        self.fig = plt.figure(figsize=(16, 10))
        gs = GridSpec(4, 3, figure=self.fig, hspace=0.4, wspace=0.3)

        # Row 1: FILTER DESIGN VERIFICATION
        self.ax_bode_mag = self.fig.add_subplot(gs[0, 0])
        self.ax_bode_phase = self.fig.add_subplot(gs[0, 1])
        self.ax_psd_comparison = self.fig.add_subplot(gs[0, 2])

        # Row 2: Y-AXIS TIME DOMAIN ANALYSIS
        self.ax_raw = self.fig.add_subplot(gs[1, 0])
        self.ax_filtered = self.fig.add_subplot(gs[1, 1])
        self.ax_residual = self.fig.add_subplot(gs[1, 2])

        # Row 3: FREQUENCY DOMAIN ANALYSIS
        self.ax_psd_raw = self.fig.add_subplot(gs[2, 0])
        self.ax_psd_filtered = self.fig.add_subplot(gs[2, 1])
        self.ax_psd_residual = self.fig.add_subplot(gs[2, 2])

        # Row 4: CLINICAL ANALYSIS
        self.ax_spectrogram = self.fig.add_subplot(gs[3, 0])
        self.ax_envelope = self.fig.add_subplot(gs[3, 1])
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
        for ax in [self.ax_bode_mag, self.ax_bode_phase, self.ax_psd_comparison,
                   self.ax_raw, self.ax_filtered, self.ax_residual,
                   self.ax_psd_raw, self.ax_psd_filtered, self.ax_psd_residual,
                   self.ax_spectrogram, self.ax_envelope, self.ax_metrics]:
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
        """Main tremor analysis pipeline - Educational approach"""

        # Focus on Y-axis (strongest tremor based on test results)
        ay = self.data['Ay']
        t = self.data['Timestamp'] / 1000.0  # Convert to seconds

        # Remove DC offset (gravity + bias)
        ay_clean = ay - np.mean(ay)

        # Create filters
        nyquist = 0.5 * FS

        # Combined tremor filter (3-12 Hz) for main analysis
        b_tremor, a_tremor = butter(FILTER_ORDER,
                                    [FREQ_REST_LOW/nyquist, FREQ_ESSENTIAL_HIGH/nyquist],
                                    btype='band')

        # Rest tremor filter (3-6 Hz)
        b_rest, a_rest = butter(FILTER_ORDER,
                                [FREQ_REST_LOW/nyquist, FREQ_REST_HIGH/nyquist],
                                btype='band')

        # Essential tremor filter (6-12 Hz)
        b_ess, a_ess = butter(FILTER_ORDER,
                              [FREQ_ESSENTIAL_LOW/nyquist, FREQ_ESSENTIAL_HIGH/nyquist],
                              btype='band')

        # Apply main tremor filter
        ay_filtered = filtfilt(b_tremor, a_tremor, ay_clean)

        # Calculate residual (what was filtered OUT)
        ay_residual = ay_clean - ay_filtered

        # Apply band-specific filters for classification
        rest_y = filtfilt(b_rest, a_rest, ay_clean)
        ess_y = filtfilt(b_ess, a_ess, ay_clean)

        # Calculate PSDs
        nperseg = min(len(ay_clean), int(FS * WINDOW_SEC))
        noverlap = int(nperseg * PSD_OVERLAP)

        f_raw, psd_raw = welch(ay_clean, FS, nperseg=nperseg, noverlap=noverlap)
        f_filt, psd_filt = welch(ay_filtered, FS, nperseg=nperseg, noverlap=noverlap)
        f_resid, psd_resid = welch(ay_residual, FS, nperseg=nperseg, noverlap=noverlap)

        # Calculate metrics
        metrics = self.calculate_metrics(ay_clean, ay_filtered, rest_y, ess_y,
                                        f_raw, psd_raw)

        # Visualize everything
        self.plot_educational_analysis(
            t, ay_clean, ay_filtered, ay_residual,
            rest_y, ess_y,
            f_raw, psd_raw, f_filt, psd_filt, f_resid, psd_resid,
            b_tremor, a_tremor, b_rest, a_rest, b_ess, a_ess,
            metrics
        )

    def calculate_metrics(self, raw, filtered, rest, ess, freq, psd):
        """Calculate tremor metrics"""
        metrics = {}

        # RMS amplitudes
        metrics['rms_raw'] = np.sqrt(np.mean(raw**2))
        metrics['rms_filtered'] = np.sqrt(np.mean(filtered**2))
        metrics['rms_rest'] = np.sqrt(np.mean(rest**2))
        metrics['rms_ess'] = np.sqrt(np.mean(ess**2))

        # Powers
        metrics['power_rest'] = metrics['rms_rest']
        metrics['power_ess'] = metrics['rms_ess']

        # Dominant frequency
        tremor_mask = (freq >= 3) & (freq <= 12)
        if np.sum(tremor_mask) > 0:
            peak_idx = np.argmax(psd[tremor_mask])
            metrics['dominant_freq'] = freq[tremor_mask][peak_idx]
            metrics['peak_power'] = psd[tremor_mask][peak_idx]
        else:
            metrics['dominant_freq'] = 0
            metrics['peak_power'] = 0

        # Classification
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

    def plot_educational_analysis(self, t, raw, filtered, residual,
                                  rest, ess,
                                  f_raw, psd_raw, f_filt, psd_filt, f_resid, psd_resid,
                                  b_tremor, a_tremor, b_rest, a_rest, b_ess, a_ess,
                                  metrics):
        """Plot educational analysis with filter verification"""

        # ============================================================
        # ROW 1: FILTER DESIGN VERIFICATION
        # ============================================================

        # Bode Magnitude Plot
        self.ax_bode_mag.clear()

        # Calculate frequency responses
        w, h_tremor = freqz(b_tremor, a_tremor, worN=4096, fs=FS)
        _, h_rest = freqz(b_rest, a_rest, worN=4096, fs=FS)
        _, h_ess = freqz(b_ess, a_ess, worN=4096, fs=FS)

        # Plot magnitude responses
        self.ax_bode_mag.plot(w, 20*np.log10(abs(h_tremor)), color='purple',
                             linewidth=2, label='Combined (3-12 Hz)')
        self.ax_bode_mag.plot(w, 20*np.log10(abs(h_rest)), color=COL_REST,
                             linewidth=1.5, linestyle='--', label='Rest (3-6 Hz)')
        self.ax_bode_mag.plot(w, 20*np.log10(abs(h_ess)), color=COL_ESSENTIAL,
                             linewidth=1.5, linestyle='--', label='Essential (6-12 Hz)')

        # Mark cutoff frequencies
        self.ax_bode_mag.axvline(FREQ_REST_LOW, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_mag.axvline(FREQ_REST_HIGH, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_mag.axvline(FREQ_ESSENTIAL_HIGH, color='blue', linestyle=':', alpha=0.5)

        self.ax_bode_mag.set_title('Filter Magnitude Response (Bode Plot)', fontweight='bold')
        self.ax_bode_mag.set_xlabel('Frequency (Hz)')
        self.ax_bode_mag.set_ylabel('Magnitude (dB)')
        self.ax_bode_mag.set_xlim(0, 20)
        self.ax_bode_mag.set_ylim(-60, 5)
        self.ax_bode_mag.grid(True, alpha=0.3)
        self.ax_bode_mag.legend(fontsize=8)

        # Bode Phase Plot
        self.ax_bode_phase.clear()
        self.ax_bode_phase.plot(w, np.unwrap(np.angle(h_tremor)) * 180/np.pi,
                               color='purple', linewidth=2, label='Combined (3-12 Hz)')
        self.ax_bode_phase.plot(w, np.unwrap(np.angle(h_rest)) * 180/np.pi,
                               color=COL_REST, linewidth=1.5, linestyle='--', label='Rest (3-6 Hz)')

        self.ax_bode_phase.axvline(FREQ_REST_LOW, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_phase.axvline(FREQ_REST_HIGH, color='red', linestyle=':', alpha=0.5)
        self.ax_bode_phase.axvline(FREQ_ESSENTIAL_HIGH, color='blue', linestyle=':', alpha=0.5)

        self.ax_bode_phase.set_title('Filter Phase Response', fontweight='bold')
        self.ax_bode_phase.set_xlabel('Frequency (Hz)')
        self.ax_bode_phase.set_ylabel('Phase (degrees)')
        self.ax_bode_phase.set_xlim(0, 20)
        self.ax_bode_phase.grid(True, alpha=0.3)
        self.ax_bode_phase.legend(fontsize=8)

        # PSD Before/After Comparison
        self.ax_psd_comparison.clear()
        psd_raw_db = 10*np.log10(psd_raw + 1e-12)
        psd_filt_db = 10*np.log10(psd_filt + 1e-12)

        self.ax_psd_comparison.plot(f_raw, psd_raw_db, color=COL_RAW,
                                   linewidth=1.5, label='Before filtering', alpha=0.7)
        self.ax_psd_comparison.plot(f_filt, psd_filt_db, color=COL_FILTERED,
                                   linewidth=2, label='After filtering (3-12 Hz)')

        # Highlight tremor bands
        self.ax_psd_comparison.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH,
                                      color=COL_REST, alpha=0.2, label='Rest band')
        self.ax_psd_comparison.axvspan(FREQ_ESSENTIAL_LOW, FREQ_ESSENTIAL_HIGH,
                                      color=COL_ESSENTIAL, alpha=0.2, label='Essential band')

        self.ax_psd_comparison.set_title('PSD: Before vs After Filtering', fontweight='bold')
        self.ax_psd_comparison.set_xlabel('Frequency (Hz)')
        self.ax_psd_comparison.set_ylabel('Power (dB)')
        self.ax_psd_comparison.set_xlim(0, 20)
        self.ax_psd_comparison.grid(True, alpha=0.3)
        self.ax_psd_comparison.legend(fontsize=7)

        # ============================================================
        # ROW 2: Y-AXIS TIME DOMAIN ANALYSIS
        # ============================================================

        # Raw signal
        self.ax_raw.clear()
        self.ax_raw.plot(t, raw, color=COL_RAW, linewidth=1, alpha=0.8)
        self.ax_raw.set_title(f'Raw Y-axis Signal | RMS: {metrics["rms_raw"]:.4f} m/s²',
                             fontweight='bold')
        self.ax_raw.set_ylabel('Accel (m/s²)')
        self.ax_raw.grid(True, alpha=0.3)
        self.ax_raw.margins(x=0)

        # Filtered signal (3-12 Hz)
        self.ax_filtered.clear()
        self.ax_filtered.plot(t, filtered, color=COL_FILTERED, linewidth=1.2)

        # Add envelope
        envelope = np.abs(hilbert(filtered))
        self.ax_filtered.plot(t, envelope, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)
        self.ax_filtered.plot(t, -envelope, '--', color=COL_FILTERED, alpha=0.4, linewidth=0.8)

        self.ax_filtered.set_title(f'Filtered Signal (3-12 Hz) | RMS: {metrics["rms_filtered"]:.4f} m/s²',
                                  fontweight='bold')
        self.ax_filtered.set_ylabel('Filtered (m/s²)')
        self.ax_filtered.grid(True, alpha=0.3)
        self.ax_filtered.margins(x=0)

        # Residual (what was filtered OUT)
        self.ax_residual.clear()
        self.ax_residual.plot(t, residual, color=COL_RESIDUAL, linewidth=1)
        rms_residual = np.sqrt(np.mean(residual**2))
        self.ax_residual.set_title(f'Residual (Filtered OUT) | RMS: {rms_residual:.4f} m/s²',
                                  fontweight='bold')
        self.ax_residual.set_ylabel('Residual (m/s²)')
        self.ax_residual.grid(True, alpha=0.3)
        self.ax_residual.margins(x=0)

        # ============================================================
        # ROW 3: FREQUENCY DOMAIN ANALYSIS
        # ============================================================

        # PSD of raw signal
        self.ax_psd_raw.clear()
        self.ax_psd_raw.plot(f_raw, psd_raw_db, color=COL_RAW, linewidth=1.2)
        self.ax_psd_raw.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH, color=COL_REST, alpha=0.2)
        self.ax_psd_raw.axvspan(FREQ_ESSENTIAL_LOW, FREQ_ESSENTIAL_HIGH, color=COL_ESSENTIAL, alpha=0.2)
        self.ax_psd_raw.set_title('PSD: Raw Signal (All Frequencies)', fontweight='bold')
        self.ax_psd_raw.set_ylabel('Power (dB)')
        self.ax_psd_raw.set_xlim(0, 20)
        self.ax_psd_raw.grid(True, alpha=0.3)

        # PSD of filtered signal
        self.ax_psd_filtered.clear()
        self.ax_psd_filtered.plot(f_filt, psd_filt_db, color=COL_FILTERED, linewidth=1.2)
        self.ax_psd_filtered.axvspan(FREQ_REST_LOW, FREQ_REST_HIGH, color=COL_REST, alpha=0.2)
        self.ax_psd_filtered.axvspan(FREQ_ESSENTIAL_LOW, FREQ_ESSENTIAL_HIGH, color=COL_ESSENTIAL, alpha=0.2)

        # Mark dominant frequency
        if metrics['dominant_freq'] > 0:
            dom_psd_db = 10*np.log10(metrics['peak_power'] + 1e-12)
            self.ax_psd_filtered.plot(metrics['dominant_freq'], dom_psd_db, 'o',
                                     color='red', markersize=8,
                                     label=f'Peak: {metrics["dominant_freq"]:.2f} Hz')

        self.ax_psd_filtered.set_title('PSD: Filtered Signal (3-12 Hz Only)', fontweight='bold')
        self.ax_psd_filtered.set_ylabel('Power (dB)')
        self.ax_psd_filtered.set_xlim(0, 20)
        self.ax_psd_filtered.grid(True, alpha=0.3)
        self.ax_psd_filtered.legend(fontsize=8)

        # PSD of residual
        self.ax_psd_residual.clear()
        self.ax_psd_residual.plot(f_resid, 10*np.log10(psd_resid + 1e-12),
                                 color=COL_RESIDUAL, linewidth=1.2)
        self.ax_psd_residual.set_title('PSD: Residual (What Was Removed)', fontweight='bold')
        self.ax_psd_residual.set_ylabel('Power (dB)')
        self.ax_psd_residual.set_xlabel('Frequency (Hz)')
        self.ax_psd_residual.set_xlim(0, 20)
        self.ax_psd_residual.grid(True, alpha=0.3)

        # ============================================================
        # ROW 4: CLINICAL ANALYSIS
        # ============================================================

        # Spectrogram
        self.ax_spectrogram.clear()
        # Limit to first 30 seconds for clarity
        nperseg_spec = int(FS * 2)  # 2-second windows
        noverlap_spec = int(nperseg_spec * 0.9)  # 90% overlap

        f_spec, t_spec, Sxx = self.ax_spectrogram.specgram(
            filtered[:int(30*FS)], Fs=FS,
            NFFT=nperseg_spec, noverlap=noverlap_spec,
            cmap='jet'
        )

        self.ax_spectrogram.set_title('Spectrogram: Tremor Evolution (First 30s)', fontweight='bold')
        self.ax_spectrogram.set_ylabel('Frequency (Hz)')
        self.ax_spectrogram.set_xlabel('Time (s)')
        self.ax_spectrogram.set_ylim(0, 15)

        # Tremor envelope
        self.ax_envelope.clear()
        envelope = np.abs(hilbert(filtered))
        self.ax_envelope.plot(t, envelope, color=COL_FILTERED, linewidth=1.5)
        self.ax_envelope.fill_between(t, envelope, alpha=0.3, color=COL_FILTERED)
        self.ax_envelope.set_title('Tremor Intensity Over Time (Envelope)', fontweight='bold')
        self.ax_envelope.set_ylabel('Amplitude (m/s²)')
        self.ax_envelope.set_xlabel('Time (s)')
        self.ax_envelope.grid(True, alpha=0.3)
        self.ax_envelope.margins(x=0)

        # Metrics table
        self.ax_metrics.clear()
        self.ax_metrics.axis('off')

        # Create metrics text
        metrics_text = f"""
TREMOR CLASSIFICATION
{'─'*35}
Type: {metrics['tremor_type']}
Confidence: {metrics['confidence']}

AMPLITUDE ANALYSIS
{'─'*35}
Raw Signal RMS:      {metrics['rms_raw']:.4f} m/s²
Filtered RMS:        {metrics['rms_filtered']:.4f} m/s²
Rest Tremor (3-6Hz): {metrics['rms_rest']:.4f} m/s²
Essential (6-12Hz):  {metrics['rms_ess']:.4f} m/s²

FREQUENCY ANALYSIS
{'─'*35}
Dominant Freq:       {metrics['dominant_freq']:.2f} Hz
Peak Power:          {metrics['peak_power']:.6f}

POWER RATIO
{'─'*35}
Rest / Essential:    {metrics['power_rest']/metrics['power_ess']:.2f}
"""

        self.ax_metrics.text(0.05, 0.95, metrics_text,
                            transform=self.ax_metrics.transAxes,
                            fontfamily='monospace', fontsize=9,
                            verticalalignment='top')

        self.ax_metrics.set_title('Clinical Metrics Summary', fontweight='bold', loc='left')

        self.canvas.draw()

        # Print to console
        print("\n" + "="*70)
        print("TREMOR ANALYSIS RESULTS (Y-axis)")
        print("="*70)
        print(metrics_text)
        print("="*70 + "\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = TremorAnalyzerEducational(root)
    root.mainloop()
