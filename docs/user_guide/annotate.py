# docs/user_guide/annotate.py
# Draws numbered red callouts on the raw dashboard screenshots (docs/user_guide/raw/*.png) and writes the annotated
# figures used by USER_GUIDE.md to docs/user_guide/img/. Element positions come from the *.json file saved next to
# each raw screenshot (bounding boxes measured in the page at capture time), so callouts sit on the real elements.
# Documentation tooling only (needs Pillow); not part of the testbed.
"""Annotate the user-guide screenshots with numbered callouts (Pillow)."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
RAW, IMG = HERE / "raw", HERE / "img"
RED = (235, 40, 40)
FONT = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 26) if Path("C:/Windows/Fonts/arialbd.ttf").exists() \
    else ImageFont.load_default()

# figure name -> (raw screenshot, crop: ("top", key) = from y=0 to bottom of key / ("keys", [k...]) = union of keys,
#                 callouts: list of element keys, numbered from `start`)
FIGS: dict[str, tuple[str, tuple, list[str], int]] = {
    # ---- Part A: tour (one screenshot in three slices, continuous numbering) ----
    "A1_tour_header_control_arch": ("04_alarm_both_sides", ("top", "arch"),
                                    ["mode", "runid", "b-cs", "b-ps", "b-auth", "b-link", "t-live", "sys-start",
                                     "sys-extra", "btn-gem_start", "btn-ua_start", "btn-remote", "result", "arch"], 1),
    "A2_tour_columns_chart_feed_timeline": ("12_after_10s_disconnected", ("keys", ["sec-cols", "sec-chart", "sec-feed", "sec-tl"]),
                                            ["sec-cols", "row-Temperature", "row-GEM link", "sec-chart", "sec-feed",
                                             "sec-tl", "tl-drop"], 15),
    "A3_tour_wire_invariants": ("14_before_stop_invariants", ("keys", ["w-secs", "w-ua", "sec-inv"]),
                                ["w-secs", "w-ua", "inv", "cnt", "lat", "overall"], 22),
    "A4_inside_policy_browser_race": ("20_inside", ("top", "sec-race"),
                                      ["t-ins", "pol-active", "browse-btn", "tree-gem-tag", "race"], 28),
    "A5_results_tab": ("30_results", ("keys", ["rlist", "md"]), ["rlist", "md"], 33),
    # ---- Part B: demo steps ----
    "B01_start_system": ("01_system_started", ("top", "sec-cols"), ["sys-start", "sys-msg", "sys-extra", "b-link", "sec-cols"], 1),
    "B02_remote": ("02_remote", ("top", "sec-cols"), ["btn-remote", "result", "b-cs", "b-auth"], 1),
    "B03_gem_start": ("03_gem_start", ("top", "sec-cols"), ["btn-gem_start", "result", "b-ps", "row-ProcessingState"], 1),
    "B04_alarm_both_sides": ("04_alarm_both_sides", ("keys", ["sec-cols", "sec-chart", "sec-tl"]),
                             ["row-Alarm 5001", "row-Last event seq", "sec-chart", "tl-first"], 1),
    "B05_ua_start_rejected": ("05_ua_start_rejected", ("top", "sec-feed"), ["btn-ua_start", "result", "row-Last rejection", "feed-first"], 1),
    "B06_gem_stop": ("06_gem_stop", ("top", "sec-cols"), ["btn-gem_stop", "result", "b-ps", "sec-chart"], 1),
    "B07_both_start": ("07_both_start", ("top", "sec-feed"), ["btn-both_start", "result", "sec-feed"], 1),
    "B08_local": ("08_local", ("top", "sec-cols"), ["btn-local", "result", "b-cs", "b-auth"], 1),
    "B09_gem_start_rejected_local": ("09_gem_start_rejected_local", ("top", "sec-feed"), ["btn-gem_start", "result", "feed-first"], 1),
    "B10_remote_again": ("10_remote_again", ("top", "sec-cols"), ["btn-remote", "result", "b-cs", "b-auth"], 1),
    "B11_kill_gem_host": ("11_gem_host_killed", ("top", "sec-cols"), ["btn-kill_gem", "result", "b-link", "arch", "row-GEM link"], 1),
    "B12_after_10s_disconnected": ("12_after_10s_disconnected", ("keys", ["sec-cols", "sec-tl"]),
                                   ["row-Temperature", "row-Alarm 5001", "tl-drop"], 1),
    "B13_gem_reconnected": ("13_gem_reconnected", ("top", "sec-tl"), ["btn-reconnect_gem", "result", "b-link", "tl-first"], 1),
    "B14_wire_same_seq": ("w1_wire_same_seq", ("keys", ["w-secs", "w-ua"]), ["wire-secs-top", "wire-ua-top"], 1),
    "B15_stop_system_verdict": ("15_system_stopped_verdict", ("top", "sec-cols"), ["sys-stop", "sys-msg", "sys-extra", "b-link"], 1),
    "B16_invariants_before_stop": ("14_before_stop_invariants", ("keys", ["sec-inv"]), ["overall", "inv", "cnt"], 1),
}


def box(rects: dict, key: str) -> list[int] | None:
    """Element box [x, y, w, h]; the wire 'top' keys are the first 330 px of each wire column (matched message)."""
    if key in ("wire-secs-top", "wire-ua-top"):
        r = rects.get("w-secs" if key == "wire-secs-top" else "w-ua")
        return [r[0], r[1], r[2], min(r[3], 330)] if r else None
    return rects.get(key)


def crop_area(rects: dict, crop: tuple, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Crop rectangle (left, top, right, bottom) with a margin."""
    if crop[0] == "top":
        r = rects[crop[1]]
        return 0, 0, size[0], min(size[1], r[1] + r[3] + 16)
    bs = [rects[k] for k in crop[1] if k in rects]
    top = min(b[1] for b in bs) - 50
    bottom = max(b[1] + b[3] for b in bs) + 16
    return 0, max(0, top), size[0], min(size[1], bottom)


def annotate(name: str, raw: str, crop: tuple, keys: list[str], start: int) -> list[str]:
    """Draw callouts and save img/<name>.png; returns keys that were not found (reported, not drawn)."""
    im = Image.open(RAW / f"{raw}.png").convert("RGB")
    rects = json.loads((RAW / f"{raw}.json").read_text(encoding="utf-8"))
    d = ImageDraw.Draw(im)
    missing = []
    for i, key in enumerate(keys):
        b = box(rects, key)
        if not b:
            missing.append(key)
            continue
        x, y, w, h = b
        d.rectangle([x - 4, y - 4, x + w + 4, y + h + 4], outline=RED, width=4)
        n = str(start + i)
        cx, cy = max(24, x - 6), max(24, y - 6)
        d.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=RED, outline=(255, 255, 255), width=3)
        tw = d.textlength(n, font=FONT)
        d.text((cx - tw / 2, cy - 15), n, fill=(255, 255, 255), font=FONT)
    im.crop(crop_area(rects, crop, im.size)).save(IMG / f"{name}.png", optimize=True)
    return missing


def main() -> None:
    """Annotate every figure in FIGS."""
    IMG.mkdir(exist_ok=True)
    for name, (raw, crop, keys, start) in FIGS.items():
        missing = annotate(name, raw, crop, keys, start)
        print(f"{name}: {len(keys) - len(missing)} callouts" + (f" (not found: {missing})" if missing else ""))


if __name__ == "__main__":
    main()
