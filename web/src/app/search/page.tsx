"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import {
  search,
  mxcToHttp,
  type SearchResults,
  type SearchScope,
  type SearchPaginationInfo,
  type SearchMessageResult,
  type SearchDiscussionResult,
  type SearchPersonResult,
  type SearchTopicResult,
} from "@/lib/api";
import { formatRelativeTime, formatDateTime } from "@/lib/utils";
import {
  Search,
  MessageSquare,
  MessagesSquare,
  User,
  Tag,
  Sparkles,
  Zap,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useRoom } from "@/contexts/room-context";

const SCOPES: { value: SearchScope; label: string; icon: React.ReactNode }[] = [
  { value: "all", label: "All", icon: <Search className="h-4 w-4" /> },
  { value: "messages", label: "Messages", icon: <MessageSquare className="h-4 w-4" /> },
  { value: "discussions", label: "Discussions", icon: <MessagesSquare className="h-4 w-4" /> },
  { value: "people", label: "People", icon: <User className="h-4 w-4" /> },
  { value: "topics", label: "Topics", icon: <Tag className="h-4 w-4" /> },
];

function ScoreBar({ score }: { score: number }) {
  const percentage = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-primary/70 rounded-full"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground">{percentage}%</span>
    </div>
  );
}

function MatchTypeBadge({ type }: { type: "hybrid" | "semantic" }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs ${
        type === "hybrid"
          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
          : "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400"
      }`}
    >
      {type === "hybrid" ? (
        <Zap className="h-3 w-3" />
      ) : (
        <Sparkles className="h-3 w-3" />
      )}
      {type === "hybrid" ? "Hybrid" : "Semantic"}
    </span>
  );
}

function MessageResultCard({
  result,
  query,
}: {
  result: SearchMessageResult;
  query: string;
}) {
  const avatarUrl = result.sender_avatar ? mxcToHttp(result.sender_avatar) : null;

  const highlightMatch = (content: string, query: string) => {
    if (!query) return content;
    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, "gi");
    const parts = content.split(regex);
    return parts.map((part, i) =>
      regex.test(part) ? (
        <mark key={i} className="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">
          {part}
        </mark>
      ) : (
        part
      )
    );
  };

  return (
    <div className="p-4 hover:bg-muted/50 transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt=""
              className="h-8 w-8 rounded-full object-cover"
            />
          ) : (
            <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
              {result.sender_name?.[0] || "?"}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium">
              {result.sender_name || "Unknown"}
            </span>
            <span className="text-xs text-muted-foreground">
              {formatRelativeTime(result.timestamp)}
            </span>
            <MatchTypeBadge type={result.match_type} />
          </div>
          <p className="text-sm text-foreground/90 line-clamp-3">
            {highlightMatch(result.content, query)}
          </p>
        </div>
        <div className="flex-shrink-0">
          <ScoreBar score={result.score} />
        </div>
      </div>
    </div>
  );
}

function DiscussionResultCard({ result }: { result: SearchDiscussionResult }) {
  return (
    <Link
      href={`/discussions/${result.id}`}
      className="block p-4 hover:bg-muted/50 transition-colors"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <MessagesSquare className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">{result.title}</span>
            <MatchTypeBadge type={result.match_type} />
          </div>
          {result.summary && (
            <p className="text-sm text-muted-foreground line-clamp-2 mb-2">
              {result.summary}
            </p>
          )}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>{result.message_count} messages</span>
            <span>{formatDateTime(result.started_at).split(",")[0]}</span>
          </div>
        </div>
        <div className="flex-shrink-0">
          <ScoreBar score={result.score} />
        </div>
      </div>
    </Link>
  );
}

function PersonResultCard({ result }: { result: SearchPersonResult }) {
  const avatarUrl = result.avatar_url ? mxcToHttp(result.avatar_url) : null;

  return (
    <Link
      href={`/people/${result.id}`}
      className="block p-4 hover:bg-muted/50 transition-colors"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt=""
              className="h-10 w-10 rounded-full object-cover"
            />
          ) : (
            <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium">
              {result.display_name?.[0] || "?"}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium">
              {result.display_name || "Unknown"}
            </span>
            <MatchTypeBadge type={result.match_type} />
          </div>
          {result.ai_summary && (
            <p className="text-sm text-muted-foreground line-clamp-2">
              {result.ai_summary}
            </p>
          )}
        </div>
        <div className="flex-shrink-0">
          <ScoreBar score={result.score} />
        </div>
      </div>
    </Link>
  );
}

function TopicResultCard({ result }: { result: SearchTopicResult }) {
  return (
    <Link
      href={`/discussions?topic_id=${result.id}`}
      className="block p-4 hover:bg-muted/50 transition-colors"
    >
      <div className="flex items-start gap-3">
        <div
          className="flex-shrink-0 h-8 w-8 rounded-lg flex items-center justify-center"
          style={{ backgroundColor: result.color + "20" }}
        >
          <Tag className="h-4 w-4" style={{ color: result.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="inline-block px-2 py-0.5 rounded-full text-sm font-medium"
              style={{
                backgroundColor: result.color + "20",
                color: result.color,
              }}
            >
              {result.name}
            </span>
            <MatchTypeBadge type={result.match_type} />
          </div>
          {result.description && (
            <p className="text-sm text-muted-foreground line-clamp-2">
              {result.description}
            </p>
          )}
        </div>
        <div className="flex-shrink-0">
          <ScoreBar score={result.score} />
        </div>
      </div>
    </Link>
  );
}

function Pagination({
  pagination,
  onPageChange,
}: {
  pagination: SearchPaginationInfo;
  onPageChange: (page: number) => void;
}) {
  if (pagination.total_pages <= 1) return null;

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t bg-muted/20">
      <span className="text-sm text-muted-foreground">
        Page {pagination.page} of {pagination.total_pages} ({pagination.total} results)
      </span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(pagination.page - 1)}
          disabled={!pagination.has_prev}
          className="p-1.5 rounded hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <button
          onClick={() => onPageChange(pagination.page + 1)}
          disabled={!pagination.has_next}
          className="p-1.5 rounded hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function ResultSection({
  title,
  icon,
  count,
  pagination,
  onPageChange,
  defaultExpanded = false,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  count: number;
  pagination?: SearchPaginationInfo;
  onPageChange?: (page: number) => void;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (count === 0) return null;

  return (
    <div className="rounded-xl border bg-card overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 px-4 py-3 w-full text-left bg-muted/30 hover:bg-muted/50 transition-colors"
      >
        {icon}
        <span className="font-medium">{title}</span>
        <span className="text-sm text-muted-foreground">({count})</span>
        <span className="ml-auto">
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </span>
      </button>
      {isExpanded && (
        <>
          <div className="divide-y border-t">{children}</div>
          {pagination && onPageChange && (
            <Pagination pagination={pagination} onPageChange={onPageChange} />
          )}
        </>
      )}
    </div>
  );
}

function SearchContent() {
  const searchParams = useSearchParams();
  const queryParam = searchParams.get("q") || "";
  const { currentRoom } = useRoom();

  const [searchQuery, setSearchQuery] = useState(queryParam);
  const [scope, setScope] = useState<SearchScope>("all");
  const [page, setPage] = useState(1);
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (queryParam) {
      setSearchQuery(queryParam);
      setPage(1);
      performSearch(queryParam, scope, 1, currentRoom?.id);
    }
  }, [queryParam, currentRoom?.id]);

  const performSearch = async (q: string, s: SearchScope, p: number, roomId?: number) => {
    if (!q.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const result = await search.query(q, s, p, 20, roomId);
      setResults(result);
    } catch (err) {
      console.error("Search failed:", err);
      setError("Search failed. Make sure the search index has been built in Settings.");
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    performSearch(searchQuery, scope, 1, currentRoom?.id);
    // Update URL
    const url = new URL(window.location.href);
    url.searchParams.set("q", searchQuery);
    window.history.pushState({}, "", url);
  };

  const handleScopeChange = (newScope: SearchScope) => {
    setScope(newScope);
    setPage(1);
    if (searchQuery) {
      performSearch(searchQuery, newScope, 1, currentRoom?.id);
    }
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    performSearch(searchQuery, scope, newPage, currentRoom?.id);
    // Scroll to top of results
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Search</h1>

        {/* Search input */}
        <form onSubmit={handleSubmit}>
          <div className="flex items-center gap-2 rounded-lg border bg-background px-4 py-3">
            <Search className="h-5 w-5 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search with AI-powered semantic understanding..."
              className="flex-1 bg-transparent outline-none"
            />
            <button
              type="submit"
              className="px-4 py-1.5 bg-primary text-primary-foreground rounded-md text-sm"
            >
              Search
            </button>
          </div>
        </form>

        {/* Scope tabs */}
        <div className="flex gap-1 p-1 rounded-lg bg-muted/50 w-fit">
          {SCOPES.map((s) => (
            <button
              key={s.value}
              onClick={() => handleScopeChange(s.value)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                scope === s.value
                  ? "bg-background shadow-sm font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s.icon}
              {s.label}
              {results && scope === "all" && s.value !== "all" && (
                <span className="text-xs text-muted-foreground">
                  {results.counts[s.value as keyof typeof results.counts]}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Results */}
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-flex items-center gap-2 text-muted-foreground">
              <Sparkles className="h-5 w-5 animate-pulse" />
              <span>Searching semantically...</span>
            </div>
          </div>
        ) : error ? (
          <div className="text-center py-12">
            <p className="text-red-500 mb-2">{error}</p>
            <Link
              href="/settings"
              className="text-primary hover:underline text-sm"
            >
              Go to Settings to build search index
            </Link>
          </div>
        ) : results && results.counts.total > 0 ? (
          <div className="space-y-6">
            <p className="text-sm text-muted-foreground">
              Found {results.counts.total} results for "{results.query}"
            </p>

            {/* Messages */}
            {(scope === "all" || scope === "messages") && (
              <ResultSection
                title="Messages"
                icon={<MessageSquare className="h-4 w-4 text-muted-foreground" />}
                count={results.counts.messages}
                pagination={scope === "messages" ? results.pagination.messages : undefined}
                onPageChange={scope === "messages" ? handlePageChange : undefined}
                defaultExpanded={scope !== "all" || results.counts.messages > 0}
              >
                {results.results.messages.map((msg) => (
                  <MessageResultCard
                    key={msg.id}
                    result={msg}
                    query={results.query}
                  />
                ))}
              </ResultSection>
            )}

            {/* Discussions */}
            {(scope === "all" || scope === "discussions") && (
              <ResultSection
                title="Discussions"
                icon={<MessagesSquare className="h-4 w-4 text-muted-foreground" />}
                count={results.counts.discussions}
                pagination={scope === "discussions" ? results.pagination.discussions : undefined}
                onPageChange={scope === "discussions" ? handlePageChange : undefined}
                defaultExpanded={scope !== "all" || (results.counts.messages === 0 && results.counts.discussions > 0)}
              >
                {results.results.discussions.map((disc) => (
                  <DiscussionResultCard key={disc.id} result={disc} />
                ))}
              </ResultSection>
            )}

            {/* People */}
            {(scope === "all" || scope === "people") && (
              <ResultSection
                title="People"
                icon={<User className="h-4 w-4 text-muted-foreground" />}
                count={results.counts.people}
                pagination={scope === "people" ? results.pagination.people : undefined}
                onPageChange={scope === "people" ? handlePageChange : undefined}
                defaultExpanded={scope !== "all" || (results.counts.messages === 0 && results.counts.discussions === 0 && results.counts.people > 0)}
              >
                {results.results.people.map((person) => (
                  <PersonResultCard key={person.id} result={person} />
                ))}
              </ResultSection>
            )}

            {/* Topics */}
            {(scope === "all" || scope === "topics") && (
              <ResultSection
                title="Topics"
                icon={<Tag className="h-4 w-4 text-muted-foreground" />}
                count={results.counts.topics}
                pagination={scope === "topics" ? results.pagination.topics : undefined}
                onPageChange={scope === "topics" ? handlePageChange : undefined}
                defaultExpanded={scope !== "all" || (results.counts.messages === 0 && results.counts.discussions === 0 && results.counts.people === 0 && results.counts.topics > 0)}
              >
                {results.results.topics.map((topic) => (
                  <TopicResultCard key={topic.id} result={topic} />
                ))}
              </ResultSection>
            )}
          </div>
        ) : results ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground">
              No results found for "{results.query}"
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              Try different keywords or a broader search scope
            </p>
          </div>
        ) : (
          <div className="text-center py-12 text-muted-foreground">
            <Sparkles className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Enter a search query to find messages, discussions, people, and topics</p>
            <p className="text-sm mt-2">
              Semantic search understands meaning, not just keywords
            </p>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <AppLayout>
          <div className="flex items-center justify-center h-full">
            <p className="text-muted-foreground">Loading...</p>
          </div>
        </AppLayout>
      }
    >
      <SearchContent />
    </Suspense>
  );
}
