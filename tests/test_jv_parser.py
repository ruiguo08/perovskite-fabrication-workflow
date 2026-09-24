import statistics
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from web.jv_parser import (
    ANALYSIS_SCHEMA_VERSION,
    _flat_metrics_from_analysis,
    assign_substrates_to_groups,
    parse_jv_analysis,
    parse_jv_metrics,
)

assert ANALYSIS_SCHEMA_VERSION == 7


def multi_device_csv_with_summary(
    summaries: list[dict[str, str]],
) -> str:
    """Multi-device export whose blocks carry instrument summary info rows.

    Each entry in ``summaries`` supplies the info-row label/value pairs for one
    trace block, in addition to the standard Name row and two data rows.
    """

    merged: list[list[str]] = [[], [], []]
    for trace_index, summary in enumerate(summaries, start=1):
        direction = "Forward" if trace_index % 2 else "Reverse"
        device_index = (trace_index + 1) // 2
        label = f"A{device_index:03d} Channel 1.{direction}"
        merged[0].extend(["No.", str(trace_index), "", "", "", "", ""])
        merged[1].extend(
            ["[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", ""]
        )
        merged[2].extend(["Name", label, "0", "-2", "-20", "", ""])
        block_rows = [
            [info_label, info_value, "", "", "", "", ""]
            for info_label, info_value in summary.items()
        ] + [
            ["", "", "0.5", "-2", "-20", "", ""],
            ["", "", "1", "0", "0", "", ""],
        ]
        for row_index, cells in enumerate(block_rows, start=3):
            while len(merged) <= row_index:
                merged.append([])
            merged[row_index].extend(cells)
    return "\n".join(",".join(row) for row in merged) + "\n"


def multi_device_csv(
    currents: list[float], device_labels: list[str] | None = None
) -> str:
    rows = [[], [], [], [], []]
    for trace_index, current in enumerate(currents, start=1):
        device_index = (trace_index + 1) // 2
        device_label = (
            device_labels[device_index - 1]
            if device_labels is not None
            else f"A{device_index:03d} Channel 1"
        )
        direction = "Forward" if trace_index % 2 else "Reverse"
        rows[0].extend(["No.", str(trace_index), "", "", "", "", ""])
        rows[1].extend(
            ["[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", ""]
        )
        rows[2].extend(["Name", f"{device_label}.{direction}", "0", "-2", str(-current), "", ""])
        rows[3].extend(["", "", "0.5", "-2", str(-current), "", ""])
        rows[4].extend(["", "", "1", "0", "0", "", ""])
    return "\n".join(",".join(row) for row in rows) + "\n"


def channel_labeled_csv(
    mark: str, channels: list[int], trace_order: list[int] | None = None
) -> str:
    """Multi-device export with ``{mark} Channel {n}`` labels.

    ``trace_order`` permutes the trace blocks so tests can prove parsed
    ordinals do not depend on the order traces appear in the file.
    """

    labels = [f"{mark} Channel {channel}" for channel in channels]
    order = trace_order if trace_order is not None else list(range(len(labels)))
    rows = [[], [], [], [], []]
    for position, label_index in enumerate(order):
        trace_index = position + 1
        direction = "Forward" if trace_index % 2 else "Reverse"
        rows[0].extend(["No.", str(trace_index), "", "", "", "", ""])
        rows[1].extend(
            ["[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", ""]
        )
        rows[2].extend(
            ["Name", f"{labels[label_index]}.{direction}", "0", "-2", "-20", "", ""]
        )
        rows[3].extend(["", "", "0.5", "-2", "-20", "", ""])
        rows[4].extend(["", "", "1", "0", "0", "", ""])
    return "\n".join(",".join(row) for row in rows) + "\n"


def reorder_trace_blocks(content: str, order: list[int]) -> str:
    reordered_rows = []
    for row in content.splitlines():
        cells = row.split(",")
        blocks = [cells[index : index + 7] for index in range(0, len(cells), 7)]
        reordered_rows.append(",".join(cell for index in order for cell in blocks[index]))
    return "\n".join(reordered_rows) + "\n"


def instrument_named_csv(substrates: list[str], channels: list[int]) -> str:
    """Multi-device export whose labels name substrates without laser marks.

    Mirrors the real instrument software export: trace blocks carry wrapped
    labels like ``prefix (Control-1-1.CH_Ref.Forward(1))`` and a summary
    table repeats the bare stems with the four core metrics.
    """

    traces: list[tuple[str, int, str]] = []
    for substrate in substrates:
        for channel in channels:
            traces.append((substrate, channel, "Forward"))
            traces.append((substrate, channel, "Reverse"))
    rows: list[list[str]] = [[], [], [], [], []]
    for trace_index, (substrate, channel, direction) in enumerate(traces, start=1):
        label = f"18-1 3 ({substrate}-{channel}.CH_Ref.{direction}(1))"
        rows[0].extend(["No.", str(trace_index), "", "", "", "", ""])
        rows[1].extend(
            ["[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", ""]
        )
        rows[2].extend(["Name", label, "0", "-2", "-20", "", ""])
        rows[3].extend(["", "", "0.5", "-2", "-20", "", ""])
        rows[4].extend(["", "", "1", "0", "0", "", ""])
    rows.append(["=========="])
    rows.append(
        ["No.", "Name", "Isc (mA)", "Voc (V)", "Efficiency (%)", "Fill Factor (%)", "Jsc (mA/cm^2)"]
    )
    for substrate, channel, direction in traces:
        rows.append(
            ["1", f"{substrate}-{channel}.CH_Ref.{direction}(1)", "2.0", "1.0", "10.0", "50.0", "20.0"]
        )
    return "\n".join(",".join(row) for row in rows) + "\n"


