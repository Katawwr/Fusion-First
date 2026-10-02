import { useCallback, useRef, useState } from "react";
import { streamScan } from "../lib/scanApi";

const EMPTY = {
  running: false,
  error: null,
  errorCode: null,
  scanId: null,
  message: "",
  total: 0,
  completed: 0,
  // null until the server says: never flash a "demo" banner over a live run.
  demonstration: null,
  checks: [], // order checks appear
  lanes: {}, // check -> { run, issues, unscored, grade }
  cards: {}, // check -> SafetyReportCard
  feed: [], // newest-first ProbeOutcome list
  result: null,
};

const LANE = { run: 0, issues: 0, unscored: 0, grade: null };

// Owns the state of a running scan and drives it from the SSE stream.
export function useScanStream() {
  const [state, setState] = useState(EMPTY);
  const abortRef = useRef(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(EMPTY);
  }, []);

  // `onCompleted(result)` fires once when the scan finishes (lets the page advance without an effect).
  const start = useCallback(async (body, { onCompleted } = {}) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ ...EMPTY, running: true });

    const handlers = {
      scan_id: (d) => setState((s) => ({ ...s, scanId: d.scan_id })),
      scan_started: (d) =>
        setState((s) => ({
          ...s,
          total: d.total,
          message: d.message,
          demonstration: d.demonstration,
        })),
      check_started: (d) =>
        setState((s) => ({
          ...s,
          message: d.message,
          checks: s.checks.includes(d.check) ? s.checks : [...s.checks, d.check],
          lanes: { ...s.lanes, [d.check]: s.lanes[d.check] || LANE },
        })),
      probe_result: (d) => {
        const p = d.probe;
        setState((s) => {
          const lane = s.lanes[p.check] || LANE;
          const unscored = p.baseline_issue === null || p.baseline_issue === undefined;
          return {
            ...s,
            completed: d.completed,
            lanes: {
              ...s.lanes,
              [p.check]: {
                ...lane,
                run: lane.run + 1,
                issues: lane.issues + (p.baseline_issue === true ? 1 : 0),
                unscored: lane.unscored + (unscored ? 1 : 0),
              },
            },
            feed: [p, ...s.feed].slice(0, 60),
          };
        });
      },
      check_completed: (d) =>
        setState((s) => ({
          ...s,
          cards: { ...s.cards, [d.check]: d.card },
          lanes: {
            ...s.lanes,
            [d.check]: { ...(s.lanes[d.check] || LANE), grade: d.card.grade },
          },
        })),
      scan_completed: (d) => {
        setState((s) => ({ ...s, result: d.result, running: false }));
        onCompleted?.(d.result);
      },
      error: (d) =>
        setState((s) => ({
          ...s,
          error: d.message || d.detail || "The scan failed.",
          errorCode: d.code || "internal",
          running: false,
        })),
    };

    try {
      await streamScan(body, handlers, controller.signal);
    } catch (e) {
      if (e.name !== "AbortError") {
        setState((s) => ({
          ...s,
          error: e.message || "The scan failed.",
          errorCode: e.code || "network",
          running: false,
        }));
      }
    }
  }, []);

  return { ...state, start, reset };
}
