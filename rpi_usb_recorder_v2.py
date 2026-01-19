#!/usr/bin/env python3
"""
ESP32 USB Serial Recorder v2
Fixed: One CSV per cycle (handles pause/resume correctly)
"""

import serial
import serial.tools.list_ports
import datetime
import sys
import os
import time

# CONFIG
DEFAULT_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200
OUTPUT_FOLDER = 'tremor_data'

def create_output_folder():
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"📁 Created folder: {OUTPUT_FOLDER}/")

def find_port():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("❌ No serial ports found!")
        return None
    
    print("\n📍 Available ports:")
    for i, port in enumerate(ports, 1):
        print(f"   {i}. {port.device} - {port.description}")
    
    if len(ports) == 1:
        print(f"\n✅ Auto-selected: {ports[0].device}")
        return ports[0].device
    
    return DEFAULT_PORT

def safe_serial_open(port, baud, timeout=2):
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            timeout=timeout
        )
        time.sleep(2)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        return ser
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Try: sudo chmod 666 " + port)
        return None

def record_data(port):
    print(f"\n📡 Connecting to {port}...")
    
    ser = safe_serial_open(port, BAUD_RATE)
    if not ser:
        return False
    
    print("✅ Connected!")
    print("\n🎬 Waiting for ESP32 to start recording...")
    print("="*60)
    
    recording = False
    paused = False
    current_cycle = 0  # Track current cycle number
    csv_file = None
    csv_filename = None
    data_count = 0
    last_timestamp = 0
    
    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if not line:
                    continue
                
                # Print non-data lines
                if not (line[0].isdigit() and ',' in line):
                    print(line)
                
                # ═══════════════════════════════════
                # Start recording
                # ═══════════════════════════════════
                if "START_RECORDING" in line:
                    recording = True
                    paused = False
                    data_count = 0
                    continue
                
                # ═══════════════════════════════════
                # New cycle detection (FIXED!)
                # ═══════════════════════════════════
                if "CYCLE" in line and recording:
                    try:
                        cycle_num = int(line.split(',')[1])
                    except:
                        cycle_num = current_cycle + 1
                    
                    # Only create NEW file if cycle number changed!
                    if cycle_num != current_cycle:
                        current_cycle = cycle_num
                        
                        # Close old file if exists
                        if csv_file:
                            csv_file.close()
                            print(f"   (Closed previous file)")
                        
                        # Create new file
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        csv_filename = f"{OUTPUT_FOLDER}/tremor_cycle{current_cycle}_{timestamp}.csv"
                        csv_file = open(csv_filename, 'w')
                        
                        print(f"\n📝 Recording to: {csv_filename}")
                        print(f"   Cycle: {current_cycle} | Rate: 100 Hz")
                        print(f"   (Pause/Resume will use SAME file)\n")
                    else:
                        # Same cycle - keep using existing file
                        print(f"   (Continuing cycle {current_cycle} in same file)")
                    
                    continue
                
                # ═══════════════════════════════════
                # Pause (don't close file!)
                # ═══════════════════════════════════
                if "PAUSE_CYCLE" in line:
                    paused = True
                    print(f"\n⏸️  PAUSED ({data_count} samples so far)")
                    print(f"   File stays open: {csv_filename}\n")
                    continue
                
                # ═══════════════════════════════════
                # Resume (continue writing to same file!)
                # ═══════════════════════════════════
                if "RESUME_CYCLE" in line:
                    paused = False
                    print(f"\n▶️  RESUMED")
                    print(f"   Continuing to: {csv_filename}\n")
                    continue
                
                # ═══════════════════════════════════
                # End recording (now close file)
                # ═══════════════════════════════════
                if "END_RECORDING" in line:
                    recording = False
                    if csv_file:
                        csv_file.close()
                        print(f"\n✅ Cycle {current_cycle} Complete!")
                        print(f"   Total samples: {data_count}")
                        print(f"   Duration: {last_timestamp/1000:.1f}s")
                        print(f"   File: {csv_filename}")
                        print("="*60 + "\n")
                        csv_file = None
                        csv_filename = None
                    continue
                
                # ═══════════════════════════════════
                # All done
                # ═══════════════════════════════════
                if "ALL_COMPLETE" in line:
                    print("\n🎉 All cycles complete!")
                    break
                
                # ═══════════════════════════════════
                # Save data (even during pause/resume!)
                # ═══════════════════════════════════
                if recording and not paused and csv_file and ',' in line:
                    # Header
                    if line.startswith("Timestamp"):
                        csv_file.write(line + '\n')
                        csv_file.flush()
                    # Data
                    elif line[0].isdigit():
                        csv_file.write(line + '\n')
                        csv_file.flush()
                        data_count += 1
                        
                        try:
                            last_timestamp = int(line.split(',')[0])
                        except:
                            pass
                        
                        # Progress every second
                        if data_count % 100 == 0:
                            print(f"   📊 {data_count:5d} samples | {last_timestamp/1000:6.1f}s")
            else:
                time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopped by user")
    
    finally:
        if csv_file:
            csv_file.close()
            print(f"\n💾 Final save: {csv_filename}")
        if ser and ser.is_open:
            ser.close()
        print("✅ Connection closed")
    
    return True

def main():
    print("\n╔════════════════════════════════════╗")
    print("║ ESP32 USB Recorder v2              ║")
    print("║ Fixed: 1 CSV per cycle!           ║")
    print("╚════════════════════════════════════╝")
    
    create_output_folder()
    
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = find_port()
        if not port:
            port = DEFAULT_PORT
    
    print(f"\n📍 Using port: {port}")
    record_data(port)

if __name__ == "__main__":
    main()