class JVParserTests(unittest.TestCase):
    def test_instrument_named_export_preserves_names_for_manual_assignment(self) -> None:
        content = instrument_named_csv(
            ["Control-1", "Control-2", "T1-6"], [1, 2, 3, 4, 5, 6]
        ).encode("utf-8")
        analysis = parse_jv_analysis(content, source_filename="20260906.csv")

        self.assertEqual(len(analysis["substrates"]), 3)
        self.assertEqual(len(analysis["devices"]), 18)
        self.assertEqual(
            sum(len(device["traces"]) for device in analysis["devices"]), 36
        )
        self.assertEqual(
            [substrate["substrate_id"] for substrate in analysis["substrates"]],
            ["Control-1", "Control-2", "T1-6"],
        )
        self.assertEqual(
            {device["device_ordinal"] for device in analysis["devices"]
             if device["substrate_id"] == "T1-6"},
            set(range(1, 7)),
        )
        self.assertTrue(all(device["group_id"] == "" for device in analysis["devices"]))
        self.assertTrue(all(device["device_mark"] is None for device in analysis["devices"]))

    def test_extracts_voc_jsc_ff_and_pce_from_jv_csv(self) -> None:
        metrics = parse_jv_metrics(
            b"voltage,current_density\n"
            b"0.0,-20.0\n"
            b"0.5,-20.0\n"
            b"1.0,0.0\n"
        )

        self.assertAlmostEqual(metrics["voc"], 1.0)
        self.assertAlmostEqual(metrics["jsc"], 20.0)
        self.assertAlmostEqual(metrics["ff"], 0.5)
        self.assertAlmostEqual(metrics["pce"], 10.0)

    def test_rejects_csv_without_zero_current_crossing(self) -> None:
        with self.assertRaisesRegex(ValueError, "zero current"):
            parse_jv_metrics("voltage,current_density\n0,-20\n0.5,-20\n")

    def test_ignores_post_voc_points_outside_power_generating_quadrant(self) -> None:
        metrics = parse_jv_metrics(
            "voltage,current_density\n"
            "0,-20\n"
            "0.5,-20\n"
            "1,0\n"
            "1.2,20\n"
        )

        self.assertAlmostEqual(metrics["pce"], 10.0)
        self.assertAlmostEqual(metrics["ff"], 0.5)

    def test_parses_multi_device_instrument_export(self) -> None:
        content = (
            "No.,1,,,,,,No.,2,,,,,\n"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,,"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,\n"
            "Name,A001 Channel 1.Forward,0,-2,-20,,,Name,A001 Channel 1.Reverse,0,-2,-20,,\n"
            ",,0.5,-2,-20,,,,,0.5,-2,-20,,\n"
            ",,1,0,0,,,,,1,0,0,,\n"
        )
        metrics = parse_jv_metrics(content)
        analysis = parse_jv_analysis(content)

        self.assertEqual(metrics["trace_count"], 2.0)
        self.assertEqual(metrics["valid_trace_count"], 2.0)
        self.assertEqual(metrics["device_count"], 1.0)
        self.assertAlmostEqual(metrics["pce"], 10.0)
        self.assertEqual(len(analysis["devices"]), 1)
        self.assertEqual(
            [trace["direction"] for trace in analysis["devices"][0]["traces"]],
            ["forward", "reverse"],
        )
        self.assertEqual(analysis["devices"][0]["traces"][0]["points"][0], [0.0, -20.0])

    def test_groups_reordered_traces_by_physical_device_label(self) -> None:
        content = reorder_trace_blocks(
            multi_device_csv([20.0, 18.0, 15.0, 13.0]),
            [0, 2, 1, 3],
        )

        analysis = parse_jv_analysis(content)

        self.assertEqual(len(analysis["devices"]), 2)
        self.assertEqual(
            [len(device["traces"]) for device in analysis["devices"]],
            [2, 2],
        )
        self.assertEqual(
            [device["label"] for device in analysis["devices"]],
            ["A001 Channel 1", "A002 Channel 1"],
        )

    def test_assigns_physical_devices_and_calculates_group_statistics(self) -> None:
        analysis = parse_jv_analysis(
            multi_device_csv([20, 20, 21, 21, 24, 24, 25, 25])
        )
        groups = [
            {"group_id": "control", "name": "Control", "kind": "control"},
            {"group_id": "target-1", "name": "ADH", "kind": "target"},
        ]
        assignments = {
            "A001": "control",
            "A002": "control",
            "A003": "target-1",
            "A004": "target-1",
        }

        assigned = assign_substrates_to_groups(analysis, assignments, groups)

        self.assertEqual(assigned["statistics"]["groups"][0]["valid_device_count"], 2)
        self.assertAlmostEqual(
            assigned["statistics"]["groups"][1]["metrics"]["pce"]["mean"],
            12.25,
        )
        comparison = assigned["statistics"]["comparisons"][0]["metrics"]["pce"]
        self.assertAlmostEqual(comparison["mean_difference"], 2.0)
        self.assertEqual(comparison["test_method"], "exact permutation")
        self.assertIsNotNone(comparison["p_value"])
        self.assertIsNotNone(comparison["adjusted_p_value"])

    def test_extracts_short_marks_and_instrument_local_timestamp(self) -> None:
        content = (
            "No.,1,,,,,,No.,2,,,,,\n"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,,"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,\n"
            "Name,A011 Channel 1.Forward,0,-2,-20,,,Name,A011 Channel 1.Reverse,0,-2,-20,,\n"
            "Time stamp,2026/7/24 10:32,0.5,-2,-20,,,Time stamp,2026/7/24 10:33,0.5,-2,-20,,\n"
            ",,1,0,0,,,,,1,0,0,,\n"
        )

        analysis = parse_jv_analysis(content)

        self.assertEqual(analysis["devices"][0]["device_mark"], "A011")
        self.assertEqual(analysis["devices"][0]["substrate_id"], "A011")
        self.assertEqual(analysis["substrates"][0]["substrate_id"], "A011")
        self.assertEqual(
            analysis["devices"][0]["traces"][0]["measured_at"],
            "2026-07-24T10:32:00",
        )

    def test_channel_labels_preserve_mark_and_explicit_ordinals(self) -> None:
        """``A001 Channel 2`` / ``A001 Channel 5`` keep substrate mark A001 and
        carry explicit device ordinals 2 and 5 regardless of trace order."""

        for trace_order in ([0, 1], [1, 0]):
            with self.subTest(trace_order=trace_order):
                analysis = parse_jv_analysis(
                    channel_labeled_csv("A001", [2, 5], trace_order)
                )

                self.assertEqual(analysis["schema_version"], ANALYSIS_SCHEMA_VERSION)
                self.assertEqual(len(analysis["devices"]), 2)
                self.assertEqual(
                    {device["substrate_id"] for device in analysis["devices"]},
                    {"A001"},
                )
                self.assertEqual(
                    sorted(
                        device["device_ordinal"]
                        for device in analysis["devices"]
                    ),
                    [2, 5],
                )
                self.assertEqual(len(analysis["substrates"]), 1)
                self.assertEqual(
                    analysis["substrates"][0]["substrate_id"], "A001"
                )

    def test_forward_reverse_same_mark_channel_merges_into_one_device(self) -> None:
        """Forward and reverse traces of the same substrate mark + channel
        ordinal must aggregate into one device, not two."""
        # Two trace blocks with the same mark+channel, different directions.
        content = multi_device_csv(
            [20.0, 20.0], device_labels=["A001 Channel 1", "A001 Channel 1"]
        )
        analysis = parse_jv_analysis(content, source_filename="multi.csv")

        self.assertEqual(len(analysis["devices"]), 1)
        self.assertEqual(analysis["devices"][0]["device_ordinal"], 1)
        self.assertEqual(analysis["devices"][0]["substrate_id"], "A001")
        self.assertEqual(len(analysis["devices"][0]["traces"]), 2)

    def test_simple_csv_requires_filename_with_one_mark_and_one_channel(self) -> None:
        """A simple (non-multi-device) CSV only parses when the filename
        contains exactly one valid laser mark and one Channel N token."""
        simple_csv = b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n"

        # Valid: filename carries one mark + one channel.
        analysis = parse_jv_analysis(simple_csv, source_filename="A001 Channel 1.csv")
        self.assertEqual(analysis["schema_version"], ANALYSIS_SCHEMA_VERSION)
        self.assertEqual(analysis["devices"][0]["substrate_id"], "A001")
        self.assertEqual(analysis["devices"][0]["device_ordinal"], 1)

        # Rejected: no mark in filename.
        with self.assertRaisesRegex(ValueError, "exactly one substrate laser mark"):
            parse_jv_analysis(simple_csv, source_filename="sample.csv")

        # Rejected: mark but no channel.
        with self.assertRaisesRegex(ValueError, "channel"):
            parse_jv_analysis(simple_csv, source_filename="A001.csv")

        # Rejected: two channels in filename.
        with self.assertRaisesRegex(ValueError, "channel"):
            parse_jv_analysis(
                simple_csv, source_filename="A001 Channel 1 Channel 2.csv"
            )

    def test_filename_rejects_multiple_marks(self) -> None:
        """A filename with more than one laser mark token is ambiguous."""
        simple = b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n"
        with self.assertRaisesRegex(ValueError, "exactly one substrate laser mark"):
            parse_jv_analysis(simple, source_filename="A001 A002 Channel 1.csv")

    def test_filename_rejects_mark_over_9_chars(self) -> None:
        """A laser mark longer than 9 characters (1 letter + 8 digits) exceeds
        the storage limit and must be rejected."""
        simple = b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n"
        with self.assertRaisesRegex(ValueError, "exactly one substrate laser mark"):
            parse_jv_analysis(simple, source_filename="A1234567890 Channel 1.csv")

    def test_filename_rejects_mark_embedded_in_longer_token(self) -> None:
        """A laser mark must be a bounded token, not a substring of a longer
        alphanumeric run (e.g. ``XA001Y`` must not extract ``A001``)."""
        simple = b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n"
        with self.assertRaisesRegex(ValueError, "exactly one substrate laser mark"):
            parse_jv_analysis(simple, source_filename="XA001Y Channel 1.csv")

    def test_multi_device_label_rejects_multiple_marks(self) -> None:
        """A multi-device instrument label with more than one laser mark is
        ambiguous and must be rejected at parse time."""
        content = multi_device_csv(
            [20.0, 20.0], device_labels=["A001A002 Channel 1"]
        )
        with self.assertRaisesRegex(ValueError, "channel|mark"):
            parse_jv_analysis(content, source_filename="multi.csv")

    def test_multi_device_label_rejects_mark_over_9_chars(self) -> None:
        """A laser mark longer than 9 characters is invalid."""
        content = multi_device_csv(
            [20.0, 20.0], device_labels=["A1234567890 Channel 1"]
        )
        with self.assertRaisesRegex(ValueError, "channel|mark"):
            parse_jv_analysis(content, source_filename="multi.csv")

    def test_multi_device_label_with_two_marks_is_rejected(self) -> None:
        """A device label with two laser marks (e.g. ``A001 A002 Channel 1``)
        is ambiguous: the parser cannot pick the first one.  It must be
        rejected, not silently assigned to ``A001``."""
        content = multi_device_csv(
            [20.0, 20.0], device_labels=["A001 A002 Channel 1"]
        )
        with self.assertRaisesRegex(ValueError, "mark"):
            parse_jv_analysis(content, source_filename="multi.csv")

    def test_simple_csv_without_filename_is_rejected(self) -> None:
        """Without a source_filename, a simple CSV cannot establish physical
        identity and must be rejected."""
        simple_csv = b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n"
        with self.assertRaisesRegex(ValueError, "source filename"):
            parse_jv_analysis(simple_csv)

    def test_multi_device_label_without_channel_is_rejected(self) -> None:
        """A multi-device label must carry exactly one Channel N token."""
        content = multi_device_csv(
            [20.0, 20.0, 21.0, 21.0], device_labels=["A001 Channel 1", "A002"]
        )
        with self.assertRaisesRegex(ValueError, "channel"):
            parse_jv_analysis(content, source_filename="multi.csv")

    def test_multi_device_with_duplicate_channel_within_substrate_is_rejected(
        self,
    ) -> None:
        """Two distinct labels resolving to the same mark+channel are a
        duplicate physical device."""
        content = multi_device_csv(
            [20.0, 20.0, 21.0, 21.0],
            device_labels=["A001 Channel 1", "A001 Channel 01"],
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_jv_analysis(content, source_filename="dup.csv")

    def test_zero_and_negative_channel_ordinals_are_rejected(self) -> None:
        """Channel ordinals of 0 or negative are invalid physical device
        ordinals."""
        for bad_channel in (0, -1):
            with self.subTest(channel=bad_channel):
                content = channel_labeled_csv("A001", [bad_channel])
                with self.assertRaisesRegex(ValueError, "channel"):
                    parse_jv_analysis(content, source_filename="bad.csv")

    def test_one_substrate_assignment_applies_to_all_of_its_devices(self) -> None:
        content = multi_device_csv([20, 20, 21, 21], device_labels=["A011 Channel 1", "A012 Channel 1"])
        analysis = parse_jv_analysis(content)

        assigned = assign_substrates_to_groups(
            analysis,
            {"A011": "control", "A012": "control"},
            [{"group_id": "control", "name": "Control", "kind": "control"}],
        )

        self.assertEqual(len(assigned["substrates"]), 2)
        self.assertTrue(all(device["group_id"] == "control" for device in assigned["devices"]))

    def test_requires_every_substrate_to_be_assigned(self) -> None:
        analysis = parse_jv_analysis(multi_device_csv([20, 20, 21, 21]))
        groups = [{"group_id": "control", "name": "Control", "kind": "control"}]

        with self.assertRaisesRegex(ValueError, "assign substrate A002"):
            assign_substrates_to_groups(
                analysis,
                {"A001": "control"},
                groups,
            )


class InstrumentSummaryTests(unittest.TestCase):
    """Info-row metrics (the third source) and v6 trace-level storage.

    v6 stores the instrument-reported metrics directly in
    ``trace['metrics']`` with ``metric_source`` provenance; the old
    ``instrument_metrics`` side-channel is gone. When info rows carry
    partial metrics (some labels malformed), the missing ones simply stay
    absent — the summary-table section tests cover the primary source.
    """

    def test_info_row_metrics_are_captured_per_trace(self) -> None:
        content = multi_device_csv_with_summary(
            [
                {"Voc (V)": "1.02", "Jsc (mA/cm2)": "22.5", "FF (%)": "74.1", "Eff (%)": "17.0"},
                {"Voc (V)": "1.04", "Jsc (mA/cm2)": "22.1", "FF (%)": "72.1", "Eff (%)": "16.6"},
            ]
        )
        analysis = parse_jv_analysis(content)

        device = analysis["devices"][0]
        self.assertEqual(
            device["metrics"]["forward"],
            {"voc": 1.02, "jsc": 22.5, "ff": 0.741, "pce": 17.0},
        )
        self.assertEqual(
            device["metrics"]["reverse"],
            {"voc": 1.04, "jsc": 22.1, "ff": 0.721, "pce": 16.6},
        )
        self.assertEqual(device["traces"][0]["metric_source"], "info rows")

    def test_traces_without_summary_rows_recompute_from_curve(self) -> None:
        analysis = parse_jv_analysis(multi_device_csv([20, 20, 21, 21]))

        for device in analysis["devices"]:
            self.assertIsNotNone(device["metrics"])
            for trace in device["traces"]:
                self.assertEqual(trace["metric_source"], "recomputed from curve")
                self.assertIn("info", trace)

    def test_summary_rows_are_preserved_verbatim_in_info(self) -> None:
        content = multi_device_csv_with_summary(
            [
                {"Voc (V)": "1.02", "Int. (sun)": "1.00"},
                {"Voc (V)": "1.04", "Int. (sun)": "1.00"},
            ]
        )
        analysis = parse_jv_analysis(content)

        info = analysis["devices"][0]["traces"][0]["info"]
        self.assertEqual(info["Voc (V)"], "1.02")
        self.assertEqual(info["Int. (sun)"], "1.00")

    def test_malformed_summary_values_are_ignored(self) -> None:
        content = multi_device_csv_with_summary(
            [
                {"Voc (V)": "N/A", "Jsc (mA/cm2)": "22.5"},
                {"Voc (V)": "1.03", "Jsc (mA/cm2)": "22.1"},
            ]
        )
        analysis = parse_jv_analysis(content)

        device = analysis["devices"][0]
        self.assertNotIn("voc", device["metrics"]["forward"])
        self.assertEqual(device["metrics"]["forward"]["jsc"], 22.5)
        self.assertEqual(device["metrics"]["reverse"]["voc"], 1.03)


def _raw_blocks_csv(
    blocks: list[tuple[str, list[float], list[float]]],
) -> str:
    """Multi-device export with explicit per-block voltage/J sequences.

    Each block is ``(label, voltages, current_densities)``; labels carry no
    Forward/Reverse keyword so direction must come from the sweep itself.
    """

    data_rows = max(len(voltages) for _, voltages, _ in blocks)
    rows: list[list[str]] = [[] for _ in range(data_rows + 3)]
    for position, (label, voltages, current_densities) in enumerate(blocks):
        rows[0].extend(["No.", str(position + 1), "", "", ""])
        rows[1].extend(["[Information]", "", "[Volt (V)]", "[J (mA/cm^2)]", ""])
        rows[2].extend(["Name", label, "", "", ""])
        for row_index, (voltage, current_density) in enumerate(
            zip(voltages, current_densities), start=1
        ):
            rows[2 + row_index].extend(["", "", str(voltage), str(current_density), ""])
    return "\n".join(",".join(row) for row in rows) + "\n"


class IrradianceWarningTests(unittest.TestCase):
    def test_deviating_illumination_produces_analysis_warning(self) -> None:
        content = multi_device_csv_with_summary(
            [
                {"Int. (sun)": "0.85"},
                {"Int. (sun)": "0.85"},
            ]
        )
        analysis = parse_jv_analysis(content)

        self.assertEqual(len(analysis["warnings"]), 2)
        self.assertIn("0.85 sun", analysis["warnings"][0])
        self.assertEqual(analysis["devices"][0]["irradiance_sun"], 0.85)

    def test_one_sun_illumination_produces_no_warning(self) -> None:
        content = multi_device_csv_with_summary(
            [
                {"Int. (sun)": "1.00"},
                {"Int. (sun)": "1.00"},
            ]
        )
        analysis = parse_jv_analysis(content)

        self.assertEqual(analysis["warnings"], [])
        self.assertEqual(analysis["devices"][0]["irradiance_sun"], 1.0)

    def test_missing_illumination_row_stays_silent(self) -> None:
        analysis = parse_jv_analysis(multi_device_csv([20.0, 20.0]))

        self.assertEqual(analysis["warnings"], [])
        self.assertIsNone(analysis["devices"][0]["irradiance_sun"])


class VocExtractionTests(unittest.TestCase):
    def test_low_voltage_shunt_crossing_does_not_understate_voc(self) -> None:
        metrics = parse_jv_metrics(
            "voltage,current_density\n"
            "-0.1,0.0\n"
            "0.0,-20.0\n"
            "0.5,-20.0\n"
            "1.0,0.0\n"
        )

        self.assertAlmostEqual(metrics["voc"], 1.0)
        self.assertAlmostEqual(metrics["jsc"], 20.0)
        self.assertAlmostEqual(metrics["pce"], 10.0)


class ScanDirectionTests(unittest.TestCase):
    def test_direction_follows_voltage_sweep_not_block_parity(self) -> None:
        # Two rising sweeps followed by two falling sweeps on one device:
        # an even/odd heuristic would label them forward/reverse/forward/
        # reverse, fabricating a hysteresis signal.
        content = _raw_blocks_csv(
            [
                ("A001 Channel 1", [0.0, 0.5, 1.0], [-20.0, -20.0, 0.0]),
                ("A001 Channel 1", [0.0, 0.5, 1.0], [-20.0, -20.0, 0.0]),
                ("A001 Channel 1", [1.0, 0.5, 0.0], [0.0, -20.0, -20.0]),
                ("A001 Channel 1", [1.0, 0.5, 0.0], [0.0, -20.0, -20.0]),
            ]
        )

        analysis = parse_jv_analysis(content)

        directions = [
            trace["direction"] for trace in analysis["devices"][0]["traces"]
        ]
        self.assertEqual(directions, ["forward", "forward", "reverse", "reverse"])

    def test_label_keyword_still_overrides_voltage_direction(self) -> None:
        content = _raw_blocks_csv(
            [
                ("A001 Channel 1.Forward", [1.0, 0.5, 0.0], [0.0, -20.0, -20.0]),
            ]
        )

        analysis = parse_jv_analysis(content)

        self.assertEqual(
            analysis["devices"][0]["traces"][0]["direction"], "forward"
        )


class HysteresisIndexTests(unittest.TestCase):
    def test_forward_reverse_pce_divergence_is_recorded(self) -> None:
        content = multi_device_csv([20.0, 16.0])

        analysis = parse_jv_analysis(content)

        device = analysis["devices"][0]
        forward_pce = device["traces"][0]["metrics"]["pce"]
        reverse_pce = device["traces"][1]["metrics"]["pce"]
        self.assertAlmostEqual(forward_pce, 10.0)
        self.assertAlmostEqual(reverse_pce, 8.0)
        self.assertAlmostEqual(device["hysteresis_index"], (8.0 - 10.0) / 8.0)

    def test_single_direction_device_has_no_hysteresis_index(self) -> None:
        analysis = parse_jv_analysis(
            b"voltage,current_density\n0.0,-20.0\n0.5,-20.0\n1.0,0.0\n",
            source_filename="A001 Channel 1.csv",
        )

        self.assertIsNone(analysis["devices"][0]["hysteresis_index"])


class CurrentColumnUnitTests(unittest.TestCase):
    SIMPLE_CSV = (
        "voltage,current\n"
        "0.0,-1.0\n"
        "0.5,-1.0\n"
        "1.0,0.0\n"
    )

    def test_total_current_is_converted_with_device_active_area(self) -> None:
        # 1 mA over 0.05 cm2 is 20 mA/cm2, so this matches the density CSV.
        metrics = parse_jv_metrics(
            self.SIMPLE_CSV, device_active_area_cm2=0.05
        )

        self.assertAlmostEqual(metrics["voc"], 1.0)
        self.assertAlmostEqual(metrics["jsc"], 20.0)
        self.assertAlmostEqual(metrics["pce"], 10.0)

    def test_total_current_conversion_is_recorded_in_the_analysis(self) -> None:
        analysis = parse_jv_analysis(
            self.SIMPLE_CSV,
            source_filename="A001 Channel 1.csv",
            device_active_area_cm2=0.05,
        )

        conversion = analysis["unit_conversion"]
        self.assertEqual(conversion["source_column"], "current")
        self.assertEqual(conversion["source_unit"], "mA")
        self.assertEqual(conversion["device_active_area_cm2"], 0.05)
        self.assertEqual(conversion["converted_to"], "mA/cm2")
        self.assertAlmostEqual(
            analysis["devices"][0]["metrics"]["forward"]["jsc"], 20.0
        )

    def test_total_current_without_area_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "total current"):
            parse_jv_metrics(self.SIMPLE_CSV)

    def test_bare_current_column_is_not_silently_a_density(self) -> None:
        with self.assertRaisesRegex(ValueError, "total current"):
            parse_jv_analysis(
                self.SIMPLE_CSV, source_filename="A001 Channel 1.csv"
            )

    def test_density_columns_still_parse_without_area(self) -> None:
        metrics = parse_jv_metrics(
            b"voltage,current_density\n0.0,-20.0\n0.5,-20.0\n1.0,0.0\n"
        )

        self.assertAlmostEqual(metrics["jsc"], 20.0)

    def test_single_jsc_number_column_is_not_accepted_as_a_curve(self) -> None:
        with self.assertRaisesRegex(ValueError, "current-density column"):
            parse_jv_metrics(
                b"voltage,jsc\n0.0,-20.0\n0.5,-20.0\n1.0,0.0\n",
                device_active_area_cm2=0.05,
            )


