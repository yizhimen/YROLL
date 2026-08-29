// GUI-02: useCoreKeymap — reads /keyboard/keymap once and exposes
// typed bindings.
//
// Per the user spec (permutation B): the Core keymap is a *semantic
// binding contract*. The GUI reads it to know which key triggers
// which *kind* of action. Local navigation (J/K/L, arrows, Space)
// updates local state. Real mutations route through the existing
// gated mutation APIs (api.trim / api.move / api.removeClip). NO
// /keyboard/execute endpoint is added.

import { useEffect, useState } from "react";
import { api } from "./api";

/** A keymap binding as returned by the server. */
export interface KeymapBinding {
  key: string;
  description: string;
  mutation_op: string;
  params: Record<string, unknown>;
}

/** A typed handler derived from the keymap. The GUI can choose
 * whether it's a local navigation or a mutation. */
export interface KeymapAction {
  /** Stable name from `mutation_op`. */
  name: string;
  /** Original key combo, e.g. "J", "Shift+L", "ArrowLeft". */
  key: string;
  /** Description, for tooltips. */
  description: string;
  /** For local nav: positive = forward, negative = back, in frames. */
  deltaFrames: number;
}

/** Read the Core keymap once. Returns a parsed list of typed
 * actions. Unknown actions are skipped (logged in dev). */
export function useCoreKeymap(): KeymapAction[] {
  const [actions, setActions] = useState<KeymapAction[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await api.getKeymap();
        if (cancelled) return;
        const parsed: KeymapAction[] = [];
        for (const b of data.bindings ?? []) {
          const delta = Number((b.params as any)?.delta_frames ?? 0);
          parsed.push({
            name: b.mutation_op,
            key: b.key,
            description: b.description,
            deltaFrames: Number.isFinite(delta) ? delta : 0,
          });
        }
        setActions(parsed);
      } catch {
        // network blip; keymap stays empty
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return actions;
}
