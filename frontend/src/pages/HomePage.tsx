import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import MapView from "../components/MapView";
import HexDetailPanel from "../components/HexDetailPanel";
import TopEnforcementSection from "../components/TopEnforcementSection";
import { getCityGridAttribution } from "../api/client";
import type { HexagonAttribution, RankedHexagon } from "../api/types";

export default function HomePage() {
  const [selectedHexCell, setSelectedHexCell] = useState<string | null>(null);

  const { data: gridData } = useQuery({
    queryKey: ["cityGridAttribution", "bengaluru"],
    queryFn: () => getCityGridAttribution("bengaluru"),
    staleTime: 60_000,
  });

  const selectedHex = selectedHexCell
    ? gridData?.hexagons.find((h) => h.h3_cell === selectedHexCell) ?? null
    : null;

  const selectedRanked: RankedHexagon | null = null;

  return (
    <div className="home-page">
      <MapView
        city="bengaluru"
        onHexagonClick={(h3) => setSelectedHexCell(h3)}
        highlightedCells={selectedHexCell ? [selectedHexCell] : []}
      />

      {(selectedHex || selectedRanked) && (
        <HexDetailPanel
          hexagon={selectedRanked || (selectedHex as HexagonAttribution)}
          onClose={() => setSelectedHexCell(null)}
        />
      )}

      <TopEnforcementSection city="bengaluru" limit={5} />
    </div>
  );
}
