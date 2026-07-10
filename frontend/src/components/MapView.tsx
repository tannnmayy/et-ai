import { useEffect, useRef, useState } from "react";
import { Loader } from "@googlemaps/js-api-loader";
import { useQuery } from "@tanstack/react-query";
import { cellToBoundary } from "h3-js";
import { getCityGridAttribution } from "../api/client";
import type { HexagonAttribution } from "../api/types";

const BENGALURU_CENTER: google.maps.LatLngLiteral = { lat: 12.9716, lng: 77.5946 };
const DEFAULT_ZOOM = 12;
const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

const AQI_COLORS: Record<string, { fill: string; text: string }> = {
  Good: { fill: "#4CAF50", text: "#1D1D1F" },
  Satisfactory: { fill: "#A9C93A", text: "#1D1D1F" },
  Moderate: { fill: "#F5C518", text: "#1D1D1F" },
  Poor: { fill: "#F58220", text: "#FFFFFF" },
  VeryPoor: { fill: "#E2401C", text: "#FFFFFF" },
  Severe: { fill: "#7E0023", text: "#FFFFFF" },
};

const CPCB_BREAKPOINTS = [
  { max: 30, band: "Good" },
  { max: 60, band: "Satisfactory" },
  { max: 90, band: "Moderate" },
  { max: 120, band: "Poor" },
  { max: 250, band: "VeryPoor" },
  { max: Infinity, band: "Severe" },
];

function pm25ToBand(pm25: number | null): string {
  if (pm25 === null || pm25 === undefined) return "Moderate";
  for (const bp of CPCB_BREAKPOINTS) {
    if (pm25 <= bp.max) return bp.band;
  }
  return "Severe";
}

function pm25ToAQIColor(pm25: number | null) {
  return AQI_COLORS[pm25ToBand(pm25)] || AQI_COLORS.Moderate;
}

interface MapViewProps {
  city?: string;
  colorBy?: "fused_pm25" | "priority_score";
  onHexagonClick?: (h3Cell: string) => void;
  highlightedCells?: string[];
  hexagonData?: Array<{ h3_cell: string; value: number }>;
  fullHeight?: boolean;
}

export default function MapView({
  city = "bengaluru",
  colorBy = "fused_pm25",
  onHexagonClick,
  highlightedCells = [],
  hexagonData,
  fullHeight = false,
}: MapViewProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<google.maps.Map | null>(null);
  const dataLayerRef = useRef<google.maps.Data | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["cityGridAttribution", city],
    queryFn: () => getCityGridAttribution(city),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!GOOGLE_MAPS_API_KEY) {
      setMapError("Google Maps API key not configured. Add VITE_GOOGLE_MAPS_API_KEY to your frontend/.env file.");
      return;
    }

    const loader = new Loader({
      apiKey: GOOGLE_MAPS_API_KEY,
      version: "weekly",
    });

    loader
      .load()
      .then(() => {
        setMapLoaded(true);
      })
      .catch((err) => {
        // Google Maps JS API authentication failures surface here (e.g. key not
        // authorised, Maps JavaScript API not enabled, billing not set up).
        // Distinguish from a missing key so debugging is unambiguous.
        setMapError(
          "Google Maps failed to load — check that your API key is valid and has the Maps JavaScript API enabled. " +
            `(${err.message})`
        );
      });
  }, []);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current || mapInstanceRef.current) return;

    const map = new google.maps.Map(mapRef.current, {
      center: BENGALURU_CENTER,
      zoom: DEFAULT_ZOOM,
      mapTypeId: google.maps.MapTypeId.ROADMAP,
      streetViewControl: false,
      mapTypeControl: false,
      fullscreenControl: false,
      styles: [
        { featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] },
      ],
    });

    mapInstanceRef.current = map;

    const dataLayer = new google.maps.Data({ map });
    dataLayerRef.current = dataLayer;

    return () => {
      mapInstanceRef.current = null;
      dataLayerRef.current = null;
    };
  }, [mapLoaded]);

  useEffect(() => {
    const dataLayer = dataLayerRef.current;
    const map = mapInstanceRef.current;
    if (!dataLayer || !map) return;

    const hexagons = hexagonData || data?.hexagons || [];
    if (hexagons.length === 0) return;

    dataLayer.forEach((f) => dataLayer.remove(f));

    const features: google.maps.Data.Feature[] = [];

    for (const hex of hexagons) {
      let value: number | null;
      if (hexagonData) {
        value = (hex as { value: number }).value;
      } else {
        const attr = hex as HexagonAttribution;
        value = attr.fused_pm25 ?? null;
      }

      try {
        const boundary = cellToBoundary((hex as HexagonAttribution).h3_cell || (hex as { h3_cell: string }).h3_cell);
        const coords = boundary.map((coord) => ({ lat: coord[0], lng: coord[1] }));

        const feature = new google.maps.Data.Feature({
          geometry: new google.maps.Data.Polygon([coords]),
          properties: {
            h3_cell: (hex as HexagonAttribution).h3_cell || (hex as { h3_cell: string }).h3_cell,
            value,
          },
        });

        features.push(feature);
      } catch {
        // skip invalid hexagons
      }
    }

    for (const feature of features) {
      dataLayer.add(feature);
    }

    dataLayer.setStyle((feature) => {
      const val = feature.getProperty("value") as number | null;
      const h3 = feature.getProperty("h3_cell") as string;
      const color = pm25ToAQIColor(val);
      const isHighlighted = highlightedCells.includes(h3);

      return {
        fillColor: isHighlighted ? color.fill : color.fill,
        fillOpacity: isHighlighted ? 0.75 : 0.55,
        strokeWeight: isHighlighted ? 2 : 1,
        strokeColor: isHighlighted ? "#1D1D1F" : "#D2D2D7",
        zIndex: isHighlighted ? 2 : 1,
      };
    });

    const clickListener = dataLayer.addListener("click", (event: google.maps.Data.MouseEvent) => {
      const h3 = event.feature.getProperty("h3_cell") as string;
      if (h3 && onHexagonClick) {
        onHexagonClick(h3);
      }
    });

    return () => {
      google.maps.event.removeListener(clickListener);
    };
  }, [data, hexagonData, highlightedCells, onHexagonClick]);

  if (mapError) {
    return (
      <div className={`map-container${fullHeight ? " map-container--full" : ""}`}>
        <div className="map-placeholder">
          <div className="map-placeholder__error">
            <p>{mapError}</p>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading || !mapLoaded) {
    return (
      <div className={`map-container${fullHeight ? " map-container--full" : ""}`}>
        <div className="map-placeholder">
          <div className="map-placeholder__spinner" />
          <p>Loading map data...</p>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className={`map-container${fullHeight ? " map-container--full" : ""}`}>
        <div className="map-placeholder">
          <div className="map-placeholder__error">
            <p>Couldn't load live air quality data</p>
            <p style={{ fontSize: 12, marginTop: 4 }}>{(error as Error)?.message}</p>
            <button className="map-placeholder__retry" onClick={() => refetch()} type="button">
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`map-container${fullHeight ? " map-container--full" : ""}`}>
      <div ref={mapRef} className="map-container__map" />
    </div>
  );
}
