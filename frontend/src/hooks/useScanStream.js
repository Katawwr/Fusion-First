import { useCallback, useRef, useState } from 'react';
import { streamScan } from '../lib/scanApi';

const EMPTY = {
  running: false,
  error: null,
  scanId: null,
  message: '',
  total: 0,
  completed: 0,
  demonstration: true,
  checks: [], // order checks appear
  lanes: {}, // check -> { run, issues, grade }
  cards: {}, // check -> SafetyReportCard
  feed: [], // newest-first ProbeOutcome list
  result: null,
};

// Owns the state of a running scan and drives it from the SSE stream.
export function useScanStream() {
  const [state, setState] = useState(EMPTY);
  const abortRef = useRef(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(EMPTY);
  }, []);

  const start = useCallback(async (body) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ ...EMPTY, running: true });

    const handlers = {
      scan_id: (d) => setState((s) => ({ ...s, scanId: d.scan_id })),
      scan_started: (d) =>
        setState((s) => ({ ...s, total: d.total, message: d.message, demonstration: d.demonstration })),
      check_started: (d) =>
        setState((s) => ({
          ...s,
          message: d.message,
          checks: s.checks.includes(d.check) ? s.checks : [...s.checks, d.check],
          lanes: { ...s.lanes, [d.check]: s.lanes[d.check] || { run: 0, issues: 0, grade: null } },
        })),
      probe_result: (d) => {
        const p = d.probe;
        setState((s) => {
          const lane = s.lanes[p.check] || { run: 0, issues: 0, grade: null };
          return {
            ...s,
            completed: d.completed,
            lanes: {
              ...s.lanes,
              [p.check]: {
                ...lane,
                run: lane.run + 1,
                issues: lane.issues + (p.baseline_issue ? 1 : 0),
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
            [d.check]: { ...(s.lanes[d.check] || { run: 0, issues: 0 }), grade: d.card.grade },
          },
        })),
      scan_completed: (d) => setState((s) => ({ ...s, result: d.result, running: false })),
      error: (d) => setState((s) => ({ ...s, error: d.detail || 'Scan failed', running: false })),
    };

    try {
      await streamScan(body, handlers, controller.signal);
    } catch (e) {
      if (e.name !== 'AbortError') {
        setState((s) => ({ ...s, error: e.message, running: false }));
      }
    }
  }, []);

  return { ...state, start, reset };
}
