import os
import csv
import numpy as np
import can
import cantools

def detect_delimiter(path):
    with open(path, 'r') as f:
        header = f.readline()
        if header.find(";") != -1:
            return ";"
        if header.find(",") != -1:
            return ","
    return ";"


def csv_load_worker(path, queue):
    """Multiprocessing worker for CSV loading. Sends progress via queue."""
    try:
        queue.put(('progress', 5, 'Reading file...'))
        with open(path, 'r', newline='') as f:
            reader = csv.reader(f, delimiter=detect_delimiter(path))
            headers = next(reader)
            headers = [h.strip() for h in headers]
            rows = list(reader)

        if not headers or not rows:
            queue.put(('error', 'File is empty or has no data rows.'))
            return

        queue.put(('progress', 20, 'Building columns...'))
        num_cols = len(headers)
        columns = {}
        for col_idx in range(num_cols):
            values = []
            for row in rows:
                if col_idx < len(row):
                    try:
                        values.append(float(row[col_idx]))
                    except ValueError:
                        values.append(float('nan'))
                else:
                    values.append(float('nan'))
            columns[headers[col_idx]] = np.array(values)
            pct = 20 + int(70 * (col_idx + 1) / num_cols)
            queue.put(('progress', pct, f'Processing column {col_idx + 1}/{num_cols}...'))

        queue.put(('progress', 95, 'Finalizing...'))
        x_col = None
        for candidate in ('Time', 'timestamp'):
            if candidate in columns:
                x_col = candidate
                break
        if x_col is None:
            x_col = headers[0]

        queue.put(('result', (x_col, columns)))
    except Exception as e:
        queue.put(('error', str(e)))


def _can_reader(path):
    """Return the appropriate python-can reader for the file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.trc':
        return can.TRCReader(path)
    if ext == '.asc':
        return can.ASCReader(path)
    return can.BLFReader(path)


def can_log_load_worker(blf_path, dbc_paths, queue):
    """Multiprocessing worker for CAN log loading (BLF/TRC). Sends progress via queue."""
    try:
        queue.put(('progress', 5, 'Loading DBC files...'))
        db = cantools.database.Database()
        for dbc_path in dbc_paths:
            db.add_dbc_file(dbc_path)

        queue.put(('progress', 10, 'Reading CAN messages...'))
        signal_data = {}
        msg_count = 0

        with _can_reader(blf_path) as reader:
            for msg in reader:
                try:
                    db_msg = db.get_message_by_frame_id(msg.arbitration_id)
                except KeyError:
                    msg_count += 1
                    continue
                try:
                    decoded = db_msg.decode(msg.data, decode_choices=False)
                except Exception:
                    msg_count += 1
                    continue
                t = msg.timestamp
                for signal_name, value in decoded.items():
                    full_name = f"{db_msg.name}.{signal_name}"
                    if full_name not in signal_data:
                        signal_data[full_name] = []
                    signal_data[full_name].append((t, float(value)))
                msg_count += 1
                if msg_count % 5000 == 0:
                    queue.put(('progress', -1, f'Reading messages... ({msg_count} processed)'))

        if not signal_data:
            queue.put(('error', 'No CAN messages could be decoded with the provided DBC file(s).'))
            return

        queue.put(('progress', 60, f'Building time index ({msg_count} messages)...'))
        all_timestamps = set()
        for pairs in signal_data.values():
            for t, _ in pairs:
                all_timestamps.add(t)
        all_timestamps = sorted(all_timestamps)

        t0 = all_timestamps[0] if all_timestamps else 0.0
        x_array = np.array([t - t0 for t in all_timestamps])
        time_index = {t: i for i, t in enumerate(all_timestamps)}

        queue.put(('progress', 70, 'Building signal arrays...'))
        all_columns = {'Time': x_array}
        sorted_names = sorted(signal_data.keys())
        total_signals = len(sorted_names)
        for sig_idx, full_name in enumerate(sorted_names):
            pairs = signal_data[full_name]
            data = np.full(len(x_array), np.nan)
            for t, val in pairs:
                data[time_index[t]] = val
            # Forward-fill NaNs with last known value
            last = np.nan
            for i in range(len(data)):
                if np.isnan(data[i]):
                    data[i] = last
                else:
                    last = data[i]
            all_columns[full_name] = data
            pct = 70 + int(25 * (sig_idx + 1) / total_signals)
            if (sig_idx + 1) % 10 == 0 or sig_idx == total_signals - 1:
                queue.put(('progress', pct, f'Processing signal {sig_idx + 1}/{total_signals}...'))

        queue.put(('result', ('Time', all_columns)))
    except Exception as e:
        queue.put(('error', str(e)))
