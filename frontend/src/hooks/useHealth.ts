import { useQuery } from "@tanstack/react-query";

import { fetchLiveness, fetchReadiness, healthQueryKeys } from "../api/health";

const REFRESH_INTERVAL_MS = 30_000;

export function useHealthQueries() {
  const liveness = useQuery({
    queryKey: healthQueryKeys.live,
    queryFn: fetchLiveness,
    refetchInterval: REFRESH_INTERVAL_MS,
  });

  const readiness = useQuery({
    queryKey: healthQueryKeys.ready,
    queryFn: fetchReadiness,
    refetchInterval: REFRESH_INTERVAL_MS,
    retry: false,
  });

  return { liveness, readiness };
}
