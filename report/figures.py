# report/figures.py
# Draws the original diagrams of the project report (Fig. 1.1, 5.1-5.6, 7.1) with matplotlib: white background,
# 300 dpi, one consistent style. Each figure is drawn at the width it is printed in the report (16 cm), so the font
# sizes below are the printed sizes. Output: report/figures/*.png. Documentation tooling only.
"""Generate the report's diagrams."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

OUT = Path(__file__).parent / "figures"
plt.rcParams.update({"font.family": "Arial", "font.size": 9, "savefig.dpi": 300, "figure.facecolor": "white"})

C_OWN, C_OWN_E = "#dbe9f6", "#1f5f99"     # original contribution
C_LIB, C_LIB_E = "#eeeeee", "#666666"     # existing library / simulation
C_EXT, C_EXT_E = "#fff6dd", "#8a6d1d"     # clients, operator, plant systems
GEM, UA, RED, DARK, GREY = "#2e7d32", "#c75b00", "#b71c1c", "#222222", "#555555"
W = 6.3  # printed width in inches (16 cm)
WHITE = dict(boxstyle="square,pad=0.12", fc="white", ec="none")


def canvas(h, xmax=14.0):
    """Figure W x h inches; data x 0..xmax, y 0..h*xmax/W (1 unit = W/xmax inches in both axes)."""
    fig, ax = plt.subplots(figsize=(W, h))
    fig.subplots_adjust(0, 0, 1, 1)
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, h * xmax / W)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text="", fc=C_LIB, ec=C_LIB_E, fs=9, bold=False, lw=1.2, tc=DARK, z=2):
    """Rounded box with centred text; (x, y) = lower-left corner."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.0,rounding_size=0.12", fc=fc, ec=ec, lw=lw, zorder=z))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, linespacing=1.3,
                fontweight="bold" if bold else "normal", zorder=z + 1)


def label(ax, x, y, text, fs=8, color=DARK, ha="center", va="center", bold=False, bg=True):
    """Text with a white background so lines never run through it."""
    ax.text(x, y, text, fontsize=fs, color=color, ha=ha, va=va, linespacing=1.3, zorder=6,
            fontweight="bold" if bold else "normal", bbox=WHITE if bg else None)


def arrow(ax, x1, y1, x2, y2, color=DARK, lw=1.3, ls="-", both=False, z=4):
    """Straight arrow."""
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="<|-|>" if both else "-|>", mutation_scale=10,
                                 color=color, lw=lw, ls=ls, shrinkA=0, shrinkB=0, zorder=z))


def legend(ax, x, y, items, step=4.4):
    """Legend row: (facecolor, edgecolor, label)."""
    for i, (fc, ec, text) in enumerate(items):
        ax.add_patch(Rectangle((x + i * step, y - 0.13), 0.42, 0.26, fc=fc, ec=ec, lw=1.2))
        ax.text(x + i * step + 0.55, y, text, va="center", fontsize=8.5)


def save(fig, name):
    """Write report/figures/<name>.png."""
    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)


