export type AgentStatus =
  | "provisioning"
  | "running"
  | "stopped"
  | "error"
  | "destroying";

export type Agent = {
  id: string;
  user_id?: string;
  status: AgentStatus;
  created_at?: string;
  updated_at?: string;
  error_detail?: string | null;
};

export type ChatRole = "system" | "user" | "assistant";

export type ChatMessage = {
  id?: string;
  role: ChatRole;
  content: string;
  created_at?: string;
};

export type ChatSession = {
  id: string;
  title?: string | null;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
};

export type ChatCompletionsRequest = {
  messages: ChatMessage[];
  client_id?: string;
  stream?: boolean;
  model?: string;
};

export type UserProfile = {
  id: string;
  email?: string | null;
  display_name?: string | null;
};

/** Which credential a campus tool needs before it can run. */
export type CampusCredentialKind = "metu_password" | "odtuclass";

export type CampusTool = {
  id: string;
  name_en: string;
  name_tr: string;
  description_en: string;
  description_tr: string;
  /** What the student is trusting this tool with. Shown verbatim as consent copy. */
  scope_en: string;
  scope_tr: string;
  requires: CampusCredentialKind[];
  default_enabled: boolean;
  /** The student chose it. */
  enabled: boolean;
  /** Chosen *and* backed by credentials that satisfy `requires`, so it is really running. */
  active: boolean;
};

export type CampusConnection = {
  connected: boolean;
  metu_username?: string | null;
  has_password: boolean;
  has_odtuclass_token: boolean;
  odtuclass_base_url?: string | null;
  locale: "tr" | "en";
  enabled_tools: string[];
  verified_at?: string | null;
  verification_error?: string | null;
  /** A saved change is not yet live in the agent container. */
  needs_restart: boolean;
  tools: CampusTool[];
};

export type CampusConnectionInput = {
  metu_username: string;
  /** Omit to keep the stored password; "" clears it. */
  metu_password?: string;
  odtuclass_token?: string;
  odtuclass_base_url?: string;
  locale?: "tr" | "en";
  enabled_tools?: string[];
  skip_verification?: boolean;
};

export type CampusVerifyResult = {
  ok: boolean;
  unreachable: boolean;
  detail?: string | null;
};

export type Profile = {
  user_id: string;
  display_name?: string | null;
  department?: string | null;
  locale: "tr" | "en";
  onboarding_step?: string | null;
  onboarding_completed: boolean;
  onboarding_completed_at?: string | null;
};

export type ProfileInput = {
  display_name?: string | null;
  department?: string | null;
  locale?: "tr" | "en";
  onboarding_step?: string | null;
  onboarding_completed?: boolean;
};
