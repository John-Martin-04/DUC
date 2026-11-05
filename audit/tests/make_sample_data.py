"""Generate small fake CASAS files in both layouts, to check the pipeline
runs before the real data arrives. NOT for any result.

Creates data/sample/raw/ with three homes:
  home_a/data          classic layout, Aruba-style labels with begin/end markers
  home_b.txt           classic layout, Milan-style labels
  csh901.ann.txt       UCI layout, 8 fields, an activity on every line

Deliberate problems for the audit to catch: an unmatched 'end', overlapping
activities, a 25-hour recording gap, a sensor that dies early, battery
messages, a raw label missing from the label map, and timestamps without
microseconds.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sample" / "raw"

# (start minute, end minute, activity key, room)
DAY = [
    (0, 420, "sleep", "Bedroom"),
    (420, 435, "hygiene", "Bathroom"),
    (440, 460, "cook", "Kitchen"),
    (460, 480, "eat", "DiningRoom"),
    (480, 490, "dishes", "Kitchen"),
    (540, 720, "work", "Office"),
    (720, 750, "cook", "Kitchen"),
    (750, 770, "eat", "DiningRoom"),
    (780, 1020, None, "LivingRoom"),
    (1080, 1110, "cook", "Kitchen"),
    (1110, 1140, "eat", "DiningRoom"),
    (1140, 1350, "tv", "LivingRoom"),
    (1350, 1365, "bathe", "Bathroom"),
    (1365, 1440, "sleep", "Bedroom"),
]
NAMES = {
    "a": {"sleep": "Sleeping", "hygiene": "Bed_to_Toilet", "cook": "Meal_Preparation",
          "eat": "Eating", "dishes": "Wash_Dishes", "work": "Work", "tv": "Relax",
          "bathe": "Housekeeping", "leave": "Leave_Home", "enter": "Enter_Home"},
    "b": {"sleep": "Sleep", "hygiene": "Master_Bathroom", "cook": "Kitchen_Activity",
          "eat": "Dining_Rm_Activity", "dishes": "Chores", "work": "Desk_Activity",
          "tv": "Watch_TV", "bathe": "Night_Wandering", "leave": "Leave_Home",
          "enter": "Enter_Home"},
    "uci": {"sleep": "Sleep", "hygiene": "Toilet", "cook": "Cook_Breakfast",
            "eat": "Eat_Breakfast", "dishes": "Wash_Dishes", "work": "Work_At_Table",
            "tv": "Watch_TV", "bathe": "Bathe", "leave": "Leave_Home",
            "enter": "Enter_Home", "other": "Other_Activity"},
}
SENSORS = {"Bedroom": ["M001", "M002"], "Bathroom": ["M003"], "Kitchen": ["M004", "M005"],
           "DiningRoom": ["M006"], "Office": ["M007"], "LivingRoom": ["M008", "M009"],
           "Entrance": ["M010"]}


def ts(t: datetime, micro: bool = True) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S.%f" if micro else "%Y-%m-%d %H:%M:%S")


def simulate(rng: random.Random, days: int, gap_day: int | None):
    """Yield (time, sensor, value, room, activity_key, phase) tuples."""
    start = datetime(2012, 7, 1)
    for d in range(days):
        if gap_day is not None and d == gap_day:
            continue  # recording gap of roughly 25 h
        base = start + timedelta(days=d)
        away = d % 4 == 2  # some days the resident leaves for work
        for s, e, act, room in DAY:
            if act == "work" and away:
                t0 = base + timedelta(minutes=s)
                yield t0, "D001", "OPEN", "Entrance", "leave", "point"
                yield t0 + timedelta(seconds=20), "D001", "CLOSE", "Entrance", "leave", "point"
                t1 = base + timedelta(minutes=e)
                yield t1, "D001", "OPEN", "Entrance", "enter", "point"
                yield t1 + timedelta(seconds=15), "D001", "CLOSE", "Entrance", "enter", "point"
                continue
            mean_gap = 900 if act == "sleep" else 50
            t = base + timedelta(minutes=s, seconds=rng.randint(0, 30))
            end = base + timedelta(minutes=e)
            events = []
            while t < end:
                sensor = rng.choice(SENSORS[room])
                off = t + timedelta(seconds=rng.randint(2, 20))
                events += [[t, sensor, "ON", room, act, "mid"],
                           [off, sensor, "OFF", room, act, "mid"]]
                t = off + timedelta(seconds=rng.expovariate(1 / mean_gap))
            if events:
                events[0][5], events[-1][5] = "begin", "end"
            yield from (tuple(ev) for ev in events)
            if room == "Kitchen" and act == "cook":
                t2 = base + timedelta(minutes=s + 3)
                yield t2, "D002", "OPEN", "Kitchen", act, "mid"
                yield t2 + timedelta(seconds=40), "D002", "CLOSE", "Kitchen", act, "mid"
        yield base + timedelta(hours=12), "T001", f"{rng.uniform(20, 24):.1f}", "LivingRoom", None, "mid"


def classic(path: Path, names: dict, seed: int, gap_day: int | None) -> None:
    rng = random.Random(seed)
    lines = []
    for i, (t, sensor, value, room, act, phase) in enumerate(simulate(rng, 28, gap_day)):
        if sensor == "M009" and t.day > 20:
            continue  # this sensor dies after day 20
        line = f"{ts(t, micro=i % 7 != 0)} {sensor} {value}"
        if act is not None:
            label = names[act]
            if phase == "begin":
                line += f" {label} begin"
            elif phase == "end":
                line += f" {label} end"
            elif phase == "point" and value == "OPEN":
                line += f" {label} begin"
            elif phase == "point" and value == "CLOSE":
                line += f" {label} end"
        lines.append(line)
    # an unmatched end and an overlapping activity
    lines.insert(500, f"{lines[500].split()[0]} {lines[500].split()[1]} M001 OFF Respirate end")
    lines.insert(800, f"{lines[800].split()[0]} {lines[800].split()[1]} M004 ON Phone begin")
    lines.insert(830, f"{lines[830].split()[0]} {lines[830].split()[1]} M004 OFF Phone end")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def uci(path: Path, seed: int) -> None:
    rng = random.Random(seed)
    names = NAMES["uci"]
    lines = []
    for i, (t, sensor, value, room, act, _phase) in enumerate(simulate(rng, 28, None)):
        kind = ("Control4-Door" if sensor.startswith("D") else
                "Control4-Temperature" if sensor.startswith("T") else "Control4-Motion")
        label = names.get(act, names["other"]) if act else names["other"]
        if act == "cook" and t.hour >= 17:
            label = "Cook_Dinner"
        lines.append(f"{ts(t)} {sensor} {room} {room} {value} {kind} {label}")
        if i % 400 == 0:
            lines.append(f"{ts(t)} BATP001 Ignore Ignore {rng.randint(60, 99)} "
                         f"Control4-BatteryPercent {names['other']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    classic(OUT / "home_a" / "data", NAMES["a"], seed=1, gap_day=10)
    classic(OUT / "home_b.txt", NAMES["b"], seed=2, gap_day=None)
    uci(OUT / "csh901.ann.txt", seed=3)
    print(f"Sample files written to {OUT}")