class GBKEncodingTests(unittest.TestCase):
    """Instrument software on Chinese Windows exports CSVs in GBK/GB18030."""

    MULTI_DEVICE_GBK = (
        "No.,1,,,,,,No.,2,,,,,\n"
        "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,,"
        "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,\n"
        "Name,A001 Channel 1.Forward,0,-2,-20,,,"
        "Name,A001 Channel 1.Reverse,0,-2,-20,,\n"
        "Channel,CH_Ref (（I）-),0,-2,-20,,,"
        "Channel,CH_Ref (（I）-),0,-2,-20,,\n"
        ",,0.5,-2,-20,,,,,0.5,-2,-20,,\n"
        ",,1,0,0,,,,,1,0,0,,\n"
    ).encode("gb18030")

    def test_gb18030_bytes_parse_in_metrics_path(self) -> None:
        metrics = parse_jv_metrics(self.MULTI_DEVICE_GBK)

        self.assertAlmostEqual(metrics["pce"], 10.0)
        self.assertEqual(metrics["trace_count"], 2.0)
        self.assertEqual(metrics["valid_trace_count"], 2.0)

    def test_gb18030_bytes_parse_in_analysis_path(self) -> None:
        analysis = parse_jv_analysis(self.MULTI_DEVICE_GBK)

        self.assertEqual(len(analysis["devices"]), 1)
        self.assertEqual(analysis["devices"][0]["substrate_id"], "A001")
        self.assertEqual(
            analysis["devices"][0]["traces"][0]["info"].get("Channel"),
            "CH_Ref (（I）-)",
        )

    def test_utf8_bom_input_keeps_working(self) -> None:
        metrics = parse_jv_metrics(
            b"\xef\xbb\xbfvoltage,current_density\n0.0,-20.0\n0.5,-20.0\n1.0,0.0\n"
        )

        self.assertAlmostEqual(metrics["jsc"], 20.0)


