"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AppLayout } from "@/components/layout/app-layout";
import { messages, type Message } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { Search } from "lucide-react";

function SearchContent() {
  const searchParams = useSearchParams();
  const query = searchParams.get("q") || "";

  const [searchQuery, setSearchQuery] = useState(query);
  const [results, setResults] = useState<Message[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (query) {
      setSearchQuery(query);
      performSearch(query);
    }
  }, [query]);

  const performSearch = async (q: string) => {
    if (!q.trim()) return;

    setLoading(true);
    try {
      const result = await messages.search(q);
      setResults(result.messages);
      setTotal(result.total);
    } catch (error) {
      console.error("Search failed:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performSearch(searchQuery);
    // Update URL
    const url = new URL(window.location.href);
    url.searchParams.set("q", searchQuery);
    window.history.pushState({}, "", url);
  };

  const highlightMatch = (content: string, query: string) => {
    if (!query) return content;
    const regex = new RegExp(`(${query})`, "gi");
    const parts = content.split(regex);
    return parts.map((part, i) =>
      regex.test(part) ? (
        <mark key={i} className="bg-yellow-200 dark:bg-yellow-800">
          {part}
        </mark>
      ) : (
        part
      )
    );
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
              placeholder="Search messages..."
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

        {/* Results */}
        {loading ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground">Searching...</p>
          </div>
        ) : results.length > 0 ? (
          <>
            <p className="text-sm text-muted-foreground">
              Found {total} results for "{query}"
            </p>
            <div className="rounded-xl border bg-card divide-y">
              {results.map((msg) => (
                <div key={msg.id} className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="h-6 w-6 rounded-full bg-muted flex items-center justify-center text-xs font-medium">
                      {msg.sender?.display_name?.[0] || "?"}
                    </div>
                    <span className="text-sm font-medium">
                      {msg.sender?.display_name || "Unknown"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatRelativeTime(msg.timestamp)}
                    </span>
                  </div>
                  <p className="text-sm">
                    {highlightMatch(msg.content || "", query)}
                  </p>
                </div>
              ))}
            </div>
          </>
        ) : query ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground">
              No results found for "{query}"
            </p>
          </div>
        ) : null}
      </div>
    </AppLayout>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </AppLayout>
    }>
      <SearchContent />
    </Suspense>
  );
}