# --------------------------------------------------------------------------------------------- Fig 1.1
def fig_fab_context():
    """Fab context: MES over SECS/GEM, plant systems over OPC UA, several tools, on-premises."""
    fig, ax = canvas(4.3)          # y 0..9.6
    ax.add_patch(Rectangle((0.1, 0.1), 13.8, 9.3, fc="none", ec="#9a9a9a", lw=1.1, ls=(0, (5, 3))))
    label(ax, 0.35, 9.05, "Fab site: on-premises network, process data stays local", fs=8.5, color=GREY, ha="left")
    box(ax, 0.5, 6.6, 3.0, 1.4, "MES / fab host\n(SECS/GEM host)", C_EXT, C_EXT_E, fs=9, bold=True)
    names = ["Maintenance", "Analytics /\ndigital twin", "Energy\nmonitoring", "Facility /\nsub-fab"]
    for i, t in enumerate(names):
        box(ax, 4.3 + i * 2.4, 6.6, 2.1, 1.4, t, C_EXT, C_EXT_E, fs=9)
    label(ax, 8.85, 8.4, "Plant-wide systems (OPC UA clients)", fs=8.5, color=UA)
    ax.plot([2.0, 2.0], [6.6, 5.2], color=GEM, lw=1.6)
    ax.plot([0.8, 13.2], [5.2, 5.2], color=GEM, lw=2.4)
    for i in range(4):
        ax.plot([5.35 + i * 2.4] * 2, [6.6, 4.3], color=UA, lw=1.4, ls=(0, (4, 2)))
    ax.plot([0.8, 13.2], [4.3, 4.3], color=UA, lw=2.4, ls=(0, (4, 2)))
    for i, t in enumerate(["Tool A", "Tool B", "Tool C"]):
        x = 0.9 + i * 4.5
        ax.plot([x + 1.0] * 2, [5.2, 2.9], color=GEM, lw=1.6)
        ax.plot([x + 2.6] * 2, [4.3, 2.9], color=UA, lw=1.4, ls=(0, (4, 2)))
        box(ax, x, 0.5, 3.6, 2.4, "", C_LIB, C_LIB_E)
        ax.text(x + 1.8, 2.5, t, ha="center", va="center", fontweight="bold", fontsize=9.5)
        box(ax, x + 0.3, 0.75, 3.0, 1.35, "equipment controller\nSECS/GEM + OPC UA", "white", C_LIB_E, fs=8.5)
    label(ax, 3.3, 5.2, "SECS/GEM over HSMS: one host session per tool", fs=8.5, color=GEM, ha="left")
    label(ax, 3.3, 4.3, "OPC UA: many clients may read, few may command", fs=8.5, color=UA, ha="left")
    save(fig, "fig_1_1_fab_context")


# --------------------------------------------------------------------------------------------- Fig 5.1
def fig_architecture():
    """Overall architecture with the original contributions marked."""
    fig, ax = canvas(4.9)          # y 0..10.9
    legend(ax, 0.2, 10.5, [(C_OWN, C_OWN_E, "original contribution"), (C_LIB, C_LIB_E, "existing library / simulation"),
                          (C_EXT, C_EXT_E, "clients / operator")], step=4.6)
    box(ax, 0.1, 4.6, 2.3, 1.6, "GEM host\n(MES)", C_EXT, C_EXT_E, fs=9, bold=True)
    box(ax, 11.6, 4.6, 2.3, 1.6, "Plant client\n(OPC UA)", C_EXT, C_EXT_E, fs=9, bold=True)
    box(ax, 3.0, 3.7, 2.5, 3.4, "", C_LIB, C_LIB_E)
    ax.text(4.25, 6.55, "GEM door", ha="center", fontweight="bold", fontsize=9)
    ax.text(4.25, 5.6, "secsgem 0.3.0\nHSMS, port 5000", ha="center", va="center", fontsize=8.5)
    box(ax, 3.2, 3.9, 2.1, 0.8, "library\noverrides", C_OWN, C_OWN_E, fs=8)
    box(ax, 8.5, 3.7, 2.5, 3.4, "", C_LIB, C_LIB_E)
    ax.text(9.75, 6.55, "OPC UA door", ha="center", fontweight="bold", fontsize=9)
    ax.text(9.75, 5.6, "asyncua 1.1.8\nopc.tcp, port 4840", ha="center", va="center", fontsize=8.5)
    box(ax, 8.7, 3.9, 2.1, 0.8, "GEM-derived\ninfo. model", C_OWN, C_OWN_E, fs=8)
    box(ax, 5.95, 2.8, 2.1, 5.0, "", C_OWN, C_OWN_E, lw=2)
    ax.text(7.0, 7.35, "Core", ha="center", fontweight="bold", fontsize=9.5)
    for i, t in enumerate(["Arbiter", "State store", "Audit log\n(global seq)", "Dispatcher"]):
        box(ax, 6.15, 6.15 - i * 1.0, 1.7, 0.8, t, "white", C_OWN_E, fs=8, z=3)
    box(ax, 5.6, 8.6, 2.8, 1.0, "Operator console", C_EXT, C_EXT_E, fs=9)
    box(ax, 5.6, 0.4, 2.8, 1.4, "Simulated chamber\n(sensor, heater)", C_LIB, C_LIB_E, fs=8.5)
    arrow(ax, 2.4, 5.4, 3.0, 5.4, GEM, both=True)
    arrow(ax, 11.6, 5.4, 11.0, 5.4, UA, both=True)
    arrow(ax, 5.5, 5.4, 5.95, 5.4, DARK, both=True)
    arrow(ax, 8.5, 5.4, 8.05, 5.4, DARK, both=True)
    arrow(ax, 7.0, 8.6, 7.0, 7.8)
    arrow(ax, 7.0, 1.8, 7.0, 2.8, both=True)
    label(ax, 2.7, 6.65, "SECS-II", fs=8, color=GEM)
    label(ax, 11.3, 6.65, "OPC UA", fs=8, color=UA)
    box(ax, 9.4, 0.3, 4.5, 1.9, "Consistency checker\naudit, send and receive logs\n→ invariants I1–I6", C_OWN, C_OWN_E, fs=8.5)
    ax.plot([8.05, 9.4], [3.2, 1.6], color=C_OWN_E, lw=1, ls=(0, (2, 2)))
    label(ax, 0.1, 2.3, "Every command (GEM host,\nOPC UA client, operator)\npasses the arbiter in the core.\n"
          "Reads are never arbitrated.", fs=8, color=GREY, ha="left", va="center")
    save(fig, "fig_5_1_architecture")


