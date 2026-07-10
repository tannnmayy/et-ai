import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import MapView from "../components/MapView";
import HexDetailPanel from "../components/HexDetailPanel";
import TopEnforcementSection from "../components/TopEnforcementSection";
import OperationsSnapshot from "../components/OperationsSnapshot";
import { getAirQualityMap, getEnforcementPriority } from "../api/client";
import type { RankedHexagon } from "../api/types";

export default function HomePage() {
  const [selectedHexCell, setSelectedHexCell] = useState<string | null>(null);

  const { data: priorities } = useQuery({
    queryKey: ["enforcementPriority", "bengaluru", 20],
    queryFn: () => getEnforcementPriority("bengaluru", 20),
    staleTime: 60_000,
  });
  const { data: airQualityMap } = useQuery({ queryKey: ["airQualityMap"], queryFn: getAirQualityMap, staleTime: 60_000 });

  const selectedHex = selectedHexCell
    ? priorities?.ranked_hexagons.find((h) => h.h3_cell === selectedHexCell) ?? null
    : null;

  const mapData = airQualityMap?.cells.map((cell) => ({ h3_cell: cell.h3_cell, value: cell.pm25, label: cell.nearest_station, message: cell.message }));

  return (
    <div className="home-page">
      <div className="page-intro"><div><h1>Bengaluru air-quality operations</h1><p>Live source attribution, forecasts, and actionable priorities.</p></div></div>
      <OperationsSnapshot />
      <MapView
        city="bengaluru"
        onHexagonClick={(h3) => setSelectedHexCell(h3)}
        highlightedCells={selectedHexCell ? [selectedHexCell] : []}
        hexagonData={mapData}
      />

      {selectedHex && (
        <HexDetailPanel
          hexagon={selectedHex as RankedHexagon}
          onClose={() => setSelectedHexCell(null)}
        />
      )}

      <TopEnforcementSection city="bengaluru" limit={5} />
    </div>
  );
}
