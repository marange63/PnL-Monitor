"""Send Total PnL to the ntfy app on a schedule.

Run by Windows Task Scheduler every 15 min. Gates itself to weekdays,
09:30-16:30 America/New_York, so stray/DST-shifted runs are harmless.

Holdings are re-read from disk on every run (neither `load_and_compute` nor the
`claudedev_shared` loaders cache), so a fresh CSV export is picked up by the next
scheduled run with no restart. The notification carries a `holdings HH:MM` stamp so
a forgotten re-export is visible rather than silent.

Manual test (bypass the market-hours gate):
    python notify_pnl.py --force
"""
import logging
import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests
from claudedev_shared import holdings_paths

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


def holdings_mtime() -> datetime | None:
    """Log each holdings CSV's mtime; return the newest as an ET datetime.

    Returns None if no holdings file could be stat'd -- the caller carries on and
    lets load_and_compute() raise, which the failure alert in main() reports.
    """
    newest = None
    for source, path in holdings_paths().items():
        try:
            mtime = datetime.fromtimestamp(os.stat(path).st_mtime, ET)
        except OSError as exc:
            log.warning("%s holdings unreadable (%s): %s", source, path, exc)
            continue
        log.info("%s holdings %s modified %s", source, path, mtime.strftime("%Y-%m-%d %H:%M:%S"))
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def _post(body: str, title: str, tags: str, priority: str = "default") -> None:
    resp = requests.post(
        NTFY_URL,
        data=body.encode("utf-8"),
        headers={"Title": title, "Tags": tags, "Priority": priority},
        timeout=15,
    )
    resp.raise_for_status()


def send_notification(total_pnl: float, now: datetime, holdings_at: datetime | None) -> None:
    sign = "+" if total_pnl >= 0 else "-"
    body = f"Total PnL: {sign}${abs(total_pnl):,.2f}"
    if holdings_at is not None:
        body += f"\nholdings {holdings_at.strftime('%H:%M')}"
    tags = "chart_with_upwards_trend" if total_pnl >= 0 else "chart_with_downwards_trend"
    # Strip leading zero from hour for a "9:45 AM" style title.
    title = f"PnL @ {now.strftime('%I:%M %p').lstrip('0')} ET"
    _post(body, title, tags)
    log.info("sent: %s", body.replace("\n", " | "))


def send_failure(exc: Exception) -> None:
    """Alert on the same topic so a broken run is visible, not silently missing."""
    try:
        _post(f"{type(exc).__name__}: {exc}", "PnL notifier failed", "warning", priority="high")
    except Exception:  # network down during the error path -- log only
        log.exception("could not send failure notification")


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
    try:
        holdings_at = holdings_mtime()
        df = load_and_compute()
        total = float(df[Col.PNL].sum())
        send_notification(total, now, holdings_at)
    except Exception as exc:
        log.exception("run failed")
        send_failure(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