# --------------------------------------------------------------------------------------------- Fig 5.2
def fig_core_internals():
    """Inputs → one lock (decide, check, apply, seq + audit, enqueue) → dispatcher queues."""
    fig, ax = canvas(4.4)          # y 0..9.8
    inputs = [("GEM door", "S2F41, S2F15"), ("OPC UA door", "Start, Stop, SetLimit"), ("Operator console", "control state, lease"),
              ("Sensor thread", "temperature sample")]
    for i, (a, b) in enumerate(inputs):
        y = 7.4 - i * 2.0
        box(ax, 0.05, y, 2.8, 1.4, "", C_EXT, C_EXT_E)
        ax.text(1.45, y + 0.92, a, ha="center", va="center", fontsize=8.5, fontweight="bold")
        ax.text(1.45, y + 0.42, b, ha="center", va="center", fontsize=7.5)
        arrow(ax, 2.85, y + 0.7, 3.4, y + 0.7)
    ax.add_patch(Rectangle((3.4, 0.2), 6.2, 9.3, fc="#f4f8fc", ec=C_OWN_E, lw=1.6, ls=(0, (6, 3))))
    label(ax, 6.5, 9.15, "one lock: decide-and-apply is atomic", fs=8.5, color=C_OWN_E, bold=True, bg=False)
    steps = ["1  arbiter.decide(control state, lease,\n    origin, action) → allowed, reason",
             "2  check state preconditions\n    (IDLE / EXECUTING, range 20–80 °C)",
             "3  apply the change to the state store\n    (SVs, ECs, control state, alarms)",
             "4  assign the global seq, append the\n    audit record (flushed per line)",
             "5  enqueue notifications in seq order"]
    for i, t in enumerate(steps):
        y = 7.55 - i * 1.6
        box(ax, 3.65, y, 5.7, 1.2, "", C_OWN, C_OWN_E)
        ax.text(3.85, y + 0.6, t, va="center", fontsize=8, linespacing=1.3)
        if i < 4:
            arrow(ax, 6.5, y, 6.5, y - 0.4, C_OWN_E)
    label(ax, 6.5, 0.6, "returns CommandResult: ok, HCACK / EAC,\nStatusCode, reason, seq", fs=7.5, color=GREY, bg=False)
    ax.text(11.8, 8.95, "Dispatcher", ha="center", fontweight="bold", fontsize=9)
    ax.text(11.8, 8.45, "bounded FIFO per subscriber\none worker each, seq order", ha="center", va="top", fontsize=7.5)
    for i, (t, c) in enumerate([("GEM door\n→ S6F11, S5F1", GEM), ("OPC UA door\n→ events, values", UA), ("live view", DARK)]):
        y = 5.7 - i * 1.85
        box(ax, 10.2, y, 3.7, 1.3, t, "white", c, fs=8)
        arrow(ax, 9.35, 1.85, 10.2, y + 0.65, c, lw=1.0)
    ax.text(12.05, 0.75, "a slow or absent subscriber\nblocks neither the core\nnor the other subscribers", ha="center", va="center",
            fontsize=7.5, color=GREY)
    save(fig, "fig_5_2_core_internals")


