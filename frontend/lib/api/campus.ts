import { apiFetch } from "@/lib/api/client";
import type {
  CampusConnection,
  CampusConnectionInput,
  CampusVerifyResult,
} from "@/lib/types";

export function getCampusConnection(token: string) {
  return apiFetch<CampusConnection>("/campus/connection", { token });
}

export function putCampusConnection(token: string, body: CampusConnectionInput) {
  return apiFetch<CampusConnection>("/campus/connection", { method: "PUT", token, body });
}

export function deleteCampusConnection(token: string) {
  return apiFetch<CampusConnection>("/campus/connection", { method: "DELETE", token });
}

/** Check credentials without storing them, so the form can validate inline. */
export function verifyCampusCredentials(
  token: string,
  body: { metu_username: string; metu_password: string },
) {
  return apiFetch<CampusVerifyResult>("/campus/connection/verify", {
    method: "POST",
    token,
    body,
  });
}

/** Rebuild the agent container so a pending campus change takes effect. */
export function applyCampusConnection(token: string) {
  return apiFetch<CampusConnection>("/campus/apply", { method: "POST", token, body: {} });
}
