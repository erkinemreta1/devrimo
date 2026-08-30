import { apiFetch } from "@/lib/api/client";

export type MemoryEntry = {
  id: string;
  content: string;
};

export type MemoryList = {
  memories: MemoryEntry[];
};

export function listMemories(token: string) {
  return apiFetch<MemoryList>("/memories", { token });
}

export function clearMemories(token: string) {
  return apiFetch<MemoryList>("/memories", { method: "DELETE", token });
}
