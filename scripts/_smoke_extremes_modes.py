"""Smoke three-mode city extremes (global_worst / global_best / local_peaks)."""
from __future__ import annotations

import time

from backend.app.services.attribution_service import (
    EXTREMES_MODE_GLOBAL_BEST,
    EXTREMES_MODE_GLOBAL_WORST,
    EXTREMES_MODE_LOCAL_PEAKS,
    get_city_extremes,
)


def main() -> None:
    t0 = time.time()
    g = get_city_extremes("bengaluru", n=30, mode=EXTREMES_MODE_GLOBAL_WORST)
    print(
        "global_worst",
        f"{time.time() - t0:.1f}s",
        g.get("error")
        or f"worst={len(g['worst'])} mode={g['mode']} max={g.get('max_fused_pm25')}",
    )
    if "error" in g:
        return
    # Confidence must be absent on Map path
    sample = (g.get("worst") or [{}])[0]
    assert "attribution_confidence_score" not in sample

    t1 = time.time()
    b = get_city_extremes("bengaluru", n=30, mode=EXTREMES_MODE_GLOBAL_BEST)
    print(
        "global_best",
        f"{time.time() - t1:.1f}s",
        b.get("error") or f"best={len(b['best'])} mode={b['mode']}",
    )

    t2 = time.time()
    loc = get_city_extremes("bengaluru", n=50, mode=EXTREMES_MODE_LOCAL_PEAKS)
    print(
        "local_peaks",
        f"{time.time() - t2:.1f}s",
        loc.get("error")
        or f"worst={len(loc['worst'])} mode={loc['mode']} peak_k={loc.get('peak_k')}",
    )

    bad = get_city_extremes("bengaluru", n=5, mode="local_plume")
    print("local_plume rejected", "error" in bad)

    from backend.app.schemas.attribution import CityExtremesResponse

    CityExtremesResponse(**g)
    CityExtremesResponse(**b)
    CityExtremesResponse(**loc)
    print("schema_ok")


if __name__ == "__main__":
    main()
