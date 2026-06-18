export const API_BASE =
  (import.meta as any).env?.VITE_API_BASE || "http://localhost:8800";

export interface Stakeholder {
  id: string;
  name: string;
  role: string;
  org: string;
  email?: string;
}

export interface IntakeMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AiEditResult {
  proposed_md: string;
  addressed_comment_ids: string[];
}

export interface IntakeOption {
  label: string;
  advantage: string;
}

export interface IntakeTurn {
  message: string;
  options: IntakeOption[];
  allow_free_text: boolean;
  done: boolean;
  brief: Record<string, string> | null;
  title: string | null;
  client_name: string | null;
  consulting_org: string | null;
  requirements_detail?: string;
}

export interface IntakeExtractResult {
  title: string;
  client_name: string;
  consulting_org: string;
  brief: Record<string, string>;
  requirements_detail: string;
  field_evidence?: Record<string, { quote: string; page: number | null; confidence: string }>;
  extraction_meta: Record<string, unknown>;
}

export interface Project {
  id: string;
  title: string;
  client_name: string;
  consulting_org: string;
  status: string;
  created_at: string;
  brief?: Record<string, string>;
}

export interface Annotation {
  id: string;
  poc_id: string;
  anchor: string;
  domain: string;
  severity: string;
  title: string;
  body: string;
  suggestion: string;
  created_at: string;
}

export interface Review {
  id: string;
  role: string;
  summary: string;
  verdict: string;
  report_md: string;
}

export interface Comment {
  id: string;
  annotation_id: string | null;
  stakeholder_id: string;
  body: string;
  anchor_line?: number | null;
  anchor_slug?: string | null;
  status: "open" | "accepted" | "closed";
  created_at: string;
}

export interface Approval {
  id: string;
  stakeholder_id: string;
  status: string;
  note: string;
}

export interface ApprovalRollup {
  needed: number;
  approved: number;
  ready: boolean;
  approved_roles: string[];
}

export interface ResearchNote {
  id: string;
  topic: string;
  digest: string;
  citations: {
    source_id?: string;
    title: string;
    url: string;
    date?: string;
    sitename?: string;
    author?: string;
  }[];
  created_at: string;
}

export interface Poc {
  id: string;
  title: string;
  version: number;
  markdown: string;
  document_md: string;
  design: any;
}

export interface PocBundle {
  project: Project;
  poc: Poc | null;
  annotations: Annotation[];
  reviews: Review[];
  comments: Comment[];
  approvals: Approval[];
  approval_rollup: ApprovalRollup;
  stakeholders: Stakeholder[];
  research: ResearchNote[];
}

async function req<T>(path: string, opts: RequestInit = {}, role?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(opts.headers as any) };
  if (role) headers["X-Apoc-Role"] = role;
  const res = await fetch(API_BASE + path, { ...opts, headers });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  health: () => req<any>("/api/health"),
  roles: () => req<any>("/api/roles"),
  stakeholders: () => req<Stakeholder[]>("/api/stakeholders"),
  projects: () => req<Project[]>("/api/projects"),
  project: (id: string) => req<Project>(`/api/projects/${id}`),
  createProject: (body: any) => req<{ id: string }>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  intakeChat: (messages: IntakeMessage[]) =>
    req<IntakeTurn>("/api/intake/chat", { method: "POST", body: JSON.stringify({ messages }) }),
  extractIntakePdf: async (file: File): Promise<IntakeExtractResult> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(API_BASE + "/api/intake/extract", { method: "POST", body: form });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json();
  },
  generate: (id: string) => req<any>(`/api/projects/${id}/generate`, { method: "POST" }),
  cancelGenerate: (id: string) => req<any>(`/api/projects/${id}/cancel`, { method: "POST" }),
  deleteProject: (id: string) => req<void>(`/api/projects/${id}`, { method: "DELETE" }),
  pocBundle: (id: string) => req<PocBundle>(`/api/projects/${id}/poc`),
  audit: (id: string) => req<any[]>(`/api/projects/${id}/audit`),
  deckUrl: (pocId: string, role: string) =>
    `${API_BASE}/api/pocs/${pocId}/deck?role=${encodeURIComponent(role)}`,
  addComment: (pocId: string, body: any, role: string) =>
    req<any>(`/api/pocs/${pocId}/comments`, { method: "POST", body: JSON.stringify(body) }, role),
  setApproval: (pocId: string, body: any, role: string) =>
    req<any>(`/api/pocs/${pocId}/approvals`, { method: "POST", body: JSON.stringify(body) }, role),
  saveDocument: (pocId: string, body: any, role: string) =>
    req<any>(`/api/pocs/${pocId}/document`, { method: "POST", body: JSON.stringify(body) }, role),
  setCommentStatus: (pocId: string, commentId: string, status: string, role: string) =>
    req<any>(`/api/pocs/${pocId}/comments/${commentId}/status`,
      { method: "POST", body: JSON.stringify({ status }) }, role),
  bulkSetCommentStatus: (pocId: string, ids: string[], status: string, role: string) =>
    req<any>(`/api/pocs/${pocId}/comments/status`,
      { method: "POST", body: JSON.stringify({ ids, status }) }, role),
  aiEdit: (pocId: string, body: { instruction?: string }, role: string) =>
    req<AiEditResult>(`/api/pocs/${pocId}/ai-edit`,
      { method: "POST", body: JSON.stringify(body) }, role),
  pocChat: (pocId: string, messages: ChatMessage[]) =>
    req<{ reply: string }>(`/api/pocs/${pocId}/chat`,
      { method: "POST", body: JSON.stringify({ messages }) }),
};
