/**
 * Static fallbacks for campus copy.
 *
 * The authoritative tool list now comes from the broker
 * (`GET /api/campus/connection` → `tools`), because only the broker knows
 * which servers a student actually has credentials for. What's left here is
 * the copy that doesn't depend on that: prompts to seed an empty thread.
 */
export const STARTER_PROMPTS = [
  "When is the add/drop deadline this semester?",
  "Summarize this week's ODTÜClass announcements",
  "What is my CGPA from my transcript?",
  "List my upcoming assignment deadlines",
] as const;
