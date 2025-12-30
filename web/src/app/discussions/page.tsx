"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import {
  discussions,
  type DiscussionBrief,
  type AnalysisStatus,
  type TopicBrief,
  type TopicClassificationStatus,
} from "@/lib/api";
import { formatRelativeTime, truncate } from "@/lib/utils";
import { Sparkles, Play, Loader2, AlertCircle, Users, MessageSquare, Tag } from "lucide-react";

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
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus | null>(null);
  const [startingAnalysis, setStartingAnalysis] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  
  // Topics state
  const [topics, setTopics] = useState<TopicBrief[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);
  const [topicClassificationStatus, setTopicClassificationStatus] = useState<TopicClassificationStatus | null>(null);
  const [startingClassification, setStartingClassification] = useState(false);

  const loadDiscussions = useCallback(async (topicId?: number | null) => {
    try {
      const params: { topic_id?: number } = {};
      if (topicId !== null && topicId !== undefined) {
        params.topic_id = topicId;
      }
      const result = await discussions.list(params);
      setData(result.discussions);
      setTotal(result.total);
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

  useEffect(() => {
    async function load() {
      await Promise.all([loadDiscussions(), loadStatus(), loadTopics(), loadTopicClassificationStatus()]);
      setLoading(false);
    }
    load();
  }, [loadDiscussions, loadStatus, loadTopics, loadTopicClassificationStatus]);

  // Reload discussions when topic filter changes
  useEffect(() => {
    if (!loading) {
      loadDiscussions(selectedTopicId);
    }
  }, [selectedTopicId, loadDiscussions, loading]);

  // Poll for status and discussions while analysis is running
  useEffect(() => {
    if (analysisStatus?.status !== "running") return;

    const interval = setInterval(async () => {
      await Promise.all([
        loadStatus(),
        loadDiscussions(selectedTopicId),
      ]);
    }, 2000);

    return () => clearInterval(interval);
  }, [analysisStatus?.status, loadStatus, loadDiscussions, selectedTopicId]);

  // Poll for topic classification status
  useEffect(() => {
    if (topicClassificationStatus?.status !== "running") return;

    const interval = setInterval(async () => {
      const status = await loadTopicClassificationStatus();
      if (status?.status === "completed") {
        await Promise.all([loadTopics(), loadDiscussions(selectedTopicId)]);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [topicClassificationStatus?.status, loadTopicClassificationStatus, loadTopics, loadDiscussions, selectedTopicId]);

  // Group discussions by date and create timeline
  const { timeline, filteredDiscussions } = useMemo(() => {
    const dateMap = new Map<string, { date: Date; count: number }>();
    
    data.forEach((d) => {
      const date = new Date(d.started_at);
      const dateKey = date.toISOString().split("T")[0];
      const existing = dateMap.get(dateKey);
      if (existing) {
        existing.count++;
      } else {
        dateMap.set(dateKey, { date, count: 1 });
      }
    });

    const timeline = Array.from(dateMap.entries())
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([key, value]) => ({
        dateKey: key,
        date: value.date,
        count: value.count,
      }));

    const filtered = selectedDate
      ? data.filter((d) => d.started_at.startsWith(selectedDate))
      : data;

    return { timeline, filteredDiscussions: filtered };
  }, [data, selectedDate]);

  const handleStartAnalysis = async () => {
    setStartingAnalysis(true);
    setError(null);
    try {
      await discussions.analyze();
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
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Sparkles className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Discussions</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleStartAnalysis}
              disabled={startingAnalysis || isRunning}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {startingAnalysis || isRunning ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {isRunning ? "Analyzing..." : "Analyze"}
            </button>
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
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Analysis: {analysisStatus.windows_processed} / {analysisStatus.total_windows} windows</span>
              <span>{analysisStatus.discussions_found} discussions</span>
            </div>
            <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-green-700 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {isClassifying && (
          <div className="space-y-1">
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
          <div className="flex gap-2 overflow-x-auto pb-2 -mx-2 px-2">
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

        <p className="text-muted-foreground">
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
              Last analysis: {formatRelativeTime(analysisStatus.completed_at)} - 
              Found {analysisStatus.discussions_found} discussions using {analysisStatus.tokens_used.toLocaleString()} tokens
            </p>
          </div>
        )}

        {/* Main content with timeline */}
        <div className="flex gap-6">
          {/* Timeline sidebar */}
          {timeline.length > 0 && (
            <div className="w-48 flex-shrink-0">
              <div className="sticky top-4">
                <h3 className="text-sm font-medium mb-3 text-muted-foreground">Timeline</h3>
                <div className="relative">
                  {/* Vertical line */}
                  <div className="absolute left-[7px] top-2 bottom-2 w-0.5 bg-border" />
                  
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
                    <span className="text-xs text-muted-foreground ml-auto">{data.length}</span>
                  </button>

                  {timeline.map(({ dateKey, date, count }) => (
                    <button
                      key={dateKey}
                      onClick={() => setSelectedDate(dateKey)}
                      className={`relative flex items-center gap-3 w-full text-left py-2 group ${
                        selectedDate === dateKey ? "text-primary" : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {/* Bead */}
                      <div
                        className={`w-4 h-4 rounded-full border-2 flex-shrink-0 z-10 transition-colors ${
                          selectedDate === dateKey
                            ? "bg-primary border-primary"
                            : "bg-background border-muted-foreground/30 group-hover:border-muted-foreground"
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm">
                          {date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                        </span>
                        <span className="text-xs text-muted-foreground ml-2">{count}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Discussions list */}
          <div className="flex-1 space-y-4">
            {filteredDiscussions.map((discussion) => (
              <Link
                key={discussion.id}
                href={`/discussions/${discussion.id}`}
                className="block rounded-xl border bg-card p-4 hover:bg-muted/50 transition-colors"
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
            ))}

            {filteredDiscussions.length === 0 && !isRunning && (
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
            )}
          </div>
        </div>

        {total > data.length && (
          <p className="text-sm text-muted-foreground text-center">
            Showing {data.length} of {total} discussions
          </p>
        )}
      </div>
    </AppLayout>
  );
}