class DeviceExclusionTests(unittest.TestCase):
    """Excluding flagged devices from statistics with an auditable reason."""

    def _three_device_analysis(self) -> Any:
        content = multi_device_csv(
            [20, 20, 19, 19, 21, 21],
            device_labels=["A011 Channel 1", "A012 Channel 1", "A013 Channel 1"],
        )
        return parse_jv_analysis(content)

    _GROUPS = [
        {"group_id": "control", "name": "Control", "kind": "control"},
        {"group_id": "target-1", "name": "Target", "kind": "target"},
    ]

    def test_excluded_device_keeps_assignment_but_leaves_statistics(self) -> None:
        analysis = self._three_device_analysis()

        assigned = assign_substrates_to_groups(
            analysis,
            {"A011": "control", "A012": "target-1", "A013": "target-1"},
            self._GROUPS,
            exclusions={"device-002": "shorted device, PCE below threshold"},
        )

        excluded = assigned["devices"][1]
        self.assertTrue(excluded["excluded"])
        self.assertEqual(excluded["exclusion_reason"], "shorted device, PCE below threshold")
        self.assertNotIn("excluded", assigned["devices"][0])

        target_row = next(
            group for group in assigned["statistics"]["groups"] if group["kind"] == "target"
        )
        self.assertEqual(target_row["device_count"], 2)
        self.assertEqual(target_row["valid_device_count"], 1)
        self.assertEqual(target_row["excluded_device_count"], 1)
        # The remaining target device (J 21) against control (J 20): the
        # excluded 19 mA/cm2 outlier no longer pulls the target mean down.
        comparison = assigned["statistics"]["comparisons"][0]["metrics"]["pce"]
        self.assertAlmostEqual(comparison["mean_difference"], 0.5)

    def test_flat_cache_pools_non_excluded_valid_traces(self) -> None:
        analysis = parse_jv_analysis(multi_device_csv([20, 20, 24, 24]))
        groups = [{"group_id": "control", "name": "Control", "kind": "control"}]
        assignments = {"A001": "control", "A002": "control"}

        assigned = assign_substrates_to_groups(analysis, assignments, groups)
        # v7 stores no aggregate summaries — every scan stays an
        # individual trace; the flat cache pools the non-excluded traces.
        self.assertNotIn("summary", assigned)
        self.assertNotIn("acquisition_summary", assigned)
        pooled = _flat_metrics_from_analysis(assigned)
        device_pces = sorted(
            value["pce"]
            for device in assigned["devices"]
            for value in device["metrics"].values()
            if value
        )
        self.assertAlmostEqual(pooled["pce"], statistics.median(device_pces))
        self.assertEqual(pooled["device_count"], 2.0)
        self.assertEqual(pooled["valid_trace_count"], 4.0)

        excluded = assign_substrates_to_groups(
            analysis,
            assignments,
            groups,
            exclusions={str(assigned["devices"][1]["device_id"]): "outlier"},
        )
        pooled_excluded = _flat_metrics_from_analysis(excluded)
        remaining_pces = [
            value["pce"]
            for device in excluded["devices"]
            if not device.get("excluded")
            for value in device["metrics"].values()
            if value
        ]
        self.assertAlmostEqual(
            pooled_excluded["pce"], statistics.median(remaining_pces)
        )
        self.assertEqual(pooled_excluded["device_count"], 1.0)
        self.assertAlmostEqual(pooled_excluded["pce_best"], max(remaining_pces))

    def test_excluding_the_only_valid_device_yields_a_counts_only_cache(self) -> None:
        analysis = parse_jv_analysis(multi_device_csv([20, 20, 24, 24]))
        # The second device's traces are invalid measurements.
        for trace in analysis["devices"][1]["traces"]:
            trace["valid"] = False
        groups = [{"group_id": "control", "name": "Control", "kind": "control"}]
        assignments = {"A001": "control", "A002": "control"}

        # Excluding the only valid device must not crash the pooled cache
        # (median over zero valid traces): it degrades honestly to counts
        # with no pooled metric values, and nothing is stored in the
        # analysis JSON.
        assigned = assign_substrates_to_groups(
            analysis,
            assignments,
            groups,
            exclusions={"device-001": "outlier"},
        )
        self.assertNotIn("summary", assigned)
        pooled = _flat_metrics_from_analysis(assigned)
        self.assertEqual(
            pooled,
            {"trace_count": 2.0, "valid_trace_count": 0.0, "device_count": 1.0},
        )

    def test_without_exclusion_all_devices_enter_the_statistics(self) -> None:
        analysis = self._three_device_analysis()

        assigned = assign_substrates_to_groups(
            analysis,
            {"A011": "control", "A012": "target-1", "A013": "target-1"},
            self._GROUPS,
        )

        target_row = next(
            group for group in assigned["statistics"]["groups"] if group["kind"] == "target"
        )
        self.assertEqual(target_row["valid_device_count"], 2)
        self.assertEqual(target_row["excluded_device_count"], 0)

    def test_saving_again_without_exclusions_reinstates_devices(self) -> None:
        analysis = self._three_device_analysis()
        excluded = assign_substrates_to_groups(
            analysis,
            {"A011": "control", "A012": "target-1", "A013": "target-1"},
            self._GROUPS,
            exclusions={"device-002": "shorted device"},
        )

        reinstated = assign_substrates_to_groups(
            excluded,
            {"A011": "control", "A012": "target-1", "A013": "target-1"},
            self._GROUPS,
        )

        self.assertNotIn("excluded", reinstated["devices"][1])
        self.assertNotIn("exclusion_reason", reinstated["devices"][1])

    def test_unknown_device_and_empty_reason_are_rejected(self) -> None:
        analysis = self._three_device_analysis()
        assignments = {"A011": "control", "A012": "target-1", "A013": "target-1"}

        with self.assertRaisesRegex(ValueError, "unknown analysis device"):
            assign_substrates_to_groups(
                analysis, assignments, self._GROUPS, exclusions={"device-999": "bad"}
            )
        with self.assertRaisesRegex(ValueError, "requires a reason"):
            assign_substrates_to_groups(
                analysis, assignments, self._GROUPS, exclusions={"device-002": "  "}
            )


