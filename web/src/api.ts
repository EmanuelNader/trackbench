const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { error?: string };
      if (body.error) detail = body.error;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type RunSummary = {
  id: string;
  runKey: string;
  commitSha: string;
  createdAt: string;
  notes: string | null;
  mota: number | null;
  ids: number | null;
  motp: number | null;
  fp: number | null;
  fn: number | null;
  frag: number | null;
  metrics: Record<string, number>;
  nFailures: number;
  nScenes: number;
};

export type SceneMetrics = {
  sceneId: string;
  name: string;
  numFrames: number;
  weather: string | null;
  timeOfDay: string | null;
  metrics: Record<string, number>;
};

export type RunDetail = {
  id: string;
  runKey: string;
  commitSha: string;
  createdAt: string;
  configJson: unknown;
  notes: string | null;
  metrics: Record<string, number>;
  scenes: SceneMetrics[];
  nFailures: number;
  nClusters: number;
};

export type ClusterSummary = {
  id: string;
  runId: string;
  label: string | null;
  size: number;
  centroidJson: Record<string, unknown>;
};

export type Tag = { id: string; name: string; author: string };

export type FailureEvent = {
  id: string;
  runId: string;
  sceneId: string;
  sceneName?: string;
  frame: number;
  t: number;
  kind: string;
  trackId: number | null;
  gtId: string | null;
  severity: number;
  features: Record<string, unknown>;
  clusterId?: string | null;
  tags: Tag[];
};

export type ClusterEventsResponse = {
  cluster: ClusterSummary;
  total: number;
  limit: number;
  offset: number;
  events: FailureEvent[];
};

export type BevBox = {
  id?: string | number;
  cls?: string;
  x: number;
  y: number;
  z?: number;
  l?: number;
  w?: number;
  h?: number;
  yaw?: number;
  score?: number;
  state?: string;
  visibility?: number;
};

export type FramePayload = {
  sceneId: string;
  frame: number;
  t: number;
  ego: { x: number; y: number; yaw: number };
  gt: BevBox[];
  tracks: BevBox[];
  sources: { gt: string; tracks: string };
};

export const TAG_OPTIONS = [
  "occlusion",
  "known-issue",
  "needs-relabel",
  "wontfix",
] as const;

export type TagName = (typeof TAG_OPTIONS)[number];

export const api = {
  listRuns: () => request<RunSummary[]>("/runs"),
  getRun: (id: string) => request<RunDetail>(`/runs/${id}`),
  listClusters: (runId: string) =>
    request<ClusterSummary[]>(`/runs/${runId}/clusters`),
  getClusterEvents: (clusterId: string, offset = 0, limit = 50) =>
    request<ClusterEventsResponse>(
      `/clusters/${clusterId}/events?offset=${offset}&limit=${limit}`,
    ),
  listRunEvents: (runId: string, sceneId?: string) => {
    const q = sceneId ? `?sceneId=${encodeURIComponent(sceneId)}` : "";
    return request<FailureEvent[]>(`/runs/${runId}/events${q}`);
  },
  getFrame: (sceneId: string, frame: number) =>
    request<FramePayload>(`/scenes/${encodeURIComponent(sceneId)}/frames/${frame}`),
  getEvent: (id: string) => request<FailureEvent>(`/events/${id}`),
  addTag: (eventId: string, name: TagName, author = "triage") =>
    request<Tag>(`/events/${eventId}/tags`, {
      method: "POST",
      body: JSON.stringify({ name, author }),
    }),
  removeTag: (eventId: string, name: string) =>
    request<void>(`/events/${eventId}/tags/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
  bootstrapDemo: () =>
    request<{
      runId: string;
      runKey: string;
      sceneId: string;
      nFailures: number;
      nClusters: number;
    }>("/demo/bootstrap"),
};
