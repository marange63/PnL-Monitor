import sys
from pathlib import Path

# Make project root importable so `import data`, `import charts` work
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import pytest

from constants import Col


@pytest.fixture
def sample_positions() -> pd.DataFrame:
    """Synthetic holdings DataFrame mirroring what load_and_compute returns."""
    return pd.DataFrame({
        Col.TICKER:      ["AAPL", "AAPL", "MSFT", "NVDA"],
        Col.SYMBOL:      ["AAPL", "AAPL", "MSFT", "NVDA"],
        Col.DESCRIPTION: ["Apple", "Apple 401k", "Microsoft", "Nvidia"],
        Col.SOURCE:      ["UBS", "401K", "UBS", "UBS"],
        Col.TAG:         ["Tech", "Tech", "Tech", "Semis"],
        Col.SOD_VALUE:   [10_000.0, 5_000.0, 8_000.0, 12_000.0],
        Col.LAST_PRICE:  [180.0, 180.0, 410.0, 800.0],
        Col.LAST_CLOSE:  [177.0, 177.0, 400.0, 820.0],
        Col.PCT_MOVE:    [0.01695, 0.01695, 0.025, -0.02439],
        Col.PNL:         [169.5, 84.75, 200.0, -292.68],
    })
