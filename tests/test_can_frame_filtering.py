import queue
import tempfile
import unittest
from pathlib import Path

import can
import numpy as np

from toucan_plot.utils.loaders import can_log_load_worker

DBC_TEXT = '''VERSION ""

NS_ :
    SIG_VALTYPE_

BS_:

BU_: Inverter

BO_ 2566871279 Feedback: 8 Inverter
 SG_ w_M : 32|32@1- (1,0) [0|0] "" Inverter

SIG_VALTYPE_ 2566871279 w_M : 1;
'''


class CanFrameFilteringTests(unittest.TestCase):
    def load_frames(self, frames):
        with tempfile.TemporaryDirectory() as temp_dir:
            dbc_path = Path(temp_dir) / "signals.dbc"
            blf_path = Path(temp_dir) / "recording.blf"
            dbc_path.write_text(DBC_TEXT, encoding="utf-8")
            with can.BLFWriter(blf_path) as writer:
                for timestamp, data, flags in frames:
                    writer.on_message_received(can.Message(
                        timestamp=timestamp,
                        arbitration_id=0x18FF58EF,
                        is_extended_id=True,
                        data=bytes.fromhex(data),
                        **flags,
                    ))
            messages = queue.Queue()
            can_log_load_worker(str(blf_path), [str(dbc_path)], messages)
            result = []
            while not messages.empty():
                result.append(messages.get_nowait())
            return result

    def test_error_frames_do_not_create_float_spikes_or_shift_time_origin(self):
        messages = self.load_frames([
            (1_700_000_000.0, "00000000830c00f4", {"is_error_frame": True}),
            (1_700_000_001.0, "0000000000002041", {}),  # 10.0
            (1_700_000_001.5, "00000000830c00f4", {"is_error_frame": True}),
            (1_700_000_002.0, "000000000000a041", {}),  # 20.0
        ])
        self.assertEqual([], [m for m in messages if m[0] == "error"])
        _, columns, time_origin = next(m[1] for m in messages if m[0] == "result")
        self.assertEqual(1_700_000_001.0, time_origin)
        np.testing.assert_array_equal([0.0, 1.0], columns["Time"])
        np.testing.assert_array_equal([10.0, 20.0], columns["Feedback.w_M"])

    def test_remote_frames_do_not_create_signal_samples(self):
        messages = self.load_frames([
            (1_700_000_000.0, "0000000000002041", {}),
            (1_700_000_000.5, "0000000000000000", {"is_remote_frame": True}),
            (1_700_000_001.0, "000000000000a041", {}),
        ])
        self.assertEqual([], [m for m in messages if m[0] == "error"])
        _, columns, _ = next(m[1] for m in messages if m[0] == "result")
        np.testing.assert_array_equal([0.0, 1.0], columns["Time"])
        np.testing.assert_array_equal([10.0, 20.0], columns["Feedback.w_M"])

    def test_only_error_or_remote_frames_produce_no_decoded_signals(self):
        for flag in ("is_error_frame", "is_remote_frame"):
            with self.subTest(flag=flag):
                messages = self.load_frames([
                    (1_700_000_000.0, "00000000830c00f4", {flag: True}),
                ])
                self.assertFalse(any(m[0] == "result" for m in messages))
                self.assertTrue(any(m[0] == "error" for m in messages))


if __name__ == "__main__":
    unittest.main()
