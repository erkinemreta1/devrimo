import { apiFetch } from "@/lib/api/client";
import type { Profile, ProfileInput } from "@/lib/types";

export function getProfile(token: string) {
  return apiFetch<Profile>("/profile", { token });
}

export function patchProfile(token: string, body: ProfileInput) {
  return apiFetch<Profile>("/profile", { method: "PATCH", token, body });
}
