#!/usr/bin/env python3
"""
Data Quality Validation Script
Per README protocol - validates tremor data CSV files
"""

import sys
import os
from datetime import datetime
from collections import Counter

# Configuration per README
EXPECTED_COLUMNS = 7
EXPECTED_SAMPLE_RATE_HZ = 100
EXPECTED_INTERVAL_MS = 10  # 1000ms / 100Hz = 10ms
INTERVAL_TOLERANCE_MS = 5  # Allow ±5ms variance
MAX_STUCK_COUNT = 15  # Freeze detection threshold
STUCK_THRESHOLD = 0.001  # m/s² threshold for detecting frozen sensor
EXPECTED_DURATION_S = 120  # Expected recording duration
EXPECTED_SAMPLES = EXPECTED_DURATION_S * EXPECTED_SAMPLE_RATE_HZ  # 12,000

class DataValidator:
    def __init__(self, csv_path):
        self.csv_path = csv_path
        self.filename = os.path.basename(csv_path)
        self.errors = []
        self.warnings = []
        self.info = []

        # Metrics
        self.total_samples = 0
        self.invalid_lines = 0
        self.validation_errors = []
        self.timestamp_gaps = []
        self.freeze_events = []
        self.metadata = {}

    def log_error(self, message):
        self.errors.append(message)

    def log_warning(self, message):
        self.warnings.append(message)

    def log_info(self, message):
        self.info.append(message)

    def parse_metadata(self, lines):
        """Extract metadata from CSV header"""
        for line in lines:
            if line.startswith('# Cycle:'):
                self.metadata['cycle'] = line.split(':')[1].strip()
            elif line.startswith('# Start Time:'):
                self.metadata['start_time'] = line.split(':', 1)[1].strip()
            elif line.startswith('# Sample Rate:'):
                rate = line.split(':')[1].strip()
                self.metadata['sample_rate'] = rate
                if '100 Hz' not in rate:
                    self.log_warning(f"Sample rate is {rate}, expected 100 Hz")

    def validate_data_line(self, line, line_num):
        """Validate a single CSV data line per README protocol"""
        parts = line.strip().split(',')

        # Check column count
        if len(parts) != EXPECTED_COLUMNS:
            return False, f"Line {line_num}: Expected {EXPECTED_COLUMNS} columns, got {len(parts)}"

        # Validate timestamp (must be positive integer)
        try:
            timestamp = int(parts[0])
            if timestamp < 0:
                return False, f"Line {line_num}: Timestamp must be positive, got {timestamp}"
        except ValueError:
            return False, f"Line {line_num}: Timestamp must be integer, got '{parts[0]}'"

        # Validate all sensor values are numeric
        try:
            ax, ay, az = float(parts[1]), float(parts[2]), float(parts[3])
            gx, gy, gz = float(parts[4]), float(parts[5]), float(parts[6])
        except ValueError as e:
            return False, f"Line {line_num}: Non-numeric sensor value - {e}"

        return True, None

    def detect_sensor_freeze(self, data):
        """Detect sensor freeze: 15 consecutive identical readings"""
        if len(data) < MAX_STUCK_COUNT:
            return

        for i in range(len(data) - MAX_STUCK_COUNT + 1):
            # Check if next 15 samples are identical (within threshold)
            is_stuck = True
            base_ax, base_ay, base_az = data[i][1:4]

            for j in range(1, MAX_STUCK_COUNT):
                ax, ay, az = data[i+j][1:4]
                if (abs(ax - base_ax) > STUCK_THRESHOLD or
                    abs(ay - base_ay) > STUCK_THRESHOLD or
                    abs(az - base_az) > STUCK_THRESHOLD):
                    is_stuck = False
                    break

            if is_stuck:
                timestamp = data[i][0]
                self.freeze_events.append({
                    'timestamp_ms': timestamp,
                    'sample_index': i,
                    'values': (base_ax, base_ay, base_az)
                })
                self.log_error(f"SENSOR FREEZE detected at {timestamp}ms: {MAX_STUCK_COUNT} consecutive identical readings")

    def check_timestamp_consistency(self, data):
        """Check for consistent 10ms intervals between samples"""
        intervals = []
        large_gaps = []

        for i in range(1, len(data)):
            interval = data[i][0] - data[i-1][0]
            intervals.append(interval)

            # Flag large gaps (more than tolerance)
            if abs(interval - EXPECTED_INTERVAL_MS) > INTERVAL_TOLERANCE_MS:
                large_gaps.append({
                    'sample': i,
                    'timestamp': data[i][0],
                    'interval_ms': interval,
                    'expected_ms': EXPECTED_INTERVAL_MS
                })

        if intervals:
            mean_interval = sum(intervals) / len(intervals)
            min_interval = min(intervals)
            max_interval = max(intervals)

            self.log_info(f"Timestamp intervals: mean={mean_interval:.2f}ms, min={min_interval}ms, max={max_interval}ms (expected={EXPECTED_INTERVAL_MS}ms)")

            # Check if mean is within tolerance
            if abs(mean_interval - EXPECTED_INTERVAL_MS) > INTERVAL_TOLERANCE_MS:
                self.log_error(f"Mean interval {mean_interval:.2f}ms exceeds tolerance (expected {EXPECTED_INTERVAL_MS}±{INTERVAL_TOLERANCE_MS}ms)")

            # Report large gaps
            if large_gaps:
                self.log_warning(f"Found {len(large_gaps)} timestamp intervals outside tolerance")
                self.timestamp_gaps = large_gaps[:10]  # Keep first 10 for reporting

    def validate(self):
        """Main validation function per README protocol"""
        print(f"\n{'='*70}")
        print(f"VALIDATING: {self.filename}")
        print(f"{'='*70}\n")

        if not os.path.exists(self.csv_path):
            self.log_error(f"File not found: {self.csv_path}")
            return False

        # Read file
        try:
            with open(self.csv_path, 'r') as f:
                lines = f.readlines()
        except Exception as e:
            self.log_error(f"Failed to read file: {e}")
            return False

        # Parse metadata
        header_lines = [l for l in lines if l.startswith('#')]
        self.parse_metadata(header_lines)

        # Find CSV header
        csv_header_idx = None
        for i, line in enumerate(lines):
            if line.startswith('Timestamp,'):
                csv_header_idx = i
                break

        if csv_header_idx is None:
            self.log_error("No CSV header found (expected 'Timestamp,Ax,Ay,Az,Gx,Gy,Gz')")
            return False

        # Validate header format
        expected_header = "Timestamp,Ax,Ay,Az,Gx,Gy,Gz"
        actual_header = lines[csv_header_idx].strip()
        if actual_header != expected_header:
            self.log_error(f"Invalid CSV header: got '{actual_header}', expected '{expected_header}'")

        # Process data lines
        data_lines = lines[csv_header_idx + 1:]
        valid_data = []

        for i, line in enumerate(data_lines, start=csv_header_idx + 2):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Check for invalid data markers
            if line.startswith('# INVALID:'):
                self.invalid_lines += 1
                self.validation_errors.append(f"Line {i}: Marked as invalid - {line}")
                continue

            # Validate data line
            is_valid, error_msg = self.validate_data_line(line, i)

            if not is_valid:
                self.invalid_lines += 1
                self.validation_errors.append(error_msg)
                continue

            # Parse valid data
            parts = line.split(',')
            timestamp = int(parts[0])
            ax, ay, az = float(parts[1]), float(parts[2]), float(parts[3])
            gx, gy, gz = float(parts[4]), float(parts[5]), float(parts[6])

            valid_data.append([timestamp, ax, ay, az, gx, gy, gz])
            self.total_samples += 1

        # Check sample count
        duration_s = valid_data[-1][0] / 1000.0 if valid_data else 0
        self.log_info(f"Total valid samples: {self.total_samples}")
        self.log_info(f"Recording duration: {duration_s:.1f}s (expected: {EXPECTED_DURATION_S}s)")

        if self.total_samples < EXPECTED_SAMPLES - 100:
            self.log_warning(f"Sample count {self.total_samples} is significantly less than expected {EXPECTED_SAMPLES}")
        elif abs(self.total_samples - EXPECTED_SAMPLES) > 10:
            self.log_warning(f"Sample count {self.total_samples} differs from expected {EXPECTED_SAMPLES}")

        # Check timestamp consistency
        if valid_data:
            self.check_timestamp_consistency(valid_data)

        # Detect sensor freeze
        if valid_data:
            self.detect_sensor_freeze(valid_data)

        # Check for corresponding log file
        log_path = self.csv_path.replace('.csv', '.log')
        if not os.path.exists(log_path):
            self.log_warning(f"No corresponding log file found: {os.path.basename(log_path)}")

        return True

    def print_report(self):
        """Print validation report"""
        print("\n" + "─"*70)
        print("METADATA")
        print("─"*70)
        if self.metadata:
            for key, value in self.metadata.items():
                print(f"  {key.replace('_', ' ').title()}: {value}")
        else:
            print("  No metadata found")

        print("\n" + "─"*70)
        print("VALIDATION SUMMARY")
        print("─"*70)
        print(f"  Total Valid Samples: {self.total_samples}")
        print(f"  Invalid Lines: {self.invalid_lines}")
        print(f"  Validation Errors: {len(self.validation_errors)}")
        print(f"  Sensor Freeze Events: {len(self.freeze_events)}")
        print(f"  Timestamp Gaps: {len(self.timestamp_gaps)}")

        print("\n" + "─"*70)
        print("INFO MESSAGES")
        print("─"*70)
        if self.info:
            for msg in self.info:
                print(f"  ℹ️  {msg}")
        else:
            print("  None")

        print("\n" + "─"*70)
        print("WARNINGS")
        print("─"*70)
        if self.warnings:
            for msg in self.warnings:
                print(f"  ⚠️  {msg}")
        else:
            print("  ✅ No warnings")

        print("\n" + "─"*70)
        print("ERRORS")
        print("─"*70)
        if self.errors:
            for msg in self.errors:
                print(f"  ❌ {msg}")
        else:
            print("  ✅ No errors")

        # Show validation errors (first 5)
        if self.validation_errors:
            print("\n" + "─"*70)
            print("VALIDATION ERRORS (First 5)")
            print("─"*70)
            for err in self.validation_errors[:5]:
                print(f"  {err}")
            if len(self.validation_errors) > 5:
                print(f"  ... and {len(self.validation_errors) - 5} more")

        # Show timestamp gaps (first 5)
        if self.timestamp_gaps:
            print("\n" + "─"*70)
            print("LARGE TIMESTAMP GAPS (First 5)")
            print("─"*70)
            for gap in self.timestamp_gaps[:5]:
                print(f"  Sample {gap['sample']} at {gap['timestamp']}ms: interval={gap['interval_ms']}ms (expected={gap['expected_ms']}ms)")

        # Show freeze events
        if self.freeze_events:
            print("\n" + "─"*70)
            print("SENSOR FREEZE EVENTS")
            print("─"*70)
            for event in self.freeze_events:
                print(f"  At {event['timestamp_ms']}ms (sample {event['sample_index']}): Ax,Ay,Az = {event['values']}")

        print("\n" + "─"*70)
        print("OVERALL STATUS")
        print("─"*70)

        if not self.errors and not self.validation_errors and not self.freeze_events:
            print("  ✅ PASS - Data quality is excellent")
        elif not self.errors and not self.validation_errors:
            print("  ⚠️  PASS with warnings - Check warnings above")
        else:
            print("  ❌ FAIL - Critical errors found")

        print("="*70 + "\n")


