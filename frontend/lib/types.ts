import type { components } from "@/lib/api/schema";

type ApiSchemas = components["schemas"];

export type AgentStatus = ApiSchemas["AgentStatus"];
export type Agent = ApiSchemas["AgentOut"];
export type ChatRole = ApiSchemas["ChatMessageIn"]["role"];

export type ChatMessage = Omit<ApiSchemas["ChatMessageOut"], "role"> & {
  id?: string;
  role: ChatRole;
};

export type ChatSession = ApiSchemas["ChatSessionOut"] & {
  message_count?: number;
};

type BrokerChatCompletionsRequest = ApiSchemas["ChatCompletionsRequestIn"];
export type ChatCompletionsRequest = Omit<BrokerChatCompletionsRequest, "messages" | "session_id"> & {
  messages: ChatMessage[];
  /** The UI SDK calls this `id`; it is forwarded as the broker's session_id. */
  client_id?: BrokerChatCompletionsRequest["session_id"];
};

export type UserProfile = {
  id: string;
  email?: string | null;
  display_name?: string | null;
};

/** Which credential a campus tool needs before it can run. */
export type CampusCredentialKind = ApiSchemas["CampusToolOut"]["requires"][number];

export type CampusTool = ApiSchemas["CampusToolOut"] & { enabled: boolean; active: boolean };

export type CampusConnection = ApiSchemas["CampusConnectionOut"] & {
  enabled_tools: string[];
  tools: CampusTool[];
};

export type CampusConnectionInput = ApiSchemas["CampusConnectionIn"];
export type CampusVerifyResult = ApiSchemas["CampusVerifyOut"];
export type Profile = ApiSchemas["ProfileOut"];
export type ProfileInput = ApiSchemas["ProfileIn"];

export type CampusUpdate = {
  id: string;
  type: string;
  title: string;
  summary?: string | null;
  content: string;
  url?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  published_at?: string | null;
  source: string;
  retrieved_at: string;
  origin: "campus" | "mail_fact";
  read: boolean;
};

export type CampusUpdates = {
  mode: "digest" | "feed";
  items: CampusUpdate[];
  personalized_by: { department?: string | null; degree_level?: string | null; campus?: string | null; interests: string[] };
  generated_at: string;
};
