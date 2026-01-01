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

// Rooms
export interface RoomListItem {
  id: number;
  name: string | null;
  avatar_url: string | null;
  description: string | null;
  message_count: number;
  member_count: number;
  last_message_at: string | null;
  display_order: number;
}

export interface RoomDetail extends RoomListItem {
  matrix_room_id: string;
  is_group: boolean;
  first_message_at: string | null;
  created_at: string;
}

export interface RoomListResponse {
  rooms: RoomListItem[];
}

export interface PersonRoomStats {
  room_id: number;
  room_name: string | null;
  avatar_url: string | null;
  message_count: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
}

export interface PersonRoomsResponse {
  person_id: number;
  rooms: PersonRoomStats[];
  total_rooms: number;
  total_messages: number;
}

export const rooms = {
  list: () => fetchAPI<RoomListResponse>("/rooms"),
  get: (id: number) => fetchAPI<RoomDetail>(`/rooms/${id}`),
  first: () => fetchAPI<RoomDetail>("/rooms/first"),
};

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
    room_id?: number;
  }) => fetchAPI<MessageListResponse>("/messages", { params }),

  get: (id: number) => fetchAPI<Message>(`/messages/${id}`),

  search: (q: string, page?: number, room_id?: number) =>
    fetchAPI<MessageListResponse>("/messages/search", {
      params: { q, page, room_id },
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

export interface PersonActivityDataPoint {
  date: string;
  count: number;
}

export interface PersonActivityResponse {
  person_id: number;
  period: string;
  granularity: string;
  data: PersonActivityDataPoint[];
  total_messages: number;
  most_active_day: string | null;
  most_active_hour: number | null;
}

// Convert mxc:// URL to HTTP URL
export function mxcToHttp(mxcUrl: string | null | undefined): string | null {
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
  list: (search?: string, room_id?: number) =>
    fetchAPI<PeopleListResponse>("/people", { params: { search, room_id } }),

  get: (id: number) => fetchAPI<PersonFull>(`/people/${id}`),

  update: (id: number, notes: string) =>
    fetchAPI<PersonFull>(`/people/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ notes }),
    }),

  messages: (id: number, page?: number, room_id?: number) =>
    fetchAPI<MessageListResponse>(`/people/${id}/messages`, {
      params: { page, room_id },
    }),

  rooms: (id: number) =>
    fetchAPI<PersonRoomsResponse>(`/people/${id}/rooms`),

  generateSummary: async (id: number): Promise<{ message: string; person_id: number; message_count: number }> => {
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
      if (response.status === 409) {
        throw new Error("Summary generation already in progress");
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

  summaryStatus: (id: number) =>
    fetchAPI<{
      status: "idle" | "running" | "completed" | "failed";
      started_at?: string;
      completed_at?: string;
      message_count?: number;
      error?: string;
      has_summary: boolean;
      summary_generated_at?: string;
    }>(`/people/${id}/generate-summary/status`),

  activity: (
    id: number,
    period: "all" | "year" | "6months" | "3months" | "month" = "6months",
    granularity: "day" | "week" | "month" = "week"
  ) =>
    fetchAPI<PersonActivityResponse>(`/people/${id}/activity`, {
      params: { period, granularity },
    }),
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
  list: (page?: number, room_id?: number) =>
    fetchAPI<ThreadListResponse>("/threads", { params: { page, room_id } }),

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
  get: (room_id?: number) => fetchAPI<Stats>("/stats", { params: { room_id } }),
  recent: (limit?: number, room_id?: number) =>
    fetchAPI<Message[]>("/stats/recent", { params: { limit, room_id } }),
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

  discussions: (page?: number, page_size?: number) =>
    fetchAPI<TableResponse>("/database/discussions", { params: { page, page_size } }),

  discussion_messages: (page?: number, page_size?: number) =>
    fetchAPI<TableResponse>("/database/discussion_messages", { params: { page, page_size } }),

  topics: (page?: number, page_size?: number) =>
    fetchAPI<TableResponse>("/database/topics", { params: { page, page_size } }),

  discussion_topics: (page?: number, page_size?: number) =>
    fetchAPI<TableResponse>("/database/discussion_topics", { params: { page, page_size } }),
};

// Discussions (AI-detected)
export interface DiscussionMessage {
  id: number;
  content: string | null;
  timestamp: string;
  sender: Person | null;
  confidence: number;
}

export interface TopicBrief {
  id: number;
  name: string;
  description: string | null;
  color: string;
  discussion_count: number;
}

export interface DiscussionBrief {
  id: number;
  title: string;
  summary: string | null;
  started_at: string;
  ended_at: string;
  message_count: number;
  participant_count: number;
  topics?: TopicBrief[];
}

export interface DiscussionFull extends DiscussionBrief {
  messages: DiscussionMessage[];
}

export interface ContextMessage {
  id: number;
  content: string | null;
  timestamp: string;
  sender: Person | null;
}

export interface DiscussionContextResponse {
  position: "before" | "after";
  messages: ContextMessage[];
  has_more: boolean;
}

export interface GapInfo {
  after_message_id: number;
  before_message_id: number;
  count: number;
}

export interface DiscussionGapsResponse {
  gaps: GapInfo[];
}

export interface GapMessagesResponse {
  messages: ContextMessage[];
}

export interface DiscussionListResponse {
  discussions: DiscussionBrief[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AnalysisStatus {
  status: "none" | "running" | "completed" | "failed" | "stale";
  started_at: string | null;
  completed_at: string | null;
  windows_processed: number;
  total_windows: number;
  discussions_found: number;
  tokens_used: number;
  error_message: string | null;
  // Incremental analysis fields
  mode: "full" | "incremental" | null;
  new_messages_count: number | null;
  context_messages_count: number | null;
}

export interface AnalysisPreview {
  incremental_available: boolean;
  reason?: string;
  new_messages: number;
  total_messages: number;
  context_messages?: number;
  last_analysis: {
    completed_at: string | null;
    discussions_found: number;
    end_message_id: number;
  } | null;
}

export interface AnalyzeResponse {
  message: string;
  run_id: number;
}

export interface TopicListResponse {
  topics: TopicBrief[];
}

export interface TopicClassificationStatus {
  status: "none" | "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  topics_created: number;
  discussions_classified: number;
  error_message: string | null;
}

export interface ClassifyTopicsResponse {
  message: string;
  run_id: number;
}

export interface TimelineEntry {
  date: string;
  count: number;
}

export interface TimelineResponse {
  timeline: TimelineEntry[];
  total: number;
}

// Semantic Search
export type SearchScope = "all" | "messages" | "discussions" | "people" | "topics";
export type MatchType = "hybrid" | "semantic";

export interface SearchMessageResult {
  id: number;
  content: string;
  sender_id: number | null;
  sender_name: string | null;
  sender_avatar: string | null;
  timestamp: string;
  score: number;
  match_type: MatchType;
}

export interface SearchDiscussionResult {
  id: number;
  title: string;
  summary: string | null;
  started_at: string;
  ended_at: string;
  message_count: number;
  score: number;
  match_type: MatchType;
}

export interface SearchPersonResult {
  id: number;
  display_name: string | null;
  avatar_url: string | null;
  ai_summary: string | null;
  score: number;
  match_type: MatchType;
}

export interface SearchTopicResult {
  id: number;
  name: string;
  description: string | null;
  color: string;
  score: number;
  match_type: MatchType;
}

export interface SearchPaginationInfo {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface SearchResults {
  query: string;
  results: {
    messages: SearchMessageResult[];
    discussions: SearchDiscussionResult[];
    people: SearchPersonResult[];
    topics: SearchTopicResult[];
  };
  counts: {
    messages: number;
    discussions: number;
    people: number;
    topics: number;
    total: number;
  };
  pagination: {
    messages: SearchPaginationInfo;
    discussions: SearchPaginationInfo;
    people: SearchPaginationInfo;
    topics: SearchPaginationInfo;
  };
}

export interface ReindexProgress {
  total: number;
  completed: number;
}

export interface ReindexStatus {
  status: "idle" | "running" | "completed" | "failed";
  progress: Record<string, ReindexProgress> | null;
  last_completed_at: string | null;
  error: string | null;
}

export const search = {
  query: (q: string, scope?: SearchScope, page?: number, pageSize?: number, roomId?: number) =>
    fetchAPI<SearchResults>("/search", {
      params: { q, scope, page, page_size: pageSize, room_id: roomId },
    }),

  reindex: (scope?: SearchScope) =>
    fetchAPI<{ message: string; scope: string }>("/search/reindex", {
      method: "POST",
      params: { scope },
    }),

  status: () => fetchAPI<ReindexStatus>("/search/status"),

  embed: (entityType: string, entityId: number) =>
    fetchAPI<{ message: string }>("/search/embed", {
      method: "POST",
      params: { entity_type: entityType, entity_id: entityId },
    }),
};

// Virtual Chat
export interface VirtualParticipant {
  person_id: number;
  display_name: string | null;
  avatar_url: string | null;
}

export interface VirtualMessage {
  id: number;
  conversation_id: number;
  sender_type: "user" | "agent";
  person_id: number | null;
  person_display_name: string | null;
  person_avatar_url: string | null;
  content: string;
  created_at: string;
}

export interface VirtualConversation {
  id: number;
  created_at: string;
  updated_at: string;
  participants: VirtualParticipant[];
}

export interface VirtualConversationWithMessages extends VirtualConversation {
  messages: VirtualMessage[];
}

// SSE Event Types
export type VirtualChatSSEEvent =
  | { type: "user_message"; id: number; content: string }
  | { type: "thinking"; person_id: number; display_name: string }
  | { type: "chunk"; person_id: number; text: string }
  | { type: "agent_done"; person_id: number; message_id: number | null }
  | { type: "complete" }
  | { type: "error"; message: string };

export const virtualChat = {
  createConversation: (participantIds: number[]) =>
    fetchAPI<VirtualConversation>("/virtual-chat/conversations", {
      method: "POST",
      body: JSON.stringify({ participant_ids: participantIds }),
    }),

  getConversation: (id: number) =>
    fetchAPI<VirtualConversationWithMessages>(`/virtual-chat/conversations/${id}`),

  addParticipant: (conversationId: number, personId: number) =>
    fetchAPI<VirtualParticipant>(
      `/virtual-chat/conversations/${conversationId}/participants`,
      {
        method: "POST",
        params: { person_id: personId },
      }
    ),

  // Returns the SSE URL for sending a message
  sendMessageUrl: (conversationId: number) =>
    `${API_URL}/api/virtual-chat/conversations/${conversationId}/message`,
};

export const discussions = {
  list: (params?: { page?: number; page_size?: number; topic_id?: number; date?: string; room_id?: number }) =>
    fetchAPI<DiscussionListResponse>("/discussions", { params }),

  get: (id: number) => fetchAPI<DiscussionFull>(`/discussions/${id}`),

  context: (id: number, position: "before" | "after", limit?: number) =>
    fetchAPI<DiscussionContextResponse>(`/discussions/${id}/context`, {
      params: { position, limit },
    }),

  gaps: (id: number) =>
    fetchAPI<DiscussionGapsResponse>(`/discussions/${id}/gaps`),

  gapMessages: (id: number, afterMessageId: number, beforeMessageId: number) =>
    fetchAPI<GapMessagesResponse>(`/discussions/${id}/gap-messages`, {
      params: { after_message_id: afterMessageId, before_message_id: beforeMessageId },
    }),

  timeline: (params?: { topic_id?: number; room_id?: number }) =>
    fetchAPI<TimelineResponse>("/discussions/timeline", { params }),

  analyze: (mode: "incremental" | "full" = "incremental") =>
    fetchAPI<AnalyzeResponse>("/discussions/analyze", {
      method: "POST",
      params: { mode },
    }),

  analysisPreview: () => fetchAPI<AnalysisPreview>("/discussions/analyze/preview"),

  analysisStatus: () => fetchAPI<AnalysisStatus>("/discussions/analysis-status"),

  // Topics
  listTopics: () => fetchAPI<TopicListResponse>("/discussions/topics/list"),

  classifyTopics: () =>
    fetchAPI<ClassifyTopicsResponse>("/discussions/classify-topics", {
      method: "POST",
    }),

  topicClassificationStatus: () =>
    fetchAPI<TopicClassificationStatus>("/discussions/classify-topics/status"),
};