# --------------------------------------------------------------------------------------------- Fig 5.3
def fig_state_diagram():
    """Control states, maintenance lease and the authority holder in each."""
    fig, ax = canvas(4.0)          # y 0..8.9
    box(ax, 0.2, 0.9, 5.4, 3.9, "", "#fafafa", C_LIB_E)
    ax.text(2.9, 4.4, "EQUIPMENT_OFFLINE", ha="center", fontweight="bold", fontsize=9)
    box(ax, 0.45, 2.4, 2.2, 1.4, "no lease\nauthority:\nOPERATOR", "white", C_LIB_E, fs=8)
    box(ax, 3.15, 2.4, 2.2, 1.4, "lease granted\nauthority:\nUA_CLIENT", C_OWN, C_OWN_E, fs=8)
    arrow(ax, 2.65, 3.35, 3.15, 3.35)
    arrow(ax, 3.15, 2.85, 2.65, 2.85)
    ax.text(2.9, 1.75, "lease ua / lease off (operator)", ha="center", fontsize=7.5)
    ax.text(2.9, 1.25, "leaving OFFLINE revokes the lease", ha="center", fontsize=7.5, color=GREY)
    box(ax, 4.9, 6.3, 4.2, 1.7, "ONLINE_LOCAL\nauthority: OPERATOR", "white", GEM, fs=9)
    box(ax, 8.6, 0.9, 5.2, 2.9, "ONLINE_REMOTE\nauthority: GEM_HOST\noperator may still STOP\n(safety override)", "white", C_OWN_E, fs=9)
    arrow(ax, 4.9, 7.0, 2.4, 4.8)
    label(ax, 3.15, 6.15, "offline", fs=8)
    arrow(ax, 3.6, 4.8, 5.8, 6.3)
    label(ax, 5.0, 5.35, "local", fs=8)
    arrow(ax, 9.1, 7.0, 11.6, 3.8)
    label(ax, 10.85, 5.75, "remote", fs=8)
    arrow(ax, 10.4, 3.8, 8.0, 6.3)
    label(ax, 8.9, 4.85, "local", fs=8)
    arrow(ax, 5.6, 2.9, 8.6, 2.9)
    label(ax, 7.1, 3.2, "remote", fs=8)
    arrow(ax, 8.6, 1.6, 5.6, 1.6)
    label(ax, 7.1, 1.3, "offline", fs=8)
    ax.text(7.0, 0.25, "All transitions are operator commands: arbitrated, audited, and announced as CEID 1001 / 1004. "
            "Initial state ONLINE_LOCAL.", ha="center", fontsize=7.5, color=GREY)
    save(fig, "fig_5_3_control_states")


# --------------------------------------------------------------------------------------------- sequence diagrams
XS = [1.25, 4.1, 7.0, 9.9, 12.75]


def lifelines(ax, names, top, bottom, colors):
    """Heads and dashed lifelines."""
    for n, x, c in zip(names, XS, colors):
        box(ax, x - 1.2, top, 2.4, 0.75, n, "white", c, fs=8, bold=True)
        ax.plot([x, x], [top, bottom], color="#a0a0a0", lw=0.9, ls=(0, (4, 3)), zorder=1)


def msg(ax, i, j, y, text, color=DARK, ls="-", fs=7.5):
    """Message from lifeline i to j with a label above the arrow."""
    arrow(ax, XS[i], y, XS[j], y, color, lw=1.1, ls=ls)
    label(ax, (XS[i] + XS[j]) / 2, y + 0.32, text, fs=fs, color=color)


