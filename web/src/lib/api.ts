const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface FetchOptions extends RequestInit {
  params?: Record<string, string | number | undefined>;
}

async function fetchAPI<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { params, ...fetchOptions } = options;

  let url = `${API_URL}/api${endpoint}`;

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += `?${queryString}`;
    }
  }

  const response = await fetch(url, {
    ...fetchOptions,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...fetchOptions.headers,
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      // Redirect to login
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

// Auth
export const auth = {
  login: (password: string) =>
    fetchAPI<{ message: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  logout: () =>
    fetchAPI<{ message: string }>("/auth/logout", {
      method: "POST",
    }),

  me: () => fetchAPI<{ authenticated: boolean }>("/auth/me"),
};

// Messages
export interface Person {
  id: number;
  display_name: string | null;
  avatar_url: string | null;
}

export interface Message {
  id: number;
  content: string | null;
  timestamp: string;
  sender: Person | null;
  reply_to_message_id: number | null;
  reply_to_sender: Person | null;
}

export interface MessageListResponse {
  messages: Message[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const messages = {
  list: (params?: {
    page?: number;
    page_size?: number;
    sender_id?: number;
    search?: string;
  }) => fetchAPI<MessageListResponse>("/messages", { params }),

  get: (id: number) => fetchAPI<Message>(`/messages/${id}`),

  search: (q: string, page?: number) =>
    fetchAPI<MessageListResponse>("/messages/search", {
      params: { q, page },
    }),
};

// People
export interface PersonFull {
  id: number;
  matrix_user_id: string;
  display_name: string | null;
  avatar_url: string | null;
  fb_profile_url: string | null;
  notes: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  // AI Summary fields
  ai_summary: string | null;
  ai_summary_generated_at: string | null;
  ai_summary_stale: boolean;
}

export interface GenerateSummaryError {
  detail: string;
  retry_after?: number;
}

// Convert mxc:// URL to HTTP URL
export function mxcToHttp(mxcUrl: string | null): string | null {
  if (!mxcUrl || !mxcUrl.startsWith("mxc://")) return null;
  const parts = mxcUrl.replace("mxc://", "").split("/");
  if (parts.length < 2) return null;
  const [serverName, mediaId] = parts;
  return `http://localhost:8008/_matrix/media/v3/download/${serverName}/${mediaId}`;
}

export interface PeopleListResponse {
  people: PersonFull[];
  total: number;
}

export const people = {
  list: (search?: string) =>
    fetchAPI<PeopleListResponse>("/people", { params: { search } }),

  get: (id: number) => fetchAPI<PersonFull>(`/people/${id}`),

  update: (id: number, notes: string) =>
    fetchAPI<PersonFull>(`/people/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ notes }),
    }),

  messages: (id: number, page?: number) =>
    fetchAPI<MessageListResponse>(`/people/${id}/messages`, {
      params: { page },
    }),

  generateSummary: async (id: number): Promise<PersonFull> => {
    const response = await fetch(`${API_URL}/api/people/${id}/generate-summary`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      if (response.status === 429) {
        const error: GenerateSummaryError = await response.json();
        throw new Error(`Rate limited. Try again in ${Math.ceil(error.retry_after || 60)} seconds.`);
      }
      if (response.status === 401) {
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
      const error = await response.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `API error: ${response.status}`);
    }

    return response.json();
  },
};

// Threads
export interface ThreadMessage {
  id: number;
  content: string | null;
  timestamp: string;
  sender: Person | null;
  reply_to_message_id: number | null;
  depth: number;
}

export interface Thread {
  id: number;
  root_message_id: number;
  started_by: Person | null;
  started_at: string;
  message_count: number;
  last_message_at: string;
  preview: string | null;
  messages: ThreadMessage[] | null;
}

export interface ThreadListResponse {
  threads: Thread[];
  total: number;
  page: number;
  page_size: number;
}

export const threads = {
  list: (page?: number) =>
    fetchAPI<ThreadListResponse>("/threads", { params: { page } }),

  get: (id: number) => fetchAPI<Thread>(`/threads/${id}`),
};

// Stats
export interface ActivityDataPoint {
  date: string;
  count: number;
}

export interface Stats {
  total_messages: number;
  total_threads: number;
  total_people: number;
  activity: ActivityDataPoint[];
}

export const stats = {
  get: () => fetchAPI<Stats>("/stats"),
  recent: (limit?: number) =>
    fetchAPI<Message[]>("/stats/recent", { params: { limit } }),
};

// Settings
export interface SettingsStatus {
  bridge: {
    messenger_connected: boolean;
    last_synced: string | null;
    matrix_running: boolean;
  };
  archive: {
    messages_archived: number;
    database_size_mb: number;
    oldest_message: string | null;
  };
}

export const settings = {
  status: () => fetchAPI<SettingsStatus>("/settings/status"),
};

// Database (raw tables)
export interface TableResponse {
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const database = {
  messages: (page?: number, page_size?: number) =>
    fetchAPI<TableResponse>("/database/messages", { params: { page, page_size } }),

  people: (page?: number, page_size?: number) =>
    fetchAPI<TableResponse>("/database/people", { params: { page, page_size } }),

  rooms: (page?: number, page_size?: number) =>
    fetchAPI<TableResponse>("/database/rooms", { params: { page, page_size } }),
};

// Discussions (AI-detected)
export interface DiscussionMessage {
  id: number;
  content: string | null;
  timestamp: string;
  sender: Person | null;
  confidence: number;
}

export interface DiscussionBrief {
  id: number;
  title: string;
  summary: string | null;
  started_at: string;
  ended_at: string;
  message_count: number;
  participant_count: number;
}

export interface DiscussionFull extends DiscussionBrief {
  messages: DiscussionMessage[];
}

export interface DiscussionListResponse {
  discussions: DiscussionBrief[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AnalysisStatus {
  status: "none" | "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  windows_processed: number;
  total_windows: number;
  discussions_found: number;
  tokens_used: number;
  error_message: string | null;
}

export interface AnalyzeResponse {
  message: string;
  run_id: number;
}

export const discussions = {
  list: (params?: { page?: number; page_size?: number }) =>
    fetchAPI<DiscussionListResponse>("/discussions", { params }),

  get: (id: number) => fetchAPI<DiscussionFull>(`/discussions/${id}`),

  analyze: () =>
    fetchAPI<AnalyzeResponse>("/discussions/analyze", {
      method: "POST",
    }),

  analysisStatus: () => fetchAPI<AnalysisStatus>("/discussions/analysis-status"),
};
