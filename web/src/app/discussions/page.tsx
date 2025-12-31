"use client";

import { useEffect, useState, useCallback, useMemo, useRef, useDeferredValue } from "react";
import Link from "next/link";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AppLayout } from "@/components/layout/app-layout";
import {
  discussions,
  search,
  type DiscussionBrief,
  type AnalysisStatus,
  type AnalysisPreview,
  type TopicBrief,
  type TopicClassificationStatus,
  type TimelineEntry,
  type SearchDiscussionResult,
} from "@/lib/api";
import { formatRelativeTime, truncate } from "@/lib/utils";
import { Sparkles, Play, Loader2, AlertCircle, Users, MessageSquare, Tag, Search, X, RefreshCw, ChevronDown } from "lucide-react";

function TopicPill({ topic, selected, onClick }: { topic: TopicBrief | null; selected: boolean; onClick: () => void }) {
  const isAll = topic === null;
  
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
        selected
          ? "bg-primary text-primary-foreground"
          : "bg-muted hover:bg-muted/80 text-foreground"
      }`}
      title={topic?.description || undefined}
    >
      {!isAll && (
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: topic.color }}
        />
      )}
      {isAll ? "All" : topic.name}
    </button>
  );
}

function DiscussionTopicPills({ topics }: { topics?: TopicBrief[] }) {
  if (!topics || topics.length === 0) return null;
  
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {topics.map((topic) => (
        <span
          key={topic.id}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-muted"
          title={topic.description || undefined}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: topic.color }}
          />
          {topic.name}
        </span>
      ))}
    </div>
  );
}

export default function DiscussionsPage() {
  const [data, setData] = useState<DiscussionBrief[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus | null>(null);
  const [startingAnalysis, setStartingAnalysis] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  
  // Topics state
  const [topics, setTopics] = useState<TopicBrief[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);
  const [topicClassificationStatus, setTopicClassificationStatus] = useState<TopicClassificationStatus | null>(null);
  const [startingClassification, setStartingClassification] = useState(false);
  
  // Timeline state (fetched separately for full view)
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  
  // Analysis preview state
  const [analysisPreview, setAnalysisPreview] = useState<AnalysisPreview | null>(null);
  const [showAnalysisMenu, setShowAnalysisMenu] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchDiscussionResult[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const deferredSearchQuery = useDeferredValue(searchQuery);

  // Virtualization
  const parentRef = useRef<HTMLDivElement>(null);
  const analysisMenuRef = useRef<HTMLDivElement>(null);
  
  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (analysisMenuRef.current && !analysisMenuRef.current.contains(event.target as Node)) {
        setShowAnalysisMenu(false);
      }
    };
    
    if (showAnalysisMenu) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showAnalysisMenu]);

  const loadDiscussions = useCallback(async (topicId?: number | null, date?: string | null, page: number = 1, append: boolean = false) => {
    try {
      const params: { topic_id?: number; date?: string; page?: number; page_size?: number } = {
        page,
        page_size: 50,
      };
      if (topicId !== null && topicId !== undefined) {
        params.topic_id = topicId;
      }
      if (date !== null && date !== undefined) {
        params.date = date;
      }
      const result = await discussions.list(params);
      
      if (append) {
        setData(prev => [...prev, ...result.discussions]);
      } else {
        setData(result.discussions);
      }
      setCurrentPage(page);
      setHasMore(page < result.total_pages);
    } catch (err) {
      console.error("Failed to load discussions:", err);
    }
  }, []);

  const loadTopics = useCallback(async () => {
    try {
      const result = await discussions.listTopics();
      setTopics(result.topics);
    } catch (err) {
      console.error("Failed to load topics:", err);
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const status = await discussions.analysisStatus();
      setAnalysisStatus(status);
      return status;
    } catch (err) {
      console.error("Failed to load analysis status:", err);
      return null;
    }
  }, []);

  const loadTopicClassificationStatus = useCallback(async () => {
    try {
      const status = await discussions.topicClassificationStatus();
      setTopicClassificationStatus(status);
      return status;
    } catch (err) {
      console.error("Failed to load topic classification status:", err);
      return null;
    }
  }, []);

  const loadAnalysisPreview = useCallback(async () => {
    try {
      const preview = await discussions.analysisPreview();
      setAnalysisPreview(preview);
      return preview;
    } catch (err) {
      console.error("Failed to load analysis preview:", err);
      return null;
    }
  }, []);

  const loadTimeline = useCallback(async (topicId?: number | null) => {
    try {
      const params: { topic_id?: number } = {};
      if (topicId !== null && topicId !== undefined) {
        params.topic_id = topicId;
      }
      const result = await discussions.timeline(params);
      setTimeline(result.timeline);
      setTotal(result.total);
    } catch (err) {
      console.error("Failed to load timeline:", err);
    }
  }, []);

  useEffect(() => {
    async function load() {
      await Promise.all([
        loadDiscussions(),
        loadTimeline(),
        loadStatus(),
        loadTopics(),
        loadTopicClassificationStatus(),
        loadAnalysisPreview()
      ]);
      setLoading(false);
    }
    load();
  }, [loadDiscussions, loadTimeline, loadStatus, loadTopics, loadTopicClassificationStatus, loadAnalysisPreview]);

  // Reload discussions when topic or date filter changes
  useEffect(() => {
    if (!loading && !searchQuery) {
      loadDiscussions(selectedTopicId, selectedDate);
    }
  }, [selectedTopicId, selectedDate, loadDiscussions, loading, searchQuery]);

  // Search effect with debounce via useDeferredValue
  useEffect(() => {
    if (!deferredSearchQuery.trim()) {
      setSearchResults(null);
      setIsSearching(false);
      return;
    }

    const performSearch = async () => {
      setIsSearching(true);
      try {
        const result = await search.query(deferredSearchQuery, "discussions", 1, 50);
        // Filter by topic if selected
        let filtered = result.results.discussions;
        if (selectedTopicId !== null) {
          // We need to fetch full discussion data to filter by topic
          // For now, just show all search results when searching
          // The user can clear the topic filter if needed
        }
        setSearchResults(filtered);
      } catch (err) {
        console.error("Search failed:", err);
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    };

    performSearch();
  }, [deferredSearchQuery, selectedTopicId]);

  // Reload timeline when topic filter changes (not date - timeline shows all dates)
  useEffect(() => {
    if (!loading) {
      loadTimeline(selectedTopicId);
    }
  }, [selectedTopicId, loadTimeline, loading]);

  // Poll for status and discussions while analysis is running
  useEffect(() => {
    if (analysisStatus?.status !== "running") return;

    const interval = setInterval(async () => {
      const status = await loadStatus();
      await Promise.all([
        loadDiscussions(selectedTopicId, selectedDate),
        loadTimeline(selectedTopicId),
      ]);
      // Reload preview when analysis completes
      if (status?.status === "completed") {
        loadAnalysisPreview();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [analysisStatus?.status, loadStatus, loadDiscussions, loadTimeline, selectedTopicId, selectedDate, loadAnalysisPreview]);

  // Poll for topic classification status
  useEffect(() => {
    if (topicClassificationStatus?.status !== "running") return;

    const interval = setInterval(async () => {
      const status = await loadTopicClassificationStatus();
      if (status?.status === "completed") {
        await Promise.all([loadTopics(), loadDiscussions(selectedTopicId, selectedDate), loadTimeline(selectedTopicId)]);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [topicClassificationStatus?.status, loadTopicClassificationStatus, loadTopics, loadDiscussions, loadTimeline, selectedTopicId, selectedDate]);

  const handleStartAnalysis = async (mode: "incremental" | "full" = "incremental") => {
    setStartingAnalysis(true);
    setError(null);
    setShowAnalysisMenu(false);
    try {
      await discussions.analyze(mode);
      await loadStatus();
    } catch (err) {
      console.error("Failed to start analysis:", err);
      setError(err instanceof Error ? err.message : "Failed to start analysis");
    } finally {
      setStartingAnalysis(false);
    }
  };

  const handleStartClassification = async () => {
    setStartingClassification(true);
    setError(null);
    try {
      await discussions.classifyTopics();
      await loadTopicClassificationStatus();
    } catch (err) {
      console.error("Failed to start topic classification:", err);
      setError(err instanceof Error ? err.message : "Failed to start classification");
    } finally {
      setStartingClassification(false);
    }
  };

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      await loadDiscussions(selectedTopicId, selectedDate, currentPage + 1, true);
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, hasMore, loadDiscussions, selectedTopicId, selectedDate, currentPage]);

  // Virtualizer for discussions list
  const rowVirtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 120, // Estimated height of each discussion card
    overscan: 5,
  });

  // Load more when scrolling near the bottom
  const virtualItems = rowVirtualizer.getVirtualItems();
  const lastItem = virtualItems[virtualItems.length - 1];
  
  useEffect(() => {
    if (!lastItem) return;
    
    // If we're within 5 items of the end and have more data, load more
    if (lastItem.index >= data.length - 5 && hasMore && !loadingMore) {
      loadMore();
    }
  }, [lastItem?.index, data.length, hasMore, loadingMore, loadMore]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </AppLayout>
    );
  }

  const isRunning = analysisStatus?.status === "running";
  const isStale = analysisStatus?.status === "stale";
  const isClassifying = topicClassificationStatus?.status === "running";
  const progress = analysisStatus?.total_windows
    ? Math.round((analysisStatus.windows_processed / analysisStatus.total_windows) * 100)
    : 0;

  return (
    <AppLayout>
      <div className="flex flex-col h-full gap-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <Sparkles className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Discussions</h1>
          </div>
          <div className="flex items-center gap-2">
            {/* Analysis button with dropdown for full re-analysis */}
            <div className="relative" ref={analysisMenuRef}>
              <div className="flex">
                <button
                  onClick={() => handleStartAnalysis(analysisPreview?.incremental_available ? "incremental" : "full")}
                  disabled={startingAnalysis || isRunning || (analysisPreview?.incremental_available && analysisPreview.new_messages === 0)}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-l-lg font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {startingAnalysis || isRunning ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {isRunning 
                    ? `Analyzing${analysisStatus?.mode === "incremental" ? " (incremental)" : ""}...` 
                    : analysisPreview?.incremental_available 
                      ? analysisPreview.new_messages > 0 
                        ? `Analyze (${analysisPreview.new_messages} new)`
                        : "Up to date"
                      : "Analyze All"
                  }
                </button>
                <button
                  onClick={() => setShowAnalysisMenu(!showAnalysisMenu)}
                  disabled={startingAnalysis || isRunning}
                  className="inline-flex items-center px-2 py-2 bg-primary text-primary-foreground rounded-r-lg font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed border-l border-primary-foreground/20"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
              </div>
              
              {/* Dropdown menu */}
              {showAnalysisMenu && (
                <div className="absolute right-0 mt-1 w-56 bg-card border rounded-lg shadow-lg z-50">
                  <div className="p-1">
                    {analysisPreview?.incremental_available && analysisPreview.new_messages > 0 && (
                      <button
                        onClick={() => handleStartAnalysis("incremental")}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-muted rounded-md flex items-center gap-2"
                      >
                        <Play className="h-4 w-4" />
                        <div>
                          <div className="font-medium">Incremental</div>
                          <div className="text-xs text-muted-foreground">
                            {analysisPreview.new_messages} new messages + {analysisPreview.context_messages} context
                          </div>
                        </div>
                      </button>
                    )}
                    <button
                      onClick={() => handleStartAnalysis("full")}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-muted rounded-md flex items-center gap-2"
                    >
                      <RefreshCw className="h-4 w-4" />
                      <div>
                        <div className="font-medium">Full Re-analysis</div>
                        <div className="text-xs text-muted-foreground">
                          Re-analyze all {analysisPreview?.total_messages.toLocaleString()} messages
                        </div>
                      </div>
                    </button>
                  </div>
                </div>
              )}
            </div>
            
            <button
              onClick={handleStartClassification}
              disabled={startingClassification || isClassifying || data.length === 0}
              className="inline-flex items-center gap-2 px-4 py-2 border rounded-lg font-medium hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {startingClassification || isClassifying ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Tag className="h-4 w-4" />
              )}
              {isClassifying ? "Classifying..." : "Classify Topics"}
            </button>
          </div>
        </div>

        {/* Progress bars */}
        {isRunning && (
          <div className="space-y-1 flex-shrink-0">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {analysisStatus.mode === "incremental" 
                  ? `Incremental: ${analysisStatus.windows_processed} / ${analysisStatus.total_windows} windows`
                  : `Analysis: ${analysisStatus.windows_processed} / ${analysisStatus.total_windows} windows`
                }
                {analysisStatus.mode === "incremental" && analysisStatus.new_messages_count !== null && (
                  <span className="ml-2 text-muted-foreground/70">
                    ({analysisStatus.new_messages_count} new + {analysisStatus.context_messages_count} context)
                  </span>
                )}
              </span>
              <span>{analysisStatus.discussions_found} discussions</span>
            </div>
            <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  analysisStatus.mode === "incremental" ? "bg-blue-600" : "bg-green-700"
                }`}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {isClassifying && (
          <div className="space-y-1 flex-shrink-0">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Classifying topics...</span>
            </div>
            <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-violet-600 rounded-full animate-pulse w-full" />
            </div>
          </div>
        )}

        {/* Topic filter bar */}
        {topics.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-2 -mx-2 px-2 flex-shrink-0">
            <TopicPill
              topic={null}
              selected={selectedTopicId === null}
              onClick={() => setSelectedTopicId(null)}
            />
            {topics.map((topic) => (
              <TopicPill
                key={topic.id}
                topic={topic}
                selected={selectedTopicId === topic.id}
                onClick={() => setSelectedTopicId(topic.id)}
              />
            ))}
          </div>
        )}

        <p className="text-muted-foreground flex-shrink-0">
          AI-detected thematic discussions extracted from the chat history.
        </p>

        {/* Error message */}
        {error && (
          <div className="flex items-center gap-2 p-4 rounded-lg border border-red-500/50 bg-red-500/10 text-red-500">
            <AlertCircle className="h-5 w-5" />
            <p className="text-sm">{error}</p>
          </div>
        )}

        {/* Analysis status */}
        {analysisStatus?.status === "failed" && (
          <div className="flex items-center gap-2 p-4 rounded-lg border border-red-500/50 bg-red-500/10 text-red-500">
            <AlertCircle className="h-5 w-5" />
            <p className="text-sm">
              Analysis failed: {analysisStatus.error_message || "Unknown error"}
            </p>
          </div>
        )}

        {isStale && (
          <div className="flex items-center justify-between gap-2 p-4 rounded-lg border border-yellow-500/50 bg-yellow-500/10 text-yellow-600">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              <p className="text-sm">
                {analysisStatus?.error_message || "Previous analysis was interrupted. Click 'Analyze' to restart."}
              </p>
            </div>
          </div>
        )}

        {analysisStatus?.status === "completed" && analysisStatus.completed_at && !isRunning && (
          <div className="rounded-lg border p-3 bg-muted/50">
            <p className="text-sm text-muted-foreground">
              Last analysis ({analysisStatus.mode || "full"}): {formatRelativeTime(analysisStatus.completed_at)} - 
              Found {analysisStatus.discussions_found} discussions using {analysisStatus.tokens_used.toLocaleString()} tokens
              {analysisStatus.mode === "incremental" && analysisStatus.new_messages_count !== null && (
                <span> ({analysisStatus.new_messages_count} new messages processed)</span>
              )}
            </p>
          </div>
        )}

        {/* Search bar */}
        <div className="flex-shrink-0">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search discussions or participants..."
              className="w-full pl-10 pr-10 py-2 rounded-lg border bg-background text-sm outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
            {isSearching && (
              <div className="absolute right-10 top-1/2 -translate-y-1/2">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            )}
          </div>
          {searchResults !== null && (
            <p className="text-xs text-muted-foreground mt-1">
              {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} for "{deferredSearchQuery}"
            </p>
          )}
        </div>

        {/* Main content with timeline */}
        <div className="flex gap-6 flex-1 min-h-0">
          {/* Timeline sidebar */}
          {timeline.length > 0 && (
            <div className="w-48 flex-shrink-0 overflow-y-auto relative">
              <div className="sticky top-0 bg-background z-20 pb-3">
                <h3 className="text-sm font-medium text-muted-foreground">Timeline</h3>
              </div>
              <div className="relative">
                {/* Vertical line */}
                <div className="absolute left-[7px] top-0 bottom-2 w-0.5 bg-border" />
                
                {/* All dates option */}
                <button
                  onClick={() => setSelectedDate(null)}
                  className={`relative flex items-center gap-3 w-full text-left py-2 group ${
                    selectedDate === null ? "text-primary" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <div
                    className={`w-4 h-4 rounded-full border-2 flex-shrink-0 z-10 transition-colors ${
                      selectedDate === null
                        ? "bg-primary border-primary"
                        : "bg-background border-muted-foreground/30 group-hover:border-muted-foreground"
                    }`}
                  />
                  <span className="text-sm font-medium">All dates</span>
                  <span className="text-xs text-muted-foreground ml-auto">{total}</span>
                </button>

                {timeline.map(({ date, count }) => {
                  const dateObj = new Date(date + "T00:00:00");
                  return (
                    <button
                      key={date}
                      onClick={() => setSelectedDate(date)}
                      className={`relative flex items-center gap-3 w-full text-left py-2 group ${
                        selectedDate === date ? "text-primary" : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {/* Bead */}
                      <div
                        className={`w-4 h-4 rounded-full border-2 flex-shrink-0 z-10 transition-colors ${
                          selectedDate === date
                            ? "bg-primary border-primary"
                            : "bg-background border-muted-foreground/30 group-hover:border-muted-foreground"
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm">
                          {dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                        </span>
                        <span className="text-xs text-muted-foreground ml-2">{count}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Discussions list - virtualized for browsing, simple list for search */}
          <div 
            ref={parentRef}
            className="flex-1 overflow-auto"
          >
            {searchResults !== null ? (
              // Search results mode
              searchResults.length > 0 ? (
                <div className="space-y-4">
                  {searchResults.map((result) => (
                    <Link
                      key={result.id}
                      href={`/discussions/${result.id}`}
                      className="block rounded-xl border bg-card p-4 hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium">{result.title}</h3>
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              result.match_type === "hybrid" 
                                ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                : "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400"
                            }`}>
                              {Math.round(result.score * 100)}%
                            </span>
                          </div>
                          <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <MessageSquare className="h-3.5 w-3.5" />
                              {result.message_count} messages
                            </span>
                            <span>
                              {formatRelativeTime(result.started_at)}
                            </span>
                          </div>
                          {result.summary && (
                            <p className="mt-2 text-sm text-muted-foreground">
                              {truncate(result.summary, 200)}
                            </p>
                          )}
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <Search className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">
                    No discussions found for "{deferredSearchQuery}"
                  </p>
                </div>
              )
            ) : data.length > 0 ? (
              // Regular browsing mode with virtualization
              <div
                style={{
                  height: `${rowVirtualizer.getTotalSize()}px`,
                  width: "100%",
                  position: "relative",
                }}
              >
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const discussion = data[virtualRow.index];
                  return (
                    <div
                      key={discussion.id}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                    >
                      <Link
                        href={`/discussions/${discussion.id}`}
                        className="block rounded-xl border bg-card p-4 hover:bg-muted/50 transition-colors mb-4"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <h3 className="font-medium">{discussion.title}</h3>
                            <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                              <span className="flex items-center gap-1">
                                <MessageSquare className="h-3.5 w-3.5" />
                                {discussion.message_count} messages
                              </span>
                              <span className="flex items-center gap-1">
                                <Users className="h-3.5 w-3.5" />
                                {discussion.participant_count} participants
                              </span>
                              <span>
                                {formatRelativeTime(discussion.started_at)}
                              </span>
                            </div>
                            <DiscussionTopicPills topics={discussion.topics} />
                            {discussion.summary && (
                              <p className="mt-2 text-sm text-muted-foreground">
                                {truncate(discussion.summary, 200)}
                              </p>
                            )}
                          </div>
                        </div>
                      </Link>
                    </div>
                  );
                })}
              </div>
            ) : (
              !isRunning && (
                <div className="text-center py-12">
                  <Sparkles className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">
                    {selectedDate || selectedTopicId ? "No discussions match the filters" : "No discussions detected yet"}
                  </p>
                  {!selectedDate && !selectedTopicId && (
                    <p className="text-sm text-muted-foreground mt-1">
                      Click "Analyze" to detect thematic discussions in your chat history
                    </p>
                  )}
                </div>
              )
            )}
            
            {!searchResults && loadingMore && (
              <div className="flex justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            )}
          </div>
        </div>

        {!searchResults && total > data.length && !loadingMore && (
          <p className="text-sm text-muted-foreground text-center">
            Loaded {data.length} of {total} discussions
          </p>
        )}
      </div>
    </AppLayout>
  );
}
