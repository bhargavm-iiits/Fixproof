import { useQuery } from "@tanstack/react-query";
import { api, type Health } from "../api";

export function useHealth() {
  return useQuery<Health>({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 20_000,
  });
}
