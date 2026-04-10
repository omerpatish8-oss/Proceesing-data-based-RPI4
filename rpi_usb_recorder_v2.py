#!/usr/bin/env python3
"""
ESP32 USB Serial Recorder v3
Improvements:
- ESP32 error event handling (sensor stuck, resets, connection loss)
- Error logging per cycle
- Connection timeout detection
- Data validation (4 columns)
- Metadata tracking (sensor resets, data quality)
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
CONNECTION_TIMEOUT = 5.0  # Seconds - alert if no data received
EXPECTED_COLUMNS = 4      # Timestamp,Ax,Ay,Az

# ─────────────────────────────────────────────────────────────
# Module-level state shared with sys_manager.py
# ─────────────────────────────────────────────────────────────
# True only while samples are actively flowing from the ESP32 (between
# START_RECORDING/RESUME_CYCLE and the matching PAUSE_CYCLE/END_RECORDING).
# sys_manager.start_analyzer() reads this flag to decide whether the analyzer
# can be launched — it must NOT be launched while a cycle is mid-capture
# (the CSV is still being written), but it IS safe between cycles.
is_actively_recording = False
# Path of the most recently completed cycle CSV (for display / convenience).
last_completed_cycle_file = None

def create_output_folder():
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"📁 Created folder: {OUTPUT_FOLDER}/")

def log_event(log_file, event_type, message):
    """Log events to error/event log file"""
    if log_file:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file.write(f"[{timestamp}] {event_type}: {message}\n")
        log_file.flush()

def validate_data_line(line):
    """Validate CSV data line format (4 columns expected)"""
    try:
        parts = line.split(',')
        if len(parts) != EXPECTED_COLUMNS:
            return False, f"Expected {EXPECTED_COLUMNS} columns, got {len(parts)}"

        # Verify first column is numeric timestamp
        timestamp = int(parts[0])
        if timestamp < 0:
            return False, "Negative timestamp"

        # Verify sensor values are numeric
        for i in range(1, EXPECTED_COLUMNS):
            float(parts[i])

        return True, None
    except ValueError as e:
        return False, f"Parse error: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"

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
    global is_actively_recording, last_completed_cycle_file

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
    log_file = None
    log_filename = None
    data_count = 0
    last_timestamp = 0

    # Error tracking
    sensor_resets = 0
    error_count = 0
    validation_errors = 0
    last_data_time = time.time()  # For timeout detection

    # Metadata for CSV header
    cycle_metadata = {
        'start_time': None,
        'sensor_resets': 0,
        'errors': 0,
        'validation_errors': 0
    }
    
    try:
        while True:
            # Connection timeout detection
            if recording and not paused:
                elapsed_since_data = time.time() - last_data_time
                if elapsed_since_data > CONNECTION_TIMEOUT:
                    warning_msg = f"⚠️  WARNING: No data received for {elapsed_since_data:.1f}s!"
                    print(warning_msg)
                    if log_file:
                        log_event(log_file, "WARNING", f"Connection timeout - no data for {elapsed_since_data:.1f}s")
                    error_count += 1
                    last_data_time = time.time()  # Reset to avoid spam

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
                    is_actively_recording = True
                    continue
                
                # ═══════════════════════════════════
                # New cycle detection (FIXED!)
                # ═══════════════════════════════════
                if "CYCLE," in line and recording:
                    try:
                        cycle_num = int(line.split(',')[1])
                    except:
                        cycle_num = current_cycle + 1
                    
                    # Only create NEW file if cycle number changed!
                    if cycle_num != current_cycle:
                        current_cycle = cycle_num

                        # Close old files if exist
                        if csv_file:
                            csv_file.close()
                            print(f"   (Closed previous CSV file)")
                        if log_file:
                            log_file.close()
                            print(f"   (Closed previous log file)")

                        # Reset metadata
                        cycle_metadata = {
                            'start_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'sensor_resets': 0,
                            'errors': 0,
                            'validation_errors': 0
                        }
                        sensor_resets = 0
                        error_count = 0
                        validation_errors = 0

                        # Create new files
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        csv_filename = f"{OUTPUT_FOLDER}/tremor_cycle{current_cycle}_{timestamp}.csv"
                        log_filename = f"{OUTPUT_FOLDER}/tremor_cycle{current_cycle}_{timestamp}.log"

                        csv_file = open(csv_filename, 'w')
                        log_file = open(log_filename, 'w')

                        # Write CSV metadata header
                        csv_file.write(f"# Cycle: {current_cycle}\n")
                        csv_file.write(f"# Start Time: {cycle_metadata['start_time']}\n")
                        csv_file.write(f"# Sample Rate: 100 Hz\n")
                        csv_file.write(f"# Format: Timestamp(ms),Ax(m/s²),Ay(m/s²),Az(m/s²)\n")

                        log_event(log_file, "INFO", f"Cycle {current_cycle} started")

                        print(f"\n📝 Recording to: {csv_filename}")
                        print(f"📄 Log file: {log_filename}")
                        print(f"   Cycle: {current_cycle} | Rate: 100 Hz")
                        print(f"   (Pause/Resume will use SAME file)\n")
                    else:
                        # Same cycle - keep using existing file
                        print(f"   (Continuing cycle {current_cycle} in same file)")

                    continue

                # ═══════════════════════════════════
                # ESP32 Error Events
                # ═══════════════════════════════════
                if "ERROR_SENSOR_STUCK" in line:
                    error_msg = "🚨 ESP32: Sensor freeze detected (15 constant samples)"
                    print(error_msg)
                    if log_file:
                        log_event(log_file, "ERROR", "Sensor stuck - 15 constant samples detected")
                    error_count += 1
                    continue

                if "ERROR_SENSOR_LOST" in line:
                    error_msg = "🚨 ESP32: Sensor connection lost"
                    print(error_msg)
                    if log_file:
                        log_event(log_file, "ERROR", "Sensor connection lost")
                    error_count += 1
                    continue

                if "ERROR_READ_FAILED" in line:
                    error_msg = "🚨 ESP32: Sensor read failed"
                    print(error_msg)
                    if log_file:
                        log_event(log_file, "ERROR", "Sensor read failed")
                    error_count += 1
                    continue

                if "SENSOR_RESET," in line:
                    try:
                        reset_count = int(line.split(',')[1])
                        sensor_resets = reset_count
                        cycle_metadata['sensor_resets'] = sensor_resets
                        print(f"🔄 ESP32: Sensor reset #{reset_count}")
                        if log_file:
                            log_event(log_file, "RESET", f"Sensor reset #{reset_count}")
                    except:
                        pass
                    continue

                if "SENSOR_RESET_OK" in line:
                    print("✅ ESP32: Sensor reset successful")
                    if log_file:
                        log_event(log_file, "INFO", "Sensor reset successful")
                    continue

                if "SENSOR_RESET_FAILED" in line:
                    print("❌ ESP32: Sensor reset FAILED")
                    if log_file:
                        log_event(log_file, "CRITICAL", "Sensor reset FAILED")
                    error_count += 1
                    continue

                if "RESETS," in line:
                    try:
                        total_resets = int(line.split(',')[1])
                        print(f"📊 Total sensor resets this cycle: {total_resets}")
                        if log_file:
                            log_event(log_file, "INFO", f"Total sensor resets: {total_resets}")
                    except:
                        pass
                    continue

                # ═══════════════════════════════════
                # Pause (don't close file!)
                # ═══════════════════════════════════
                if "PAUSE_CYCLE" in line:
                    paused = True
                    is_actively_recording = False
                    print(f"\n⏸️  PAUSED ({data_count} samples so far)")
                    print(f"   File stays open: {csv_filename}\n")
                    if log_file:
                        log_event(log_file, "INFO", f"Recording paused at {data_count} samples")
                    continue

                # ═══════════════════════════════════
                # Resume (continue writing to same file!)
                # ═══════════════════════════════════
                if "RESUME_CYCLE" in line:
                    paused = False
                    is_actively_recording = True
                    print(f"\n▶️  RESUMED")
                    print(f"   Continuing to: {csv_filename}\n")
                    if log_file:
                        log_event(log_file, "INFO", f"Recording resumed at {data_count} samples")
                    last_data_time = time.time()  # Reset timeout counter
                    continue
                
                # ═══════════════════════════════════
                # End recording (now close file)
                # ═══════════════════════════════════
                if "END_RECORDING" in line:
                    recording = False
                    is_actively_recording = False
                    if csv_file:
                        # Update final metadata
                        cycle_metadata['errors'] = error_count
                        cycle_metadata['validation_errors'] = validation_errors
                        cycle_metadata['sensor_resets'] = sensor_resets

                        # Write summary to log
                        if log_file:
                            log_event(log_file, "INFO", f"Recording complete - {data_count} samples")
                            log_event(log_file, "SUMMARY", f"Duration: {last_timestamp/1000:.1f}s")
                            log_event(log_file, "SUMMARY", f"Sensor resets: {sensor_resets}")
                            log_event(log_file, "SUMMARY", f"Errors: {error_count}")
                            log_event(log_file, "SUMMARY", f"Validation errors: {validation_errors}")
                            log_file.close()
                            log_file = None

                        csv_file.close()
                        last_completed_cycle_file = csv_filename
                        print(f"\n✅ Cycle {current_cycle} Complete!")
                        print(f"   Total samples: {data_count}")
                        print(f"   Duration: {last_timestamp/1000:.1f}s")
                        print(f"   Sensor resets: {sensor_resets}")
                        print(f"   Errors: {error_count}")
                        print(f"   Validation errors: {validation_errors}")
                        print(f"   CSV: {csv_filename}")
                        print(f"   Log: {log_filename}")
                        print(f"   ▶ Analyzer can now be launched on this file")
                        print("="*60 + "\n")
                        csv_file = None
                        csv_filename = None
                        log_filename = None
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
                        last_data_time = time.time()  # Reset timeout
                    # Data
                    elif line[0].isdigit():
                        # Validate data format
                        is_valid, error_msg = validate_data_line(line)
                        if not is_valid:
                            validation_errors += 1
                            print(f"⚠️  Data validation error: {error_msg}")
                            if log_file:
                                log_event(log_file, "VALIDATION_ERROR", f"{error_msg} | Line: {line[:50]}")
                            # Still write data, but flag it
                            csv_file.write(f"# INVALID: {line}\n")
                        else:
                            csv_file.write(line + '\n')

                        csv_file.flush()
                        data_count += 1
                        last_data_time = time.time()  # Reset timeout

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
        is_actively_recording = False
        if csv_file:
            csv_file.close()
            print(f"\n💾 Final save: {csv_filename}")
        if log_file:
            log_event(log_file, "INFO", "Session interrupted")
            log_file.close()
            print(f"💾 Log saved: {log_filename}")
        if ser and ser.is_open:
            ser.close()
        print("✅ Connection closed")
    
    return True

def main():
    print("\n╔════════════════════════════════════╗")
    print("║ ESP32 USB Recorder v3              ║")
    print("║ + Error handling & validation     ║")
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
