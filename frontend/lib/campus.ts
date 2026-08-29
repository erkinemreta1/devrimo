export const CAMPUS_MCP_TOOLS = [
  {
    id: "odas",
    name: "ODTÜClass",
    description: "Announcements, assignments, and course materials",
  },
  {
    id: "catalog",
    name: "Course catalog",
    description: "Codes, credits, and prerequisites",
  },
  {
    id: "calendar",
    name: "Academic calendar",
    description: "Add/drop, exams, and holidays",
  },
  {
    id: "library",
    name: "Library",
    description: "Hours, holds, and article search",
  },
  {
    id: "campus",
    name: "Campus",
    description: "Buildings, rings, and study spots",
  },
] as const;

export const STARTER_PROMPTS = [
  "When is the add/drop deadline this semester?",
  "Help me plan CENG 140 this week",
  "Where can I study on campus tonight?",
  "Summarize this week's ODTÜClass announcements",
] as const;
