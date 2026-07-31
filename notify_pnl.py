"""Send Total PnL to the ntfy app on a schedule.

Run by Windows Task Scheduler every 15 min. Gates itself to weekdays,
09:30-16:30 America/New_York, so stray/DST-shifted runs are harmless.

Manual test (bypass the market-hours gate):
    python notify_pnl.py --force
"""
import logging
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests

from data import load_and_compute
from constants import Col

NTFY_TOPIC = "EwtinPnL-yfj58gdt"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
ET = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 30)

log = logging.getLogger("notify_pnl")


def in_market_window(now: datetime) -> bool:
    """True on weekdays between 09:30 and 16:30 ET (inclusive)."""
    if now.weekday() >= 5:  # Sat/Sun
        return False
    return MARKET_OPEN <= now.timetz().replace(tzinfo=None) <= MARKET_CLOSE


def send_notification(total_pnl: float, now: datetime) -> None:
    sign = "+" if total_pnl >= 0 else "-"
    body = f"Total PnL: {sign}${abs(total_pnl):,.2f}"
    tags = "chart_with_upwards_trend" if total_pnl >= 0 else "chart_with_downwards_trend"
    # Strip leading zero from hour for a "9:45 AM" style title.
    title = f"PnL @ {now.strftime('%I:%M %p').lstrip('0')} ET"
    requests.post(
        NTFY_URL,
        data=body.encode("utf-8"),
        headers={"Title": title, "Tags": tags},
        timeout=15,
    )
    log.info("sent: %s", body)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    force = "--force" in sys.argv
    now = datetime.now(ET)
    if not force and not in_market_window(now):
        log.info("outside market window (%s ET) - skipping", now.strftime("%a %H:%M"))
        return 0
    df = load_and_compute()
    total = float(df[Col.PNL].sum())
    send_notification(total, now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
