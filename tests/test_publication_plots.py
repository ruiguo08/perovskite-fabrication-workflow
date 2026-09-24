from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from web.jv_parser import assign_substrates_to_groups, parse_jv_analysis
from web.repository.result import _result_record

from web.publication_plots import (
    PlotInputError,
    _render_boxplot,
    _trace_points,
    _render_jv,
    _render_uniformity,
    _representative_trace,
    render_publication_figure,
)

from tests.test_jv_parser import instrument_named_csv


def device(device_id: str, position: int, group_id: str = "control") -> dict:
    return {
        "device_id": device_id,
        "device_ordinal": position,
        "substrate_id": "A001",
        "group_id": group_id,
        "metrics": {
            "forward": {"voc": 1.0, "jsc": 20.0, "ff": 0.50, "pce": 10.0 + position},
            "reverse": {"voc": 1.02, "jsc": 21.0, "ff": 0.55, "pce": 11.0 + position},
        },
        "traces": [
            {"trace_id": "low", "valid": True, "direction": "forward", "metrics": {"pce": 4.0}, "points": [[0, -20], [1, 0]]},
            {"trace_id": "best", "valid": True, "direction": "forward", "metrics": {"pce": 12.0}, "points": [[0, -22], [1.1, 0]]},
            {"trace_id": "reverse", "valid": True, "direction": "reverse", "metrics": {"pce": 11.0}, "points": [[1.0, 0], [0, -21]]},
        ],
    }


class PublicationPlotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analysis = {"devices": [device(f"d-{index}", index) for index in range(1, 7)]}
        self.groups = [{"group_id": "control", "name": "Control", "kind": "control"}]

    def test_saved_v5_result_renders_publication_figures_on_read(self) -> None:
        legacy_analysis = {
            "schema_version": 5,
            "devices": [
                {**device("d-1", 1), "metrics": {"voc": 1.0, "jsc": 20.0, "ff": 0.5, "pce": 10.0}}
            ],
            "summary": {"pce": 10.0},
        }
        saved_row = {
            "id": 1,
            "experiment_id": 1,
            "fabrication_batch_id": 1,
            "filename": "legacy.csv",
            "content_type": "text/csv",
            "size_bytes": 42,
            "sha256": "a" * 64,
            "group_assignment": "control",
            "metrics": {"pce": 10.0},
            "analysis": legacy_analysis,
            "analysis_schema_version": 5,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "created_by_id": 1,
        }

        loaded = _result_record(saved_row)
        figure = render_publication_figure(loaded["analysis"], self.groups, kind="boxplot", metric="pce")
        self.assertTrue(figure.startswith(b"<?xml"))
        self.assertEqual(loaded["analysis_schema_version"], 7)
        self.assertEqual(saved_row["analysis"]["schema_version"], 5)

    def test_instrument_named_csv_renders_directional_figures_after_manual_assignment(self) -> None:
        analysis = parse_jv_analysis(
            instrument_named_csv(
                ["Control-1", "T1-6", "T2-11", "T3-16"],
                [1, 2, 3, 4, 5, 6],
            ).encode("utf-8"),
            source_filename="20260906.csv",
        )
        manually_chosen = {
            "Control": (1, 2, 3, 4),
            "T1": (6, 7, 8, 9),
            "T2": (11, 12, 13, 14),
            "T3": (16, 17, 18, 19),
        }
        groups = [
            {"group_id": name, "name": name, "kind": "control" if name == "Control" else "target"}
            for name in manually_chosen
        ]
        assigned = assign_substrates_to_groups(
            analysis,
            {f"{name}-{number}": name for name, numbers in manually_chosen.items() for number in numbers},
            groups,
        )
        selected = (assigned["devices"][0]["device_id"],)
        jv = render_publication_figure(assigned, groups, kind="jv", device_ids=selected)
        boxplot = render_publication_figure(assigned, groups, kind="boxplot", metric="pce")
        forward = render_publication_figure(assigned, groups, kind="uniformity", metric="pce", direction="forward")
        reverse = render_publication_figure(assigned, groups, kind="uniformity", metric="pce", direction="reverse")

        self.assertTrue(all(blob.startswith(b"<?xml") for blob in (jv, boxplot, forward, reverse)))
        self.assertIn(b"n=6", boxplot)
        self.assertIn(b"Control-1", forward)
        self.assertIn(b"T3-16", forward)
        self.assertNotEqual(forward, reverse)

    def test_representative_trace_is_highest_pce_per_direction(self) -> None:
        selected = _representative_trace(self.analysis["devices"][0], "forward")
        self.assertEqual(selected["trace_id"], "best")

    def test_jv_keeps_measured_points_on_both_sides_of_the_voc_axis_crossing(self) -> None:
        voltage, current = _trace_points({"points": [[0, -20], [0.5, -10], [0.9, -2], [1.1, 2]]})
        self.assertEqual(voltage, [0.0, 0.5, 0.9, 1.1])
        self.assertEqual(current, [20.0, 10.0, 2.0, -2.0])

    def test_jv_marks_each_measured_sample_with_script_colors(self) -> None:
        figure = _render_jv(self.analysis, self.groups, ["d-1"])
        forward, reverse = figure.axes[0].lines
        self.assertEqual([line.get_color() for line in (forward, reverse)], ["#F08228", "#00C8C8"])
        self.assertTrue(all(line.get_marker() == "o" and line.get_markevery() is None for line in (forward, reverse)))

    def test_jv_retains_all_samples_across_multiple_axis_crossings(self) -> None:
        row = device("d-1", 1)
        row["traces"][1]["points"] = [[0, -20], [0.3, -12], [0.5, 2], [0.7, -8], [0.9, 1], [1.1, 3]]
        figure = _render_jv({"devices": [row]}, self.groups, ["d-1"])
        forward = figure.axes[0].lines[0]
        self.assertEqual(list(forward.get_xdata()), [0, 0.3, 0.5, 0.7, 0.9, 1.1])
        self.assertEqual(list(forward.get_ydata()), [20, 12, -2, 8, -1, -3])
        self.assertIsNone(forward.get_markevery())

    def test_palette_selection_changes_figure_and_rejects_unknown_choice(self) -> None:
        standalone_jv = render_publication_figure(self.analysis, self.groups, kind="jv", device_ids=("d-1",))
        nature_jv = render_publication_figure(self.analysis, self.groups, kind="jv", device_ids=("d-1",), palette="nature-classic")
        self.assertNotEqual(standalone_jv, nature_jv)
        default = render_publication_figure(self.analysis, self.groups, kind="boxplot", metric="pce")
        science = render_publication_figure(self.analysis, self.groups, kind="boxplot", metric="pce", palette="science-tol")
        self.assertNotEqual(default, science)
        default_map = render_publication_figure(self.analysis, self.groups, kind="uniformity", metric="pce")
        rainbow_map = render_publication_figure(self.analysis, self.groups, kind="uniformity", metric="pce", palette="rainbow")
        self.assertNotEqual(default_map, rainbow_map)
        with self.assertRaisesRegex(PlotInputError, "palette"):
            render_publication_figure(self.analysis, self.groups, kind="uniformity", metric="pce", palette="unknown")

    def test_default_jv_overview_contains_every_device_in_group_panels(self) -> None:
        svg = render_publication_figure(self.analysis, self.groups, kind="jv").decode("utf-8")
        self.assertIn("All-device J–V curves", svg)
        self.assertIn("Control", svg)
        self.assertIn("6 devices", svg)

    def test_default_jv_overview_includes_unassigned_and_unknown_groups(self) -> None:
        unassigned = device("d-unassigned", 2)
        unassigned["group_id"] = None
        unknown = device("d-unknown", 3, "missing-group")
        figure = _render_jv(
            {"devices": [device("d-control", 1), unassigned, unknown]}, self.groups, [],
        )
        self.assertEqual(figure.axes[1].get_title(loc="left"), "Unassigned · 2 devices")
        self.assertEqual(len(figure.axes[1].lines), 4)

    def test_zero_pce_is_still_preferred_to_a_missing_pce(self) -> None:
        selected = _representative_trace(
            {
                "traces": [
                    {"trace_id": "missing", "valid": True, "direction": "forward", "metrics": {}, "points": [[0, 0]]},
                    {"trace_id": "zero", "valid": True, "direction": "forward", "metrics": {"pce": 0.0}, "points": [[0, 0]]},
                ]
            },
            "forward",
        )
        self.assertEqual(selected["trace_id"], "zero")

    def test_all_publication_formats_are_real_files(self) -> None:
        svg = render_publication_figure(self.analysis, self.groups, kind="jv", device_ids=("d-1",))
        pdf = render_publication_figure(self.analysis, self.groups, kind="boxplot", metric="pce", figure_format="pdf")
        tiff = render_publication_figure(self.analysis, self.groups, kind="uniformity", metric="pce", figure_format="tiff")
        self.assertIn(b"<svg", svg[:1000])
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(tiff[:4], (b"II*\x00", b"MM\x00*"))

    def test_boxplots_count_one_value_per_device_and_direction(self) -> None:
        svg = render_publication_figure(self.analysis, self.groups, kind="boxplot", metric="pce")
        text = svg.decode("utf-8")
        self.assertIn("Control", text)
        self.assertGreaterEqual(text.count("n=6"), 2)

    def test_boxplot_top_labeled_tick_covers_highest_device_point(self) -> None:
        self.analysis["devices"][0]["metrics"]["reverse"]["voc"] = 1.131916
        self.analysis["devices"][1]["metrics"]["forward"]["voc"] = 0.0
        figure = _render_boxplot(self.analysis, self.groups, "voc")
        axis = figure.axes[0]
        highest_point = 1.131916
        top_labeled_tick = max(tick for tick in axis.get_yticks() if tick <= axis.get_ylim()[1])
        self.assertGreaterEqual(top_labeled_tick, highest_point)
        self.assertGreater(axis.get_ylim()[1], top_labeled_tick)

    def test_boxplot_preview_uses_the_exact_pending_exclusion_set(self) -> None:
        for row in self.analysis["devices"]:
            row["excluded"] = True
        restored = render_publication_figure(
            self.analysis,
            self.groups,
            kind="boxplot",
            metric="pce",
            excluded_device_ids=(),
        ).decode("utf-8")
        filtered = render_publication_figure(
            self.analysis,
            self.groups,
            kind="boxplot",
            metric="pce",
            excluded_device_ids=("d-1", "d-2"),
        ).decode("utf-8")
        self.assertGreaterEqual(restored.count("n=6"), 2)
        self.assertGreaterEqual(filtered.count("n=4"), 2)
        self.assertIn("All devices", restored)
        self.assertIn("After exclusions", filtered)

    def test_uniformity_labels_its_exclusion_scope(self) -> None:
        all_devices = render_publication_figure(
            self.analysis, self.groups, kind="uniformity", metric="pce",
            excluded_device_ids=(),
        ).decode("utf-8")
        included = render_publication_figure(
            self.analysis, self.groups, kind="uniformity", metric="pce",
            excluded_device_ids=("d-1",),
        ).decode("utf-8")
        self.assertIn("All devices", all_devices)
        self.assertIn("After exclusions", included)

    def test_uniformity_uses_shared_forward_reverse_scale_and_channel_layout(self) -> None:
        svg = render_publication_figure(self.analysis, self.groups, kind="uniformity", metric="ff").decode("utf-8")
        self.assertIn("shared across substrates, scopes and F/R", svg)
        self.assertIn("A001", svg)
        self.assertNotIn(">1<", svg)
        self.assertNotIn(">6<", svg)

    def test_red_blue_uniformity_centers_white_on_all_device_median(self) -> None:
        figure = _render_uniformity(self.analysis, self.groups, "pce", palette="red-blue")
        median_cell = figure.axes[0].patches[3]  # Forward PCE 14; all-direction median is 14.
        self.assertTrue(all(channel > 0.99 for channel in median_cell.get_facecolor()[:3]))
        self.assertIn("white = all-device median", figure.axes[-1].get_ylabel())

    def test_red_blue_manual_range_uses_raw_ticks_and_range_midpoint_when_needed(self) -> None:
        figure = _render_uniformity(
            self.analysis, self.groups, "voc", palette="red-blue",
            scale_min=1.10, scale_max=1.15,
        )
        colorbar = figure.axes[-1]
        self.assertAlmostEqual(colorbar.get_ylim()[0], 1.10)
        self.assertAlmostEqual(colorbar.get_ylim()[1], 1.15)
        self.assertIn("white = selected range midpoint", colorbar.get_ylabel())
        self.assertTrue({1.10, 1.125, 1.15}.issubset(set(colorbar.get_yticks())))

    def test_uniformity_custom_colorbar_range_and_problem_threshold(self) -> None:
        figure = _render_uniformity(
            self.analysis, self.groups, "voc", "forward", "rdylgn",
            scale_min=1.0, scale_max=1.15, threshold=1.10,
        )
        colorbar = figure.axes[-1]
        self.assertAlmostEqual(colorbar.get_ylim()[0], 1.0)
        self.assertAlmostEqual(colorbar.get_ylim()[1], 1.15)
        self.assertTrue({1.0, 1.1, 1.15}.issubset(set(colorbar.get_yticks())))
        self.assertIn("Problem threshold: 1.100 V", colorbar.get_ylabel())
        self.assertGreaterEqual(len(colorbar.lines), 1)

    def test_uniformity_rejects_invalid_manual_scale(self) -> None:
        for bounds in ((1.15, 1.0, None), (1.0, 1.15, 1.20), (1.0, None, None)):
            with self.subTest(bounds=bounds), self.assertRaisesRegex(PlotInputError, "color scale|threshold"):
                render_publication_figure(
                    self.analysis, self.groups, kind="uniformity", metric="voc",
                    scale_min=bounds[0], scale_max=bounds[1], threshold=bounds[2],
                )

    def test_uniformity_renders_only_selected_scan_direction(self) -> None:
        forward = _render_uniformity(self.analysis, self.groups, "pce", "forward")
        reverse = _render_uniformity(self.analysis, self.groups, "pce", "reverse")
        self.assertEqual(len(forward.axes[0].patches), 7)
        self.assertEqual(len(reverse.axes[0].patches), 7)
        forward_values = [text.get_text() for text in forward.axes[0].texts]
        reverse_values = [text.get_text() for text in reverse.axes[0].texts]
        self.assertIn("11.0", forward_values)
        self.assertNotIn("11.0", reverse_values)
        self.assertIn("12.0", reverse_values)
        self.assertIn("Forward", forward._suptitle.get_text())
        self.assertIn("Reverse", reverse._suptitle.get_text())

    def test_uniformity_rejects_unknown_direction(self) -> None:
        with self.assertRaisesRegex(PlotInputError, "direction must be"):
            render_publication_figure(self.analysis, self.groups, kind="uniformity", metric="pce", direction="combined")

    def test_uniformity_keeps_each_condition_on_one_row(self) -> None:
        devices = []
        for group_id, substrates in (
            ("control", ("C0001", "C0002", "C0003", "C0004")),
            ("target", ("T1001", "T1002", "T1003")),
        ):
            for substrate in substrates:
                row = device(f"{substrate}-1", 1, group_id)
                row["substrate_id"] = substrate
                devices.append(row)
        figure = _render_uniformity(
            {"devices": devices},
            [
                {"group_id": "control", "name": "Control", "kind": "control"},
                {"group_id": "target", "name": "T1", "kind": "target"},
            ],
            "pce",
        )
        axes = {axis.get_title(loc="center"): axis for axis in figure.axes if axis.get_title(loc="center")}
        control_rows = {
            axes[substrate].get_subplotspec().rowspan.start
            for substrate in ("C0001", "C0002", "C0003", "C0004")
        }
        target_rows = {
            axes[substrate].get_subplotspec().rowspan.start
            for substrate in ("T1001", "T1002", "T1003")
        }
        self.assertEqual(control_rows, {0})
        self.assertEqual(target_rows, {1})
        condition_labels = {label.get_text(): label for label in figure.texts}
        self.assertEqual(condition_labels["Control"].get_rotation(), 90.0)
        self.assertEqual(condition_labels["T1"].get_rotation(), 90.0)
        self.assertLess(condition_labels["Control"].get_position()[0], axes["C0001"].get_position().x0)
        self.assertGreater(condition_labels["Control"].get_position()[1], condition_labels["T1"].get_position()[1])

    def test_uniformity_draws_one_square_substrate_frame_around_six_cells(self) -> None:
        figure = _render_uniformity(self.analysis, self.groups, "pce")
        cells, frame = figure.axes[0].patches[:6], figure.axes[0].patches[6]
        self.assertEqual(frame.get_width(), frame.get_height())
        self.assertFalse(frame.get_fill())
        for cell in cells:
            self.assertGreater(cell.get_x(), frame.get_x())
            self.assertGreater(cell.get_y(), frame.get_y())
            self.assertLess(cell.get_x() + cell.get_width(), frame.get_x() + frame.get_width())
            self.assertLess(cell.get_y() + cell.get_height(), frame.get_y() + frame.get_height())

    def test_uniformity_places_the_shared_colorbar_on_the_right(self) -> None:
        figure = _render_uniformity(self.analysis, self.groups, "pce")
        bounds = figure.axes[-1].get_position()
        self.assertGreater(bounds.height, bounds.width)
        self.assertGreater(bounds.x0, 0.85)

    def test_invalid_or_oversized_selections_are_rejected(self) -> None:
        with self.assertRaisesRegex(PlotInputError, "at most 12"):
            render_publication_figure(
                {"devices": [device(f"d-{index}", 1) for index in range(13)]},
                self.groups,
                kind="jv",
                device_ids=tuple(f"d-{index}" for index in range(13)),
            )


if __name__ == "__main__":
    unittest.main()