def main():
    """Main validation function"""
    print("\n" + "="*70)
    print("DATA QUALITY VALIDATION TOOL")
    print("Per README Protocol - Tremor Data Acquisition System")
    print("="*70)

    # Find CSV files
    csv_files = [
        '/home/user/Proceesing-data-based-RPI4/tremor_cycle1_20260121_141523.csv',
        '/home/user/Proceesing-data-based-RPI4/tremor_cycle1_20260121_160502.csv'
    ]

    # Filter existing files
    csv_files = [f for f in csv_files if os.path.exists(f)]

    if not csv_files:
        print("\n❌ No CSV files found!")
        return 1

    print(f"\nFound {len(csv_files)} CSV file(s) to validate\n")

    # Validate each file
    all_passed = True
    validators = []

    for csv_file in csv_files:
        validator = DataValidator(csv_file)
        validator.validate()
        validator.print_report()
        validators.append(validator)

        if validator.errors or validator.validation_errors or validator.freeze_events:
            all_passed = False

    # Overall summary
    print("\n" + "="*70)
    print("OVERALL VALIDATION SUMMARY")
    print("="*70)

    total_samples = sum(v.total_samples for v in validators)
    total_errors = sum(len(v.errors) + len(v.validation_errors) for v in validators)
    total_warnings = sum(len(v.warnings) for v in validators)
    total_freezes = sum(len(v.freeze_events) for v in validators)

    print(f"  Files validated: {len(validators)}")
    print(f"  Total samples: {total_samples}")
    print(f"  Total errors: {total_errors}")
    print(f"  Total warnings: {total_warnings}")
    print(f"  Total freeze events: {total_freezes}")

    if all_passed:
        print("\n  ✅ ALL FILES PASSED VALIDATION")
    else:
        print("\n  ❌ SOME FILES FAILED VALIDATION")

    print("="*70 + "\n")

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
