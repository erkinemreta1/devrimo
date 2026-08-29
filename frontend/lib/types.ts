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
  host_port?: number | null;
  hermes_image_tag?: string | null;
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
