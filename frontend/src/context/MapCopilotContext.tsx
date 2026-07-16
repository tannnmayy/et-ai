/**
 * Bidirectional Map ↔ Copilot bridge.
 *
 * Map → Copilot: selected station_id / h3_cell / label (preferred location).
 * Copilot → Map: map_actions (highlight hexes/stations, optional focus).
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';

const STORAGE_KEY = 'aqi_sentinel_map_copilot_ctx_v1';
const ACTIONS_KEY = 'aqi_sentinel_map_actions_v1';

export type MapFocusOn = {
  h3_cell?: string | null;
  station_id?: string | null;
  lat?: number | null;
  lng?: number | null;
  label?: string | null;
};

export type CopilotMapActions = {
  highlight_h3_cells?: string[];
  highlight_stations?: string[];
  focus_on?: MapFocusOn | null;
};

export type MapCopilotContextValue = {
  /** Active Map → Copilot location preference */
  station_id?: string;
  h3_cell?: string | null;
  label?: string;
  /** Copilot → Map highlights */
  mapActions: CopilotMapActions | null;
  mapActionsUpdatedAt: number | null;
  setMapContext: (ctx: {
    station_id?: string;
    h3_cell?: string | null;
    label?: string;
  }) => void;
  clearMapContext: () => void;
  /** Apply structured actions returned by Copilot API */
  applyMapActions: (actions: CopilotMapActions | null | undefined) => void;
  clearMapActions: () => void;
};

const MapCopilotContext = createContext<MapCopilotContextValue | null>(null);

function loadStoredCtx(): {
  station_id?: string;
  h3_cell?: string | null;
  label?: string;
} {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const p = JSON.parse(raw) as {
      station_id?: string;
      h3_cell?: string | null;
      label?: string;
    };
    return {
      station_id: p.station_id || undefined,
      h3_cell: p.h3_cell || null,
      label: p.label,
    };
  } catch {
    return {};
  }
}

function loadStoredActions(): {
  mapActions: CopilotMapActions | null;
  mapActionsUpdatedAt: number | null;
} {
  try {
    const raw = sessionStorage.getItem(ACTIONS_KEY);
    if (!raw) return { mapActions: null, mapActionsUpdatedAt: null };
    const p = JSON.parse(raw) as {
      mapActions?: CopilotMapActions | null;
      mapActionsUpdatedAt?: number | null;
    };
    return {
      mapActions: p.mapActions ?? null,
      mapActionsUpdatedAt: p.mapActionsUpdatedAt ?? null,
    };
  } catch {
    return { mapActions: null, mapActionsUpdatedAt: null };
  }
}

export function MapCopilotProvider({ children }: { children: React.ReactNode }) {
  const [ctx, setCtx] = useState(loadStoredCtx);
  const [{ mapActions, mapActionsUpdatedAt }, setActionsState] = useState(loadStoredActions);

  const setMapContext = useCallback(
    (next: { station_id?: string; h3_cell?: string | null; label?: string }) => {
      const cleaned = {
        station_id: next.station_id || undefined,
        h3_cell: next.h3_cell || null,
        label: next.label,
      };
      setCtx(cleaned);
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(cleaned));
      } catch {
        /* ignore */
      }
    },
    [],
  );

  const clearMapContext = useCallback(() => {
    setCtx({});
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const applyMapActions = useCallback((actions: CopilotMapActions | null | undefined) => {
    if (!actions) return;
    const cleaned: CopilotMapActions = {
      highlight_h3_cells: Array.isArray(actions.highlight_h3_cells)
        ? actions.highlight_h3_cells.map(String).filter(Boolean).slice(0, 12)
        : [],
      highlight_stations: Array.isArray(actions.highlight_stations)
        ? actions.highlight_stations.map(String).filter(Boolean).slice(0, 12)
        : [],
      focus_on: actions.focus_on || null,
    };
    if (
      !(cleaned.highlight_h3_cells?.length) &&
      !(cleaned.highlight_stations?.length) &&
      !cleaned.focus_on
    ) {
      return;
    }
    const ts = Date.now();
    setActionsState({ mapActions: cleaned, mapActionsUpdatedAt: ts });
    try {
      sessionStorage.setItem(
        ACTIONS_KEY,
        JSON.stringify({ mapActions: cleaned, mapActionsUpdatedAt: ts }),
      );
    } catch {
      /* ignore */
    }
  }, []);

  const clearMapActions = useCallback(() => {
    setActionsState({ mapActions: null, mapActionsUpdatedAt: null });
    try {
      sessionStorage.removeItem(ACTIONS_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(
    () => ({
      ...ctx,
      mapActions,
      mapActionsUpdatedAt,
      setMapContext,
      clearMapContext,
      applyMapActions,
      clearMapActions,
    }),
    [
      ctx,
      mapActions,
      mapActionsUpdatedAt,
      setMapContext,
      clearMapContext,
      applyMapActions,
      clearMapActions,
    ],
  );

  return (
    <MapCopilotContext.Provider value={value}>{children}</MapCopilotContext.Provider>
  );
}

export function useMapCopilotContext(): MapCopilotContextValue {
  const v = useContext(MapCopilotContext);
  if (!v) {
    return {
      mapActions: null,
      mapActionsUpdatedAt: null,
      setMapContext: () => undefined,
      clearMapContext: () => undefined,
      applyMapActions: () => undefined,
      clearMapActions: () => undefined,
    };
  }
  return v;
}
