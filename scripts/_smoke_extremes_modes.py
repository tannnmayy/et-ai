"""Smoke dual-mode city extremes."""
from __future__ import annotations

import time

from backend.app.services.attribution_service import (
    EXTREMES_MODE_GLOBAL,
    EXTREMES_MODE_LOCAL_PEAKS,
    get_city_extremes,
)


def main() -> None:
    t0 = time.time()
    g = get_city_extremes("bengaluru", n=30, mode=EXTREMES_MODE_GLOBAL)
    print(
        "global",
        f"{time.time() - t0:.1f}s",
        g.get("error")
        or f"worst={len(g['worst'])} mode={g['mode']} max={g.get('max_fused_pm25')} ties={g.get('tie_count_at_max')}",
    )
    if "error" in g:
        return
    glats = [h["center_lat"] for h in g["worst"]]
    print("global lat", min(glats), max(glats), "mean", sum(glats) / len(glats))

    t1 = time.time()
    loc = get_city_extremes("bengaluru", n=30, mode=EXTREMES_MODE_LOCAL_PEAKS)
    print(
        "local",
        f"{time.time() - t1:.1f}s",
        loc.get("error")
        or f"worst={len(loc['worst'])} mode={loc['mode']} peak_k={loc.get('peak_k')}",
    )
    if "error" in loc:
        return
    llats = [h["center_lat"] for h in loc["worst"]]
    print("local lat", min(llats), max(llats), "mean", sum(llats) / len(llats))
    g_ids = {h["h3_cell"] for h in g["worst"]}
    l_ids = {h["h3_cell"] for h in loc["worst"]}
    print("overlap", len(g_ids & l_ids), "local_only", len(l_ids - g_ids))
    print("local names", [h.get("name") or h["h3_cell"][:10] for h in loc["worst"][:10]])

    # Schema validation
    from backend.app.schemas.attribution import CityExtremesResponse

    CityExtremesResponse(**g)
    CityExtremesResponse(**loc)
    print("schema_ok")


if __name__ == "__main__":
    main()