def fig_seq_conflict():
    """Simultaneous START from GEM host and OPC UA client."""
    fig, ax = canvas(5.0)          # y 0..11.1
    lifelines(ax, ["GEM host", "GEM door", "Core + arbiter", "OPC UA door", "OPC UA client"], 10.2, 0.9,
              [GEM, GEM, C_OWN_E, UA, UA])
    ax.text(7.0, 9.75, "ONLINE_REMOTE, IDLE: both requests are released by one barrier", ha="center", fontsize=7.5, color=GREY)
    msg(ax, 0, 1, 8.9, "S2F41 W  START", GEM)
    msg(ax, 4, 3, 8.9, "Call Start()", UA)
    msg(ax, 1, 2, 7.9, "submit (GEM_HOST)", GEM)
    msg(ax, 3, 2, 7.9, "submit (UA_CLIENT)", UA)
    ax.add_patch(Rectangle((XS[2] - 0.22, 4.9), 0.44, 2.7, fc=C_OWN, ec=C_OWN_E, zorder=5))
    label(ax, XS[2] + 0.4, 7.0, "decide GEM_HOST: allowed\napply IDLE → EXECUTING", fs=7.5, ha="left")
    label(ax, XS[2] - 0.4, 5.6, "decide UA_CLIENT: rejected\n\"authority held by GEM_HOST\"", fs=7.5, ha="right")
    msg(ax, 2, 1, 4.2, "accepted", GEM)
    msg(ax, 1, 0, 4.2, "S2F42  HCACK 0", GEM)
    msg(ax, 2, 3, 4.2, "rejected", RED)
    msg(ax, 3, 4, 4.2, "BadUserAccessDenied", RED)
    msg(ax, 2, 1, 2.6, "CEID 1002, 1005", DARK)
    msg(ax, 1, 0, 2.6, "S6F11 × 2", GEM)
    msg(ax, 2, 3, 2.6, "CEID 1002, 1005", DARK)
    msg(ax, 3, 4, 2.6, "EventNotification × 2", UA)
    ax.text(7.0, 0.35, "The winner follows the policy, not arrival order. CEID 1005 (CommandRejected, Origin UA_CLIENT)\n"
            "reaches both sides, so the GEM host also learns of the rejected OPC UA attempt.", ha="center", va="center",
            fontsize=7.5, color=DARK)
    save(fig, "fig_5_4_seq_conflict")


def fig_seq_alarm():
    """Alarm and sample events carrying the same seq on both protocols."""
    fig, ax = canvas(4.8)          # y 0..10.7
    lifelines(ax, ["GEM host", "GEM door", "Core", "OPC UA door", "OPC UA client"], 9.8, 0.9, [GEM, GEM, C_OWN_E, UA, UA])
    box(ax, XS[2] - 1.0, 8.75, 2.0, 0.6, "sensor sample", C_LIB, C_LIB_E, fs=7.5, z=6)
    arrow(ax, XS[2], 8.75, XS[2], 8.3)
    ax.add_patch(Rectangle((XS[2] - 0.22, 6.4), 0.44, 1.9, fc=C_OWN, ec=C_OWN_E, zorder=5))
    label(ax, XS[2] + 0.4, 7.6, "temperature > TempHighLimit\nalarm_set ALID 5001\nseq 77 (run S2)", fs=7.5, ha="left")
    label(ax, XS[2] - 0.4, 7.6, "audit record written,\nthen queued for\nboth doors", fs=7.5, ha="right")
    msg(ax, 2, 1, 5.5, "seq 77", DARK)
    msg(ax, 1, 0, 5.5, "S5F1 W  ALID 5001\n\"… seq=77\"", GEM)
    msg(ax, 0, 1, 4.3, "S5F2", GEM, ls=(0, (4, 2)))
    msg(ax, 2, 3, 5.5, "seq 77", DARK)
    msg(ax, 3, 4, 5.5, "alarm event\nEventSeq 77", UA)
    msg(ax, 2, 1, 2.7, "CEID 1007, seq k", DARK)
    msg(ax, 1, 0, 2.7, "S6F11  DATAID k", GEM)
    msg(ax, 2, 3, 2.7, "CEID 1007, seq k", DARK)
    msg(ax, 3, 4, 2.7, "EventNotification\nEventSeq k", UA)
    ax.text(7.0, 0.35, "Every message carries the core's sequence number, so the checker can join GEM, core and OPC UA\n"
            "records. In run S2 the alarm set/clear seqs were 77 / 98 on the core and on both clients.", ha="center",
            va="center", fontsize=7.5)
    save(fig, "fig_5_5_seq_alarm")


# --------------------------------------------------------------------------------------------- Fig 5.6
def fig_model_tree():
    """OPC UA instance tree with GEM annotations."""
    rows = [
        (0, "Chamber1Tool", ": SemiEquipmentType", None),
        (1, "Identification", "Manufacturer, Model, SoftwareRevision", None),
        (1, "GemInterface", "", None),
        (2, "ControlState", "String", None),
        (2, "ControlStateId", "Byte", "SVID 2 · U1"),
        (2, "Authority", "String", "SVID 4 · A"),
        (2, "CommunicationState", "String (GEM link)", None),
        (2, "LastEventSeq", "UInt32", "SVID 5 · U4"),
        (1, "ProcessingState", "String", None),
        (1, "ProcessingStateId", "Byte", "SVID 3 · U1"),
        (1, "Chamber1", ": ChamberType", None),
        (2, "Temperature", "Double, °C, 0..100", "SVID 1 · F4"),
        (1, "EquipmentConstants", "", None),
        (2, "TempHighLimit", "Double, °C, 20..80, read-only", "ECID 201 · F4"),
        (1, "Alarms", "", None),
        (2, "ChamberOverTemp", "ALID 5001, AlarmText, Active", None),
        (1, "Start(), Stop()", "methods → arbiter", None),
        (1, "SetTempHighLimit(value)", "method → arbiter", None),
    ]
    fig, ax = canvas(0.3 * len(rows) + 0.9)
    top = (0.3 * len(rows) + 0.9) * 14 / W
    y = top - 0.5
    for depth, name, info, gem in rows:
        x = 0.3 + depth * 0.9
        if depth:
            ax.plot([x - 0.55, x - 0.55, x - 0.12], [y + 0.62, y, y], color="#aaaaaa", lw=0.9)
        ax.text(x, y, name, fontweight="bold", va="center", fontsize=8.5)
        ax.text(6.3, y, info, va="center", fontsize=8, color="#444444")
        if gem:
            ax.text(13.85, y, "GemId · " + gem, va="center", ha="right", fontsize=8, color=C_OWN_E,
                    bbox=dict(boxstyle="round,pad=0.22", fc=C_OWN, ec=C_OWN_E, lw=0.8))
        y -= 0.67
    ax.text(0.3, y + 0.1, "Events (EmittingNode Chamber1Tool): GemCollectionEventType (CEID, EventSeq, Origin, Payload) and\n"
            "GemOffNormalAlarmType (OffNormalAlarmType + ALID, EventSeq). Blue tags: GemId / GemKind / GemFormat properties.",
            fontsize=7.5, color=GREY, va="top")
    save(fig, "fig_5_6_information_model")


# --------------------------------------------------------------------------------------------- Fig 7.1
def fig_verification():
    """Logs → checker → invariants → verdict."""
    fig, ax = canvas(3.9)          # y 0..8.7
    srcs = [("Core audit log", "oracle: global seq", C_OWN, C_OWN_E), ("Send-side logs", "GEM door, OPC UA door", C_OWN, C_OWN_E),
            ("Receive-side logs", "GEM host, OPC UA client", C_EXT, C_EXT_E), ("Scenario file", "window, conflict rounds", C_LIB, C_LIB_E)]
    for i, (a, b, fc, ec) in enumerate(srcs):
        y = 6.9 - i * 1.9
        box(ax, 0.05, y, 3.4, 1.4, "", fc, ec)
        ax.text(1.75, y + 0.92, a, ha="center", va="center", fontsize=8.5, fontweight="bold")
        ax.text(1.75, y + 0.42, b, ha="center", va="center", fontsize=7.5)
        arrow(ax, 3.45, y + 0.7, 4.5, 4.45, DARK, lw=1.0)
    box(ax, 4.5, 3.3, 2.6, 2.3, "checker\n\njoins every\nrecord on seq", C_OWN, C_OWN_E, fs=8.5, bold=True)
    inv = ["I1 completeness", "I2 order", "I3 value agreement", "I4 convergence ≤ 500 ms", "I5 single winner", "I6 loss attribution"]
    for i, t in enumerate(inv):
        y = 7.35 - i * 1.3
        box(ax, 7.9, y, 3.3, 0.9, t, "white", C_OWN_E, fs=8)
        arrow(ax, 7.1, 4.45, 7.9, y + 0.45, C_OWN_E, lw=0.8)
        ax.plot([11.2, 11.9], [y + 0.45, 4.45], color="#9a9a9a", lw=0.8)
    box(ax, 11.9, 3.5, 2.05, 1.9, "verdict\nPASS / FAIL\n+ latency", C_OWN, C_OWN_E, fs=8.5, bold=True)
    ax.text(5.8, 1.9, "Self-test: five deliberate\ncorruptions of a real run\nmust each be flagged by\nthe right invariant.",
            fontsize=7.5, color=GREY, va="center", ha="center")
    save(fig, "fig_7_1_verification")


if __name__ == "__main__":
    for f in (fig_fab_context, fig_architecture, fig_core_internals, fig_state_diagram, fig_seq_conflict, fig_seq_alarm,
              fig_model_tree, fig_verification):
        f()
        print("ok", f.__name__)
