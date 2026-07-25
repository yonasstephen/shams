import { useRef, useCallback } from 'react';

/**
 * Guards against out-of-order async responses ("latest request wins").
 *
 * Data-fetching pages fire overlapping requests on rapid input (sort clicks,
 * week navigation, filter changes). Without a guard, a slower earlier response
 * can resolve after a faster later one and overwrite fresh data with stale data.
 *
 * Usage:
 *   const { begin, isCurrent } = useLatestRequest();
 *   const token = begin();
 *   const data = await api.fetch(...);
 *   if (!isCurrent(token)) return; // a newer request superseded this one
 *   setState(data);
 */
export function useLatestRequest() {
  const counter = useRef(0);

  /** Start a new request and return its token (invalidates all prior tokens). */
  const begin = useCallback(() => {
    counter.current += 1;
    return counter.current;
  }, []);

  /** True only if `token` belongs to the most recently started request. */
  const isCurrent = useCallback((token: number) => token === counter.current, []);

  return { begin, isCurrent };
}