def _summary_table_csv(
    summary_rows: list[dict[str, str]],
    *,
    separator: bool = True,
    pad_rows: int = 0,
) -> str:
    """Multi-device export with a trailing per-scan summary table.

    The trace area is the real wide-table layout: two scan blocks of one
    device (A001 Channel 1) side by side, 7 columns each. The summary
    table is appended after an optional '====' separator row and optional
    padding rows, with the canonical 14-column header (No., Name,
    Isc (mA), Voc (V), Pmax (mW), ..., Rs (ohm), Rsh (ohm)).
    """

    rows: list[list[str]] = [
        ["No.", "1", "", "", "", "", "", "No.", "2", "", "", "", "", ""],
        [
            "[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", "",
            "[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", "",
        ],
        [
            "Name", "A001 Channel 1.Forward", "0", "-2", "-20", "", "",
            "Name", "A001 Channel 1.Reverse", "0", "-2", "-18", "", "",
        ],
        ["", "", "0.5", "-2", "-20", "", "", "", "", "0.5", "-2", "-18", "", ""],
        ["", "", "1", "0", "0", "", "", "", "", "1", "0", "0", "", ""],
    ]
    for _ in range(pad_rows):
        rows.append([""] * 14)
    if separator:
        rows.append(["=" * 10])
    rows.append(
        [
            "No.", "Name", "Isc (mA)", "Voc (V)", "Pmax (mW)", "Imax (mA)",
            "Vmax (V)", "Efficiency (%)", "Fill Factor (%)", "Jsc (mA/cm^2)",
            "Jmax (mA/cm^2)", "Area (cm^2)", "Rs (ohm)", "Rsh (ohm)",
        ]
    )
    for row in summary_rows:
        rows.append(
            [row.get("No.", "1"), row["Name"], row.get("Isc (mA)", ""),
             row.get("Voc (V)", ""), row.get("Pmax (mW)", ""),
             row.get("Imax (mA)", ""), row.get("Vmax (V)", ""),
             row.get("Efficiency (%)", ""), row.get("Fill Factor (%)", ""),
             row.get("Jsc (mA/cm^2)", ""), row.get("Jmax (mA/cm^2)", ""),
             row.get("Area (cm^2)", ""), row.get("Rs (ohm)", ""),
             row.get("Rsh (ohm)", "")]
        )
    return "\n".join(",".join(cell for cell in row) for row in rows) + "\n"


