import type { components } from "./schema";

export type ContractRequest = components["schemas"]["SpikeContractRequest"];
export type ContractResponse = components["schemas"]["SpikeContractResponse"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

export function parseApiError(payload: unknown): ErrorEnvelope["error"] | null {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    return (payload as ErrorEnvelope).error;
  }
  return null;
}
