import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import numpy as np
from scipy.signal import butter, filtfilt, welch, freqz
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import mplcursors

# ==========================================
# 1. VISUAL CONFIGURATION
# ==========================================
def set_matlab_style():
    plt.style.use('seaborn-v0_8-whitegrid')
    global COL_GYRO, COL_ACCEL, COL_FILL_GYRO, COL_FILL_ACCEL
    COL_GYRO = '#0072BD'   # Blue
    COL_ACCEL = '#D95319'  # Orange
    COL_FILL_GYRO = '#4DBEEE' 
    COL_FILL_ACCEL = '#EDB120'
    
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.size': 9,
        'axes.labelsize': 9,
        'axes.titlesize': 10,
        'axes.titleweight': 'bold',
        'lines.linewidth': 1.2,
        'figure.autolayout': True 
    })

# ==========================================
# 2. PARAMETERS
# ==========================================
FS = 100.0          
CUTOFF_LOW = 3.0    # 3Hz - 20Hz Bandpass
CUTOFF_HIGH = 20.0  
FILTER_ORDER = 4
WINDOW_SEC = 4      

class TremorAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Tremor Analysis: Full Sensor Suite (Tabs)")
        self.root.geometry("1400x950")
        
        set_matlab_style()
        
        # UI Setup
        self.setup_main_layout()
        
        # Create Two Separate Dashboards (Tabs)
        self.figs_gyro = self.create_dashboard_tab(self.tab_gyro, "Gyroscope Analysis")
        self.figs_accel = self.create_dashboard_tab(self.tab_accel, "Accelerometer Analysis")

    def setup_main_layout(self):
        # 1. Top Control Panel
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Button(control_frame, text="📂 Load CSV Data", command=self.process_data).pack(side=tk.LEFT, padx=10)
        self.lbl_status = ttk.Label(control_frame, text="Status: Ready", font=("Arial", 11))
        self.lbl_status.pack(side=tk.LEFT, padx=20)
        
        # 2. Tabs Container
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create the frames for the tabs
        self.tab_gyro = ttk.Frame(self.notebook)
        self.tab_accel = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_gyro, text="  🌀 GYROSCOPE (Rotation)  ")
        self.notebook.add(self.tab_accel, text="  🚀 ACCELEROMETER (Linear)  ")

    def create_dashboard_tab(self, parent_frame, title_prefix):
        """ Creates a full 6-plot dashboard inside a given tab/frame """
        
        # Container for Graph & Toolbar
        frame = ttk.Frame(parent_frame)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Figure Layout
        fig = plt.figure(figsize=(12, 10))
        gs = fig.add_gridspec(3, 2)
        
        axes = {
            'time_raw': fig.add_subplot(gs[0, 0]),
            'time_filt': fig.add_subplot(gs[0, 1]),
            'bode_amp': fig.add_subplot(gs[1, 0]),
            'bode_phase': fig.add_subplot(gs[1, 1]),
            'psd': fig.add_subplot(gs[2, 0]),
            'hist': fig.add_subplot(gs[2, 1])
        }
        
        plt.subplots_adjust(hspace=0.4, wspace=0.25)
        
        # Canvas
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Toolbar
        toolbar_frame = ttk.Frame(frame)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        toolbar = NavigationToolbar2Tk(canvas, toolbar_frame)
        toolbar.update()
        
        return {'fig': fig, 'canvas': canvas, 'axes': axes}

    def process_data(self):
        try:
            self.lbl_status.config(text="Processing Both Sensors...", foreground="blue")
            self.root.update()

            # 1. Load Data
            df = pd.read_csv('tremor_data.csv')
            for c in ['ax','ay','az','gx','gy','gz']: 
                df[c] = pd.to_numeric(df[c], errors='coerce')
            df.dropna(inplace=True)

            # 2. Prepare Filter
            nyquist = 0.5 * FS
            b, a = butter(FILTER_ORDER, [CUTOFF_LOW/nyquist, CUTOFF_HIGH/nyquist], btype='band')

            # 3. Process GYRO
            raw_g = np.sqrt(df['gx']**2 + df['gy']**2 + df['gz']**2)
            raw_g = raw_g - np.mean(raw_g)
            filt_g = filtfilt(b, a, raw_g)
            
            self.plot_sensor_dashboard(
                self.figs_gyro['axes'], self.figs_gyro['canvas'],
                raw_g, filt_g, b, a, 
                COL_GYRO, COL_FILL_GYRO, "Gyroscope (deg/s)"
            )

            # 4. Process ACCEL
            raw_a = np.sqrt(df['ax']**2 + df['ay']**2 + df['az']**2)
            raw_a = raw_a - np.mean(raw_a)
            filt_a = filtfilt(b, a, raw_a) # Same filter removes gravity!
            
            self.plot_sensor_dashboard(
                self.figs_accel['axes'], self.figs_accel['canvas'],
                raw_a, filt_a, b, a, 
                COL_ACCEL, COL_FILL_ACCEL, "Accelerometer (g)"
            )

            self.lbl_status.config(text="Analysis Complete ✅ (Switch Tabs to View)", foreground="green")
            mplcursors.cursor(hover=True)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def plot_sensor_dashboard(self, ax, canvas, raw, filtered, b, a, main_color, fill_color, unit_label):
        t = np.arange(len(raw)) / FS
        
        # 1. Time Raw
        ax['time_raw'].clear()
        ax['time_raw'].plot(t, raw, color='#7F7F7F', linewidth=0.8, alpha=0.6)
        ax['time_raw'].set_title(f"Raw Input")
        ax['time_raw'].set_ylabel(unit_label)
        ax['time_raw'].margins(x=0)

        # 2. Time Filtered
        ax['time_filt'].clear()
        ax['time_filt'].plot(t, filtered, color=main_color, linewidth=1.2)
        ax['time_filt'].set_title(f"Filtered Output ({CUTOFF_LOW}-{CUTOFF_HIGH} Hz)")
        ax['time_filt'].set_ylabel(unit_label)
        ax['time_filt'].margins(x=0)

        # 3. Bode Plot (Filter Response)
        w, h = freqz(b, a, worN=4096, fs=FS)
        ax['bode_amp'].clear()
        ax['bode_amp'].plot(w, 20 * np.log10(abs(h)), color='purple')
        ax['bode_amp'].set_title("Filter Amplitude Response")
        ax['bode_amp'].set_ylabel("Magnitude [dB]")
        ax['bode_amp'].set_ylim(-60, 5)
        ax['bode_amp'].axvline(CUTOFF_LOW, color='red', linestyle='--')
        ax['bode_amp'].axvline(CUTOFF_HIGH, color='red', linestyle='--')

        ax['bode_phase'].clear()
        ax['bode_phase'].plot(w, np.degrees(np.unwrap(np.angle(h))), color='green')
        ax['bode_phase'].set_title("Filter Phase Response")
        ax['bode_phase'].set_ylabel("Phase [deg]")

        # 4. PSD
        nperseg = min(len(filtered), int(FS * WINDOW_SEC))
        f, p = welch(filtered, FS, nperseg=nperseg)
        p_db = 10 * np.log10(p + 1e-10)
        pk_f = f[np.argmax(p)]
        
        ax['psd'].clear()
        ax['psd'].plot(f, p_db, color='black', linewidth=1)
        ax['psd'].fill_between(f, p_db, where=((f>=3)&(f<=7)), color=fill_color, alpha=0.5, label='Tremor Band')
        ax['psd'].plot(pk_f, p_db[np.argmax(p)], 'o', color=main_color)
        ax['psd'].set_title(f"PSD Spectrum (Peak: {pk_f:.2f} Hz)")
        ax['psd'].set_ylabel("Power [dB]")
        ax['psd'].set_xlabel("Frequency [Hz]")
        ax['psd'].set_xlim(0, 15)
        ax['psd'].legend(loc='upper right')

        # 5. Histogram
        winsize = int(FS * 1)
        step = int(FS/2)
        freqs = []
        for i in range(0, len(filtered)-winsize, step):
            seg = filtered[i:i+winsize]
            f_s, p_s = welch(seg, FS, nperseg=winsize)
            if np.max(p_s) > 0.1: freqs.append(f_s[np.argmax(p_s)])
        
        ax['hist'].clear()
        if freqs:
            ax['hist'].hist(freqs, bins=np.arange(0, 16, 1), color=main_color, alpha=0.6, edgecolor='black')
        ax['hist'].set_title("Tremor Stability")
        ax['hist'].set_ylabel("Count")
        ax['hist'].set_xlabel("Frequency [Hz]")
        ax['hist'].set_xlim(0, 15)

        canvas.draw()

if __name__ == "__main__":
    root = tk.Tk()
    app = TremorAnalyzerGUI(root)
    root.mainloop()