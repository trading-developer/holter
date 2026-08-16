import io
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from db.models import Measurement  # noqa: E402

BG = "#1a1a2e"
PLOT_BG = "#16213e"
GRID = "#2a2a4a"
TICK = "#aaaacc"
TITLE = "#e0e0ff"

SERIES = (
    ("САД", "#ef5350"),
    ("ДАД", "#4fc3f7"),
    ("Пульс", "#66bb6a"),
)


def build_chart(rows: list[Measurement], tz: ZoneInfo, days: int) -> io.BytesIO | None:
    if not rows:
        return None

    dates = [r.created_at.astimezone(tz) for r in rows]
    values = [
        [r.systolic for r in rows],
        [r.diastolic for r in rows],
        [r.pulse if r.pulse is not None else 0 for r in rows],  # нет пульса — рисуем 0
    ]

    fig, ax = plt.subplots(figsize=(11, 5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PLOT_BG)

    for (label, color), vals in zip(SERIES, values):
        ax.plot(dates, vals, color=color, linewidth=2, marker="o", markersize=4,
                 label=label, zorder=3)
        last_val, last_date = vals[-1], dates[-1]
        ax.scatter([last_date], [last_val], color=color, s=50, zorder=5)
        ax.annotate(f"{last_val}", (last_date, last_val),
                     textcoords="offset points", xytext=(8, 0),
                     color=color, fontsize=9, fontweight="bold", ha="left", va="center")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m\n%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=0, ha="center")

    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.tick_params(colors=TICK)
    ax.yaxis.label.set_color(TICK)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_ylabel("мм рт. ст. / уд/мин", color=TICK)
    ax.set_title(f"Давление и пульс — последние {days} дн.", color=TITLE, pad=12)
    ax.legend(loc="upper left", facecolor=PLOT_BG, edgecolor=GRID, labelcolor=TITLE)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf
