# VCD Program Entry Guide

How to record the standard Vacuum Chamber Drying (VCD) operating patterns in
the perovskite deposition process. The VCD program is edited in the
**Vacuum and gas-backfill program** section of the perovskite process editor
(open the perovskite layer card and expand *Edit complete layer values*). The
same fields appear in baseline authoring, layer-preset revision, the
experiment builder, and the fabrication-batch run sheet. A condensed version
of this guide is available in the app through the "?" hint beside the
program heading.

## Common rules

- The program is an ordered list of rows added with **Add stage** (at most 10
  rows total). Each row is either **Evacuate** or **Gas backfill**; rows run
  from top to bottom. Up to five rows of each kind are stored.
- **Evacuate stage** fields:
  - Valve — one of `VV02`, `VV03`, `VV06`, `Pudi`. The valve may change from
    row to row (for example VV03 followed by VV06).
  - Pressure — integer Pa, 0 or greater.
  - Duration — whole seconds, 0 or greater. This is the time held at that
    pressure (the pump time to reach the setpoint is not recorded separately).
    **0 s means "reach the pressure and move on without holding"** — used when
    a fast valve only has to get near the setpoint before the next row takes
    over (see Pattern 2).
- **Gas backfill stage** fields:
  - Gas — the gas supplied through the MFC.
  - Flow — MFC flow rate in integer sccm.
  - Target pressure — integer Pa, 0 or greater.
  - Hold time — whole seconds at the target pressure, 0 or greater (0 means
    no hold). The fill time itself (governed by the flow rate and the
    pressure difference) is not recorded.
- Every evacuation and gas-backfill stage must appear exactly once in the
  execution order; removing a row updates the order automatically.

## Pattern 1 — Pump to base vacuum (pump-down, no pressure control)

Evacuate from atmosphere for a fixed total time without controlling the
pressure. The valve is typically VV02, VV03, or Pudi; whatever base pressure
is reached (usually below 1 Pa) is accepted.

Record one evacuate row with **pressure 0 Pa** and the total pump time:

| Stage | Valve | Pressure (Pa) | Duration (s) |
| --- | --- | --- | --- |
| Evacuate | VV02 | 0 | 25 |

The 0 Pa value is the agreed convention for "pressure not controlled"; the
achieved base pressure is not captured.

## Pattern 2 — Hold at one or more setpoint pressures

Pump to a setpoint, hold for a time, then optionally continue to further
setpoints. Add one evacuate row per pressure step; the valve may repeat or
change between rows.

A common two-row pattern pairs a fast valve with a slow one. VV03 pumps
quickly and can overshoot a setpoint: aiming for 50 Pa, it may blow past and
reach 30 Pa before the valve finishes closing (valve actuation takes time).
So use VV03 only to pull down *near* the target, then VV06 (slow, stable) to
settle on it. Record the VV03 row with **0 s** — it is there to reach the
pressure, not to hold — and the VV06 row with the real hold time. Target
50 Pa, hold 10 s:

| Stage | Valve | Pressure (Pa) | Duration (s) |
| --- | --- | --- | --- |
| Evacuate | VV03 | 50 | 0 |
| Evacuate | VV06 | 50 | 10 |

The 0 s hold means VV03 hands over the moment it reaches the setpoint, and
VV06's slower pumping then stabilizes there without significant overshoot.
If overshoot is still observed, set the VV03 row's target a little above the
final setpoint so it hands over even earlier.

Pudi with three setpoints (1000 Pa hold 5 s, 400 Pa hold 5 s, 150 Pa hold
10 s):

| Stage | Valve | Pressure (Pa) | Duration (s) |
| --- | --- | --- | --- |
| Evacuate | Pudi | 1000 | 5 |
| Evacuate | Pudi | 400 | 5 |
| Evacuate | Pudi | 150 | 10 |

VV03 directly to 10 Pa, held 10 s:

| Stage | Valve | Pressure (Pa) | Duration (s) |
| --- | --- | --- | --- |
| Evacuate | VV03 | 10 | 10 |

VV03 followed by VV06 uses two rows with different valves, each recording the
pressure it reaches and its hold time.

## Pattern 3 — MFC gas backfill to a target pressure

Evacuate first, then fill gas through the MFC at a set flow rate until the
target pressure is reached, and hold there. The fill time is determined by
the flow and the pressure difference, so only the flow, the target pressure,
and the hold time are recorded.

Pudi to 1 Pa, then backfill N2 to 40 Pa and hold 10 s:

| Stage | Valve/Gas | Pressure (Pa) | Flow (sccm) | Hold (s) |
| --- | --- | --- | --- | --- |
| Evacuate | Pudi | 1 | — | *pump time* |
| Gas backfill | N2 | 40 | *set flow* | 10 |

Backfill rows may be interleaved with further evacuate rows (evacuate, fill,
evacuate again, fill again) in any order, within the five-rows-per-kind and
ten-rows-total limits.