def _instrument_export_csv(
    forward: dict[str, str],
    reverse: dict[str, str],
) -> str:
    """A001 Channel 1 export: forward/reverse scans + full summary table."""

    return _summary_table_csv(
        [
            {"No.": "1", "Name": "A001 Channel 1.Forward", **forward},
            {"No.": "1", "Name": "A001 Channel 1.Reverse", **reverse},
        ]
    )


class SummaryTableTests(unittest.TestCase):
    """The per-scan summary table is the primary metric source (v6).

    The instrument computes Voc/Jsc/FF/PCE (and Isc, Pmax, Rs, Rsh, ...);
    the parser's job is to locate the table structurally — never by row
    number — grab the values by column name, and store them per scan
    direction. No re-computation, no cross-direction medians.
    """

    FORWARD = {
        "Isc (mA)": "2.5", "Voc (V)": "1.02", "Pmax (mW)": "1.9",
        "Imax (mA)": "2.4", "Vmax (V)": "0.80", "Efficiency (%)": "17.5",
        "Fill Factor (%)": "74.0", "Jsc (mA/cm^2)": "22.5",
        "Jmax (mA/cm^2)": "21.6", "Area (cm^2)": "0.10",
        "Rs (ohm)": "25.5", "Rsh (ohm)": "5656",
    }
    REVERSE = {
        "Isc (mA)": "2.4", "Voc (V)": "1.04", "Pmax (mW)": "1.8",
        "Imax (mA)": "2.3", "Vmax (V)": "0.82", "Efficiency (%)": "16.6",
        "Fill Factor (%)": "72.0", "Jsc (mA/cm^2)": "22.1",
        "Jmax (mA/cm^2)": "21.0", "Area (cm^2)": "0.10",
        "Rs (ohm)": "24.5", "Rsh (ohm)": "16869",
    }

    def test_summary_table_is_the_primary_metric_source(self) -> None:
        analysis = parse_jv_analysis(
            _instrument_export_csv(self.FORWARD, self.REVERSE)
        )
        self.assertEqual(analysis["schema_version"], 7)

        device = analysis["devices"][0]
        self.assertEqual(
            device["metrics"]["forward"],
            {"voc": 1.02, "jsc": 22.5, "ff": 0.74, "pce": 17.5},
        )
        self.assertEqual(
            device["metrics"]["reverse"],
            {"voc": 1.04, "jsc": 22.1, "ff": 0.72, "pce": 16.6},
        )

    def test_per_scan_metrics_live_on_the_trace_records(self) -> None:
        analysis = parse_jv_analysis(
            _instrument_export_csv(self.FORWARD, self.REVERSE)
        )

        traces = {t["direction"]: t for t in analysis["devices"][0]["traces"]}
        self.assertEqual(
            traces["forward"]["metrics"],
            {"voc": 1.02, "jsc": 22.5, "ff": 0.74, "pce": 17.5},
        )
        self.assertEqual(
            traces["reverse"]["metrics"],
            {"voc": 1.04, "jsc": 22.1, "ff": 0.72, "pce": 16.6},
        )
        self.assertEqual(
            traces["forward"]["metric_source"], "summary table"
        )

    def test_repeated_forward_scans_keep_their_own_summary_metrics(self) -> None:
        content = _summary_table_csv(
            [
                {"Name": "A001 Channel 1.Forward(1)", "Efficiency (%)": "10.0"},
                {"Name": "A001 Channel 1.Forward(2)", "Efficiency (%)": "12.0"},
            ]
        ).replace("A001 Channel 1.Forward,", "A001 Channel 1.Forward(1),", 1).replace(
            "A001 Channel 1.Reverse,", "A001 Channel 1.Forward(2),", 1
        )

        analysis = parse_jv_analysis(content)
        traces = analysis["devices"][0]["traces"]
        self.assertEqual([trace["metrics"]["pce"] for trace in traces], [10.0, 12.0])
        self.assertEqual(analysis["devices"][0]["metrics"]["forward"]["pce"], 12.0)

    def test_missing_scan_number_does_not_borrow_a_different_summary_row(self) -> None:
        content = _summary_table_csv(
            [{"Name": "A001 Channel 1.Forward(2)", "Efficiency (%)": "12.0"}]
        ).replace("A001 Channel 1.Forward,", "A001 Channel 1.Forward(3),", 1)

        analysis = parse_jv_analysis(content)
        forward = analysis["devices"][0]["traces"][0]
        self.assertEqual(forward["metrics"]["pce"], 10.0)
        self.assertEqual(forward["metric_source"], "recomputed from curve")

    def test_duplicate_unnumbered_summary_rows_are_not_assigned_to_numbered_scans(self) -> None:
        content = _summary_table_csv(
            [
                {"Name": "A001 Channel 1.Forward", "Efficiency (%)": "11.0"},
                {"Name": "A001 Channel 1.Forward", "Efficiency (%)": "12.0"},
            ]
        ).replace("A001 Channel 1.Forward,", "A001 Channel 1.Forward(1),", 1).replace(
            "A001 Channel 1.Reverse,", "A001 Channel 1.Forward(2),", 1
        )

        traces = parse_jv_analysis(content)["devices"][0]["traces"]
        self.assertEqual([trace["metrics"]["pce"] for trace in traces], [10.0, 9.0])
        self.assertEqual([trace["metric_source"] for trace in traces], ["recomputed from curve"] * 2)

    def test_summary_table_is_located_without_a_separator_row(self) -> None:
        content = _summary_table_csv(
            [
                {"No.": "1", "Name": "A001 Channel 1.Forward", **self.FORWARD},
                {"No.": "1", "Name": "A001 Channel 1.Reverse", **self.REVERSE},
            ],
            separator=False,
        )

        analysis = parse_jv_analysis(content)

        device = analysis["devices"][0]
        self.assertEqual(device["metrics"]["forward"]["pce"], 17.5)
        self.assertEqual(device["metrics"]["reverse"]["pce"], 16.6)

    def test_summary_table_location_is_signature_based_not_row_based(self) -> None:
        # 20 padding rows before the separator: the header moves but the
        # signature locator still finds it, and the trace data area is cut
        # at the table regardless of where it sits.
        content = _summary_table_csv(
            [
                {"No.": "1", "Name": "A001 Channel 1.Forward", **self.FORWARD},
                {"No.": "1", "Name": "A001 Channel 1.Reverse", **self.REVERSE},
            ],
            pad_rows=20,
        )

        analysis = parse_jv_analysis(content)

        device = analysis["devices"][0]
        self.assertEqual(device["metrics"]["forward"]["voc"], 1.02)
        # Trace curves never see the summary numbers as scan points.
        for trace in device["traces"]:
            voltages = [point[0] for point in trace["points"]]
            self.assertTrue(all(-0.3 <= v <= 1.3 for v in voltages))

    def test_failed_device_summary_values_do_not_leak_into_curves(self) -> None:
        # Regression: a failed device reports Isc/Pmax inside the trace
        # voltage window; only the structural summary boundary keeps those
        # numbers out of the curve points.
        failed = {
            "Isc (mA)": "0.5", "Voc (V)": "0.10", "Pmax (mW)": "0.02",
            "Imax (mA)": "0.4", "Vmax (V)": "0.05", "Efficiency (%)": "0.1",
            "Fill Factor (%)": "24.0", "Jsc (mA/cm^2)": "5.0",
            "Jmax (mA/cm^2)": "4.0", "Area (cm^2)": "0.10",
            "Rs (ohm)": "-23.1", "Rsh (ohm)": "-281.2",
        }
        content = _summary_table_csv(
            [
                {"No.": "1", "Name": "A001 Channel 1.Forward", **failed},
                {"No.": "1", "Name": "A001 Channel 1.Reverse", **failed},
            ]
        )

        analysis = parse_jv_analysis(content)

        device = analysis["devices"][0]
        self.assertEqual(device["metrics"]["forward"]["pce"], 0.1)
        for trace in device["traces"]:
            self.assertEqual(len(trace["points"]), 3)
            voltages = [point[0] for point in trace["points"]]
            self.assertEqual(min(voltages), 0.0)

    def test_extra_summary_columns_are_preserved_in_trace_info(self) -> None:
        analysis = parse_jv_analysis(
            _instrument_export_csv(self.FORWARD, self.REVERSE)
        )

        traces = {t["direction"]: t for t in analysis["devices"][0]["traces"]}
        self.assertEqual(traces["forward"]["info"]["Rs (ohm)"], "25.5")
        self.assertEqual(traces["forward"]["info"]["Rsh (ohm)"], "5656")
        self.assertEqual(traces["forward"]["info"]["Pmax (mW)"], "1.9")

    def test_malformed_summary_numbers_are_skipped(self) -> None:
        forward = dict(self.FORWARD)
        forward["Voc (V)"] = "N/A"
        content = _instrument_export_csv(forward, self.REVERSE)

        analysis = parse_jv_analysis(content)

        device = analysis["devices"][0]
        self.assertNotIn("voc", device["metrics"]["forward"])
        self.assertEqual(device["metrics"]["forward"]["jsc"], 22.5)
        self.assertEqual(device["metrics"]["reverse"]["voc"], 1.04)


class DirectionalMetricsTests(unittest.TestCase):
    """v6: forward and reverse metrics are stored separately, never merged.

    The two sweep directions probe different physics (ion migration,
    charge storage — the hysteresis itself is the signal), so a
    forward/reverse median or mean erases information. Cross-device
    statistics pool the scans as independent samples instead.
    """

    def test_forward_and_reverse_metrics_are_never_averaged(self) -> None:
        # Curve-recomputed fallback: forward PCE 10, reverse PCE 8.
        analysis = parse_jv_analysis(multi_device_csv([20.0, 16.0]))

        device = analysis["devices"][0]
        self.assertAlmostEqual(device["metrics"]["forward"]["pce"], 10.0)
        self.assertAlmostEqual(device["metrics"]["reverse"]["pce"], 8.0)
        self.assertNotIn("voc", device["metrics"])  # no flat v5-style record

    def test_hysteresis_index_reads_directional_metrics(self) -> None:
        analysis = parse_jv_analysis(multi_device_csv([20.0, 16.0]))

        device = analysis["devices"][0]
        self.assertAlmostEqual(
            device["hysteresis_index"], (8.0 - 10.0) / 8.0
        )

    def test_single_direction_device_keeps_other_direction_none(self) -> None:
        content = (
            "No.,1,,,,,\n"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,\n"
            "Name,A001 Channel 1.Forward,0,-2,-20,,\n"
            ",,0.5,-2,-20,,\n"
            ",,1,0,0,,\n"
        )

        analysis = parse_jv_analysis(content)

        device = analysis["devices"][0]
        self.assertEqual(
            device["metrics"]["forward"]["pce"], 10.0
        )
        self.assertIsNone(device["metrics"]["reverse"])
        self.assertIsNone(device["hysteresis_index"])

    def test_repeat_scans_keep_best_pce_as_representative_and_all_traces(self) -> None:
        # One device measured twice forward (PCE 10 then 12) and once
        # reverse (PCE 8): the representative forward scan is the 12% one,
        # and every scan stays an individual trace.
        rows = [[], [], [], [], []]
        for trace_index, current in enumerate([20.0, 24.0, 16.0], start=1):
            direction = "Forward" if trace_index <= 2 else "Reverse"
            suffix = f"({trace_index})" if trace_index <= 2 else ""
            label = f"A001 Channel 1.{direction}{suffix}"
            rows[0].extend(["No.", str(trace_index), "", "", "", "", ""])
            rows[1].extend(
                ["[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", ""]
            )
            rows[2].extend(["Name", label, "0", "-2", str(-current), "", ""])
            rows[3].extend(["", "", "0.5", "-2", str(-current), "", ""])
            rows[4].extend(["", "", "1", "0", "0", "", ""])
        content = "\n".join(",".join(row) for row in rows) + "\n"

        analysis = parse_jv_analysis(content)

        self.assertEqual(len(analysis["devices"]), 1)
        device = analysis["devices"][0]
        self.assertEqual(len(device["traces"]), 3)
        forward_traces = [
            trace for trace in device["traces"] if trace["direction"] == "forward"
        ]
        self.assertEqual(len(forward_traces), 2)
        self.assertEqual(
            {trace["metrics"]["pce"] for trace in forward_traces}, {10.0, 12.0}
        )
        # The representative is the highest-PCE valid scan, not the first.
        self.assertAlmostEqual(device["metrics"]["forward"]["pce"], 12.0)
        self.assertAlmostEqual(device["metrics"]["reverse"]["pce"], 8.0)
        # Hysteresis is the divergence of the two representatives.
        self.assertAlmostEqual(device["hysteresis_index"], (8.0 - 12.0) / 8.0)

    def test_analysis_stores_no_aggregate_summaries(self) -> None:
        # v7: the analysis JSON keeps per-scan records only; pooled views
        # are derived at write/read time from the traces.
        analysis = parse_jv_analysis(multi_device_csv([20.0, 16.0, 24.0, 20.0]))

        self.assertNotIn("summary", analysis)
        self.assertNotIn("acquisition_summary", analysis)

    def test_group_statistics_pool_all_scans_by_default(self) -> None:
        analysis = parse_jv_analysis(
            multi_device_csv([20.0, 16.0, 24.0, 20.0],
                             device_labels=["A001 Channel 1", "A002 Channel 1"])
        )
        groups = [{"group_id": "control", "name": "Control", "kind": "control"}]

        assigned = assign_substrates_to_groups(analysis, {"A001": "control", "A002": "control"}, groups)

        control = assigned["statistics"]["groups"][0]
        # Pooled scans: forward {10, 12}, reverse {8, 10} -> combined {8, 10, 10, 12}.
        self.assertEqual(control["metrics"]["pce"]["n"], 4)
        self.assertAlmostEqual(control["metrics"]["pce"]["mean"], 10.0)

    def test_v5_analysis_is_migrated_on_read(self) -> None:
        analysis = parse_jv_analysis(multi_device_csv([20.0, 16.0]))
        legacy = dict(analysis)
        legacy["schema_version"] = 5
        legacy["devices"] = [
            dict(
                device,
                metrics={"voc": 1.0, "jsc": 20.0, "ff": 0.5, "pce": 10.0},
            )
            for device in analysis["devices"]
        ]
        legacy["summary"] = {
            "voc": 1.0, "jsc": 20.0, "ff": 0.5, "pce": 10.0,
            "pce_mean": 10.0, "pce_best": 10.0, "trace_count": 2.0,
            "valid_trace_count": 2.0, "device_count": 1.0,
        }
        legacy.pop("acquisition_summary", None)

        groups = [{"group_id": "control", "name": "Control", "kind": "control"}]
        assigned = assign_substrates_to_groups(legacy, {"A001": "control"}, groups)

        self.assertEqual(assigned["schema_version"], 7)
        device = assigned["devices"][0]
        # v5 flat metrics are preserved as the combined tier per direction.
        self.assertEqual(device["metrics"]["combined"]["pce"], 10.0)
        # v6-era aggregate summaries are dropped on normalization.
        self.assertNotIn("summary", assigned)
        self.assertNotIn("acquisition_summary", assigned)

    def test_v6_saved_directional_metrics_survive_when_traces_are_missing(self) -> None:
        legacy = parse_jv_analysis(multi_device_csv([20.0, 16.0]))
        legacy["schema_version"] = 6
        legacy["devices"][0]["traces"] = []
        legacy["devices"][0]["metrics"] = {
            "forward": {"voc": 1.0, "jsc": 20.0, "ff": 0.5, "pce": 10.0},
            "reverse": {"voc": 1.0, "jsc": 16.0, "ff": 0.5, "pce": 8.0},
        }
        groups = [{"group_id": "control", "name": "Control", "kind": "control"}]

        assigned = assign_substrates_to_groups(legacy, {"A001": "control"}, groups)
        self.assertEqual(assigned["devices"][0]["metrics"]["forward"]["pce"], 10.0)
        self.assertEqual(assigned["devices"][0]["metrics"]["reverse"]["pce"], 8.0)


