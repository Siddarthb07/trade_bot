import { useCallback, useEffect, useState } from "react";

export type HoldDisplayMode = "days" | "weeks" | "both";

export const HOLD_PREFS_KEY = "tradebot_hold_prefs";
export const HOLD_PREFS_EVENT = "tradebot-hold-prefs";

function readMode(): HoldDisplayMode {
  try {
    const raw = localStorage.getItem(HOLD_PREFS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.hold_display_mode === "days" || parsed.hold_display_mode === "weeks" || parsed.hold_display_mode === "both") {
        return parsed.hold_display_mode;
      }
    }
  } catch {
    /* ignore */
  }
  return "both";
}

export function useHoldPrefs(): HoldDisplayMode {
  const [mode, setMode] = useState<HoldDisplayMode>(readMode);

  const refresh = useCallback(() => setMode(readMode()), []);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === HOLD_PREFS_KEY) refresh();
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener(HOLD_PREFS_EVENT, refresh);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(HOLD_PREFS_EVENT, refresh);
    };
  }, [refresh]);

  return mode;
}

export function saveHoldDisplayMode(mode: HoldDisplayMode) {
  localStorage.setItem(HOLD_PREFS_KEY, JSON.stringify({ hold_display_mode: mode }));
  window.dispatchEvent(new Event(HOLD_PREFS_EVENT));
}
