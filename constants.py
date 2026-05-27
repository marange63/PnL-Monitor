AUTO_UPDATE_INTERVAL_MS = 60_000
AUTO_UPDATE_COUNTDOWN_SECS = 59
BAR_ROW_HEIGHT_INCHES = 0.28
BAR_MIN_HEIGHT_INCHES = 3.0
BAR_RESIZE_DEBOUNCE_MS = 50

SOURCE_COLORS = {"UBS": "#1f77b4", "401K": "#ff7f0e"}
MULTI_SOURCE_COLOR = "#9467bd"  # purple — ticker present in both UBS and 401K
PNL_POS_COLOR = "#2ca02c"
PNL_NEG_COLOR = "#d62728"

BTN_BG = "#2d5a9e"
BTN_BG_ACTIVE = "#3a6fbf"
BTN_FG_DISABLED = "#8899bb"
DELETE_FG = "#b22222"


class Col:
    """DataFrame column names used across data.py, charts.py, and app.py."""
    TICKER = "Ticker Alias"
    SOD_VALUE = "SOD VALUE"
    PNL = "PnL"
    PCT_MOVE = "% Move On Day"
    SOURCE = "Source"
    TAG = "Tag"
    SYMBOL = "SYMBOL"
    DESCRIPTION = "DESCRIPTION"
    LAST_PRICE = "Last Price"
    LAST_CLOSE = "Last Close"