class StatisticSectionTests(unittest.TestCase):
    """In-block [Statistic] rows are the fallback metric source."""

    def test_statistic_section_supplies_metrics_without_summary_table(self) -> None:
        rows = [
            ["No.", "1", "", "", "", "", ""],
            ["[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", ""],
            ["Name", "A004 Channel 1.Forward", "0", "-2", "-20", "", ""],
            ["[Statistic]", "", "0.5", "-2", "-20", "", ""],
            ["Name", "A004 Channel 1.Forward", "0.5", "-2", "-20", "", ""],
            ["Voc (V)", "1.03", "0.5", "-2", "-20", "", ""],
            ["Jsc (mA/cm^2)", "22.0", "0.5", "-2", "-20", "", ""],
            ["Fill Factor (%)", "73.0", "0.5", "-2", "-20", "", ""],
            ["Efficiency (%)", "16.5", "1", "0", "0", "", ""],
        ]

        analysis = parse_jv_analysis(
            "\n".join(",".join(cells) for cells in rows) + "\n"
        )

        device = analysis["devices"][0]
        self.assertEqual(
            device["metrics"]["forward"],
            {"voc": 1.03, "jsc": 22.0, "ff": 0.73, "pce": 16.5},
        )
        trace = device["traces"][0]
        self.assertEqual(trace["metric_source"], "[Statistic] section")
        self.assertEqual(len(trace["points"]), 7)


class RawInstrumentDataTests(unittest.TestCase):
    def test_preserves_measured_current_without_recomputing_from_density(self):
        analysis = parse_jv_analysis(multi_device_csv([20, 20]))
        trace = analysis["devices"][0]["traces"][0]
        self.assertEqual(trace["raw_data"]["units"], ["V", "mA", "mA/cm^2"])
        self.assertEqual(trace["raw_data"]["points"],
                         [[0.0, -2.0, -20.0], [0.5, -2.0, -20.0], [1.0, 0.0, 0.0]])
        self.assertEqual(trace["points"], [[0.0, -20.0], [0.5, -20.0], [1.0, 0.0]])

    def test_invalid_current_is_null_without_losing_voltage_density(self):
        import json
        content = multi_device_csv([20, 20]).replace(",0,-2,-20,", ",0,NaN,-20,")
        analysis = parse_jv_analysis(content)
        trace = analysis["devices"][0]["traces"][0]
        self.assertIsNone(trace["raw_data"]["points"][0][1])
        json.dumps(analysis, allow_nan=False)

    def test_metadata_keeps_sections_duplicates_and_untruncated_values(self):
        from web.jv_parser import _block_metadata_rows
        rows = [["No.", "1"], ["[Information]", ""], ["Name", "original"],
                ["Comment", ""], ["Temperature (degC)", "NaN"]]
        rows.extend([[f"Extra {i}", "x" * 100] for i in range(30)])
        rows.extend([["[Statistic]", ""], ["Name", "summary"], ["Time stamp", "########"]])
        entries = _block_metadata_rows(rows, 0, 2)
        names = [e for e in entries if e["label"] == "Name"]
        self.assertEqual([(e["section"], e["value"]) for e in names],
                         [("Information", "original"), ("Statistic", "summary")])
        self.assertEqual(next(e["value"] for e in entries if e["label"] == "Extra 29"), "x" * 100)
        self.assertEqual(next(e["value"] for e in entries if e["label"] == "Comment"), "")
        self.assertEqual(entries[-1]["value"], "########")


if __name__ == "__main__":
    unittest.main()
