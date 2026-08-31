export type AdminRole = "super_admin" | "operator" | "campus_admin";

export type AdminPrincipal = {
  user_id: string;
  email: string | null;
  role: AdminRole;
  organization_id: string | null;
  permissions: string[];
  bootstrap: boolean;
};

export type Overview = {
  users: number;
  active_users: number;
  onboarding_completed: number;
  campus_connected: number;
  agents: Record<string, number>;
  resident_agents: number;
  attention: Array<{
    user_id: string;
    email: string | null;
    account_status: string;
    agent_status: string | null;
  }>;
  fresh_at: string;
};

export type AdminUser = {
  user_id: string;
  email: string | null;
  display_name: string | null;
  status: string;
  onboarding_completed: boolean;
  agent_status: string | null;
  last_seen_at: string | null;
  created_at: string;
};

export type AgentRow = {
  user_id: string;
  email: string | null;
  display_name: string | null;
  status: string;
  resident: boolean;
  last_active_at: string | null;
  has_error: boolean;
};

export type RuntimeSettings = {
  model_id: string;
  profile: "scholar" | "legacy";
  max_tokens: number;
  legacy_history_runs: number;
  scholar_history_runs: number;
  tool_call_limit: number;
  learning_enabled: boolean;
  input_token_price: number;
  output_token_price: number;
  revision: number;
  has_database_override: boolean;
  updated_at: string | null;
  editable: boolean;
};
