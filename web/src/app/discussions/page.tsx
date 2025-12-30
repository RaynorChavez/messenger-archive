"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import {
  discussions,
  type DiscussionBrief,
  type AnalysisStatus,
} from "@/lib/api";
import { formatRelativeTime, truncate } from "@/lib/utils";
import { Sparkles, Play, Loader2, AlertCircle, Users, MessageSquare } from "lucide-react";

export default function DiscussionsPage() {
  const [data, setData] = useState<DiscussionBrief[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus | null>(null);
  const [startingAnalysis, setStartingAnalysis] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDiscussions = useCallback(async () => {
    try {
      const result = await discussions.list();
      setData(result.discussions);
      setTotal(result.total);
    } catch (err) {
      console.error("Failed to load discussions:", err);
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

  useEffect(() => {
    async function load() {
      await Promise.all([loadDiscussions(), loadStatus()]);
      setLoading(false);
    }
    load();
  }, [loadDiscussions, loadStatus]);

  // Poll for status and discussions while analysis is running
  useEffect(() => {
    if (analysisStatus?.status !== "running") return;

    const interval = setInterval(async () => {
      const [status] = await Promise.all([
        loadStatus(),
        loadDiscussions(), // Also refresh discussions list to show new ones
      ]);
      // If completed, one final refresh is already done above
    }, 2000);

    return () => clearInterval(interval);
  }, [analysisStatus?.status, loadStatus, loadDiscussions]);

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
            {isRunning ? "Analyzing..." : "Analyze Messages"}
          </button>
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-green-700 rounded-full transition-all duration-300"
            style={{ width: `${isRunning ? progress : 0}%` }}
          />
        </div>

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

        {isRunning && (
          <div className="rounded-xl border bg-card p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Analysis in progress</span>
              <span className="text-sm text-muted-foreground">
                {analysisStatus.windows_processed} / {analysisStatus.total_windows} windows
              </span>
            </div>
            <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
              <span>{analysisStatus.discussions_found} discussions found</span>
              <span>{analysisStatus.tokens_used.toLocaleString()} tokens used</span>
            </div>
          </div>
        )}

        {analysisStatus?.status === "completed" && analysisStatus.completed_at && (
          <div className="rounded-lg border p-3 bg-muted/50">
            <p className="text-sm text-muted-foreground">
              Last analysis: {formatRelativeTime(analysisStatus.completed_at)} - 
              Found {analysisStatus.discussions_found} discussions using {analysisStatus.tokens_used.toLocaleString()} tokens
            </p>
          </div>
        )}

        {/* Discussions list */}
        <div className="space-y-4">
          {data.map((discussion) => (
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
                  {discussion.summary && (
                    <p className="mt-2 text-sm text-muted-foreground">
                      {truncate(discussion.summary, 200)}
                    </p>
                  )}
                </div>
              </div>
            </Link>
          ))}

          {data.length === 0 && !isRunning && (
            <div className="text-center py-12">
              <Sparkles className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">No discussions detected yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Click "Analyze Messages" to detect thematic discussions in your chat history
              </p>
            </div>
          )}
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
