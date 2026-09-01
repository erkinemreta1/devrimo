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

export type AdminUserDetail = {
  status: string;
  last_seen_at: string | null;
  agent: { status: string } | null;
  sessions: { count: number };
  campus: { connected: boolean; enabled_tools: string[] };
};

export type IntegrationOverview = {
  connected_accounts: number;
  items: Array<{
    id: string;
    name_en: string;
    name_tr: string;
    adopted: number;
    verification_failures: number;
  }>;
  commits: Record<string, string>;
};

export type AuditEvent = {
  id: string;
  actor_user_id: string;
  target_user_id: string | null;
  action: string;
  result: string;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type AdminMembership = {
  user_id: string;
  email: string | null;
  role: AdminRole;
  organization_id: string | null;
  bootstrap: boolean;
};

export type SystemHealth = {
  broker: string;
  database: string;
  posthog: string;
  posthog_dashboard_url: string | null;
  supabase_admin: string;
  agent_runtime: string;
  resident_agents: number;
  pool_capacity: number;
  checked_at: string;
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
  knowledge_enabled: boolean;
  knowledge_max_results: number;
  revision: number;
  has_database_override: boolean;
  updated_at: string | null;
  editable: boolean;
};

/** One configured origin of public campus content. */
export type CampusSource = {
  id: string;
  slug: string;
  name: string;
  enabled: boolean;
  adapter: string;
  kind: string;
  base_url: string;
  /**
   * Adapter-specific parsing configuration, edited as raw JSON on purpose.
   * A typed form here would have to change every time an adapter grows an
   * option — the coupling the source registry exists to avoid. Preview is what
   * tells an admin whether what they typed actually parses.
   */
  config: Record<string, unknown>;
  encoding: string | null;
  languages: string[];
  departments: string[];
  degree_levels: string[];
  audience_rules: Record<string, string>;
  refresh_seconds: number;
  max_pages: number;
  max_items: number;
  priority: number;
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  revision: number;
  updated_at: string | null;
  documents: number;
};

export type CampusSourceList = {
  sources: CampusSource[];
  adapters: string[];
  kinds: string[];
  editable: boolean;
  runnable: boolean;
  knowledge_configured: boolean;
};

export type CampusSourceRun = {
  id: string;
  status: string;
  items_seen: number;
  items_written: number;
  items_unchanged: number;
  requests_made: number;
  bytes_fetched: number;
  duration_ms: number;
  error: string | null;
  started_at: string | null;
};

export type CampusSourcePreview = {
  ok: boolean;
  error: string | null;
  error_code: string | null;
  items_seen: number;
  documents?: number;
  duration_ms: number;
  requests_made?: number;
  bytes_fetched?: number;
  items: {
    title: string;
    url: string | null;
    language: string;
    published_at: string | null;
    body_preview: string;
    extra: Record<string, unknown>;
  }[];
};

export type CuratedEntry = {
  id: string;
  kind: "whatsapp_group" | "club" | "event" | "note";
  entry_key: string | null;
  title: string;
  body: string;
  url: string | null;
  language: "tr" | "en";
  departments: string[];
  degree_levels: string[];
  tags: string[];
  valid_from: string | null;
  valid_until: string | null;
  enabled: boolean;
  updated_at: string | null;
};

export type KnowledgeOverview = {
  configured: boolean;
  embedding_model: string;
  embedding_dimensions: number;
  table: string;
  documents_by_source: Record<string, number>;
  documents_total: number;
  reindex_required_after_model_change: boolean;
  can_manage: boolean;
};

export type GradePolicy = {
  scale: Record<string, number>;
  non_graded: string[];
  passing_grades: string[];
  weight_basis: "credit" | "ects";
  retake_replaces: boolean;
  max_credits_per_semester: number;
  notes: string | null;
  revision: number;
  updated_at: string | null;
  editable: boolean;
};
