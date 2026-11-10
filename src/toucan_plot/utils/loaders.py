import csv
import os

import can
import cantools
import numpy as np
from asammdf import MDF


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
        return can.ASCReader(path, relative_timestamp=False)
    return can.BLFReader(path)


def _can_signal_name(channel, message_name, signal_name, message_channels):
    """Return a signal's display name, qualified only if its message is on several channels."""
    full_name = f"{message_name}.{signal_name}"
    if len(message_channels) > 1 and channel is not None:
        return f"CH{channel}.{full_name}"
    return full_name


def can_log_load_worker(blf_path, dbc_paths, queue):
    """Multiprocessing worker for CAN log loading (BLF/TRC). Sends progress via queue."""
    try:
        queue.put(('progress', 5, 'Loading DBC files...'))
        db = cantools.database.Database()
        for dbc_path in dbc_paths:
            db.add_dbc_file(dbc_path)

        queue.put(('progress', 10, 'Reading CAN messages...'))
        signal_data = {}
        channels_by_message = {}
        msg_count = 0
        stats = dict(decoded_frames=0, unknown_id_frames=0, decode_error_frames=0,
                     error_frames=0, remote_frames=0)
        frame_ids = set()
        channels = set()
        first_timestamp = None
        last_timestamp = None

        with _can_reader(blf_path) as reader:
            for msg in reader:
                msg_count += 1
                if msg_count % 5000 == 0:
                    queue.put(('progress', -1, f'Reading messages... ({msg_count} processed)'))
                if first_timestamp is None:
                    first_timestamp = last_timestamp = msg.timestamp
                else:
                    first_timestamp = min(first_timestamp, msg.timestamp)
                    last_timestamp = max(last_timestamp, msg.timestamp)
                if msg.channel is not None:
                    channels.add(msg.channel)
                # Error frames and remote requests do not carry valid signal data.
                if msg.is_error_frame:
                    stats['error_frames'] += 1
                    continue
                frame_ids.add((msg.arbitration_id, msg.is_extended_id))
                if msg.is_remote_frame:
                    stats['remote_frames'] += 1
                    continue
                try:
                    db_msg = db.get_message_by_frame_id(msg.arbitration_id)
                except KeyError:
                    stats['unknown_id_frames'] += 1
                    continue
                try:
                    decoded = db_msg.decode(msg.data, decode_choices=False)
                except Exception:
                    stats['decode_error_frames'] += 1
                    continue
                stats['decoded_frames'] += 1
                t = msg.timestamp
                channels_by_message.setdefault(db_msg.name, set()).add(msg.channel)
                for signal_name, value in decoded.items():
                    key = (msg.channel, db_msg.name, signal_name)
                    signal_data.setdefault(key, []).append((t, float(value)))

        if not signal_data:
            queue.put(('error', 'No CAN messages could be decoded with the provided DBC file(s).'))
            return

        # A message seen on several buses is independent traffic and must not share one trace.
        signal_data = {
            _can_signal_name(channel, message_name, signal_name, channels_by_message[message_name]): pairs
            for (channel, message_name, signal_name), pairs in signal_data.items()
        }

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
        can_samples = {}
        sorted_names = sorted(signal_data.keys())
        total_signals = len(sorted_names)
        for sig_idx, full_name in enumerate(sorted_names):
            pairs = sorted(signal_data[full_name], key=lambda pair: pair[0])
            can_samples[full_name] = (
                np.array([t - t0 for t, _ in pairs]),
                np.array([value for _, value in pairs]),
            )
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

        stats.update(total_frames=msg_count, unique_ids=len(frame_ids),
                     channels=sorted(channels), duration=last_timestamp - first_timestamp,
                     decoded_signals=total_signals)
        queue.put(('can_samples', can_samples))
        queue.put(('can_statistics', stats))
        queue.put(('result', ('Time', all_columns, t0)))
    except Exception as e:
        queue.put(('error', str(e)))


def mf4_load_worker(path, queue):
    """Multiprocessing worker for MF4 loading via asammdf. Sends progress via queue."""
    try:
        queue.put(('progress', 5, 'Opening MF4 file...'))
        mdf = MDF(path)

        queue.put(('progress', 15, 'Extracting channels...'))
        # Collect all non-empty numeric channels
        channel_names = []
        for i, group in enumerate(mdf.groups):
            for j, channel in enumerate(group.channels):
                name = channel.name
                if name and name != 't':
                    channel_names.append((name, i, j))

        if not channel_names:
            queue.put(('error', 'No channels found in MF4 file.'))
            mdf.close()
            return

        queue.put(('progress', 25, f'Processing {len(channel_names)} channels...'))
        all_columns = {}
        x_col = None
        total = len(channel_names)

        for idx, (name, group_idx, ch_idx) in enumerate(channel_names):
            try:
                sig = mdf.get(name, group=group_idx, index=ch_idx)
            except Exception:
                continue

            # Skip non-numeric or empty signals
            if sig.samples.size == 0:
                continue
            if sig.samples.ndim != 1:
                continue
            if not np.issubdtype(sig.samples.dtype, np.number):
                continue

            timestamps = sig.timestamps
            try:
                samples = sig.samples.astype(float)
            except (ValueError, TypeError):
                continue

            # Use the first valid channel's timestamps as x axis
            if x_col is None:
                x_col = 'Time'
                all_columns['Time'] = timestamps

            # If this channel's timestamps match the common time axis, use directly
            common_t = all_columns['Time']
            if len(timestamps) == len(common_t) and np.allclose(timestamps, common_t):
                all_columns[name] = samples
            else:
                # Interpolate onto the common time axis
                all_columns[name] = np.interp(common_t, timestamps, samples)

            pct = 25 + int(70 * (idx + 1) / total)
            if (idx + 1) % 20 == 0 or idx == total - 1:
                queue.put(('progress', pct, f'Processing channel {idx + 1}/{total}...'))

        mdf.close()

        if x_col is None or len(all_columns) <= 1:
            queue.put(('error', 'No numeric channels could be extracted from the MF4 file.'))
            return

        queue.put(('progress', 98, 'Finalizing...'))
        queue.put(('result', (x_col, all_columns)))
    except Exception as e:
        queue.put(('error', str(e)))


def feather_load_worker(path, queue):
    """Multiprocessing worker for Feather loading via pandas. Sends progress via queue."""
    try:
        import pandas as pd

        queue.put(('progress', 5, 'Reading Feather file...'))
        df = pd.read_feather(path)

        if df.empty:
            queue.put(('error', 'Feather file is empty or has no data rows.'))
            return

        queue.put(('progress', 30, 'Building columns...'))
        all_columns = {}
        num_cols = len(df.columns)

        x_col = None
        for candidate in ('Time', 'timestamp', 'time'):
            if candidate in df.columns:
                x_col = candidate
                break
        if x_col is None:
            x_col = df.columns[0]

        for col_idx, col_name in enumerate(df.columns):
            try:
                all_columns[col_name] = df[col_name].to_numpy(dtype=float, na_value=np.nan)
            except (ValueError, TypeError):
                continue
            pct = 30 + int(65 * (col_idx + 1) / num_cols)
            queue.put(('progress', pct, f'Processing column {col_idx + 1}/{num_cols}...'))

        queue.put(('progress', 98, 'Finalizing...'))
        queue.put(('result', (x_col, all_columns)))
    except Exception as e:
        queue.put(('error', str(e)))
