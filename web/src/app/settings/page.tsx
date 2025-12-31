"use client";

import { useEffect, useState, useCallback } from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { settings, search, type SettingsStatus, type ReindexStatus } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function SettingsPage() {
  const [data, setData] = useState<SettingsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [reindexStatus, setReindexStatus] = useState<ReindexStatus | null>(null);
  const [reindexing, setReindexing] = useState(false);

  const loadReindexStatus = useCallback(async () => {
    try {
      const status = await search.status();
      setReindexStatus(status);
      return status;
    } catch (error) {
      console.error("Failed to load reindex status:", error);
      return null;
    }
  }, []);

  useEffect(() => {
    async function load() {
      try {
        const [settingsResult] = await Promise.all([
          settings.status(),
          loadReindexStatus(),
        ]);
        setData(settingsResult);
      } catch (error) {
        console.error("Failed to load settings:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [loadReindexStatus]);

  // Poll for reindex status when running
  useEffect(() => {
    if (reindexStatus?.status !== "running") return;

    const interval = setInterval(async () => {
      const status = await loadReindexStatus();
      if (status?.status !== "running") {
        setReindexing(false);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [reindexStatus?.status, loadReindexStatus]);

  const handleReindex = async () => {
    try {
      setReindexing(true);
      await search.reindex("all");
      await loadReindexStatus();
    } catch (error) {
      console.error("Failed to start reindex:", error);
      setReindexing(false);
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

  return (
    <AppLayout>
      <div className="space-y-6 max-w-2xl">
        <h1 className="text-2xl font-bold">Settings</h1>

        {/* Bridge Status */}
        <div className="rounded-xl border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">Bridge Status</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm">Messenger Connection</span>
              <span className="flex items-center gap-2 text-sm">
                <span
                  className={`h-2 w-2 rounded-full ${
                    data?.bridge.messenger_connected
                      ? "bg-green-500"
                      : "bg-red-500"
                  }`}
                />
                {data?.bridge.messenger_connected ? "Connected" : "Disconnected"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Last synced</span>
              <span className="text-sm text-muted-foreground">
                {data?.bridge.last_synced
                  ? formatDateTime(data.bridge.last_synced)
                  : "Never"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Matrix homeserver</span>
              <span className="flex items-center gap-2 text-sm">
                <span
                  className={`h-2 w-2 rounded-full ${
                    data?.bridge.matrix_running ? "bg-green-500" : "bg-red-500"
                  }`}
                />
                {data?.bridge.matrix_running ? "Running" : "Stopped"}
              </span>
            </div>
          </div>
          <button className="mt-4 px-4 py-2 border rounded-lg text-sm hover:bg-muted transition-colors">
            Re-authenticate
          </button>
        </div>

        {/* Archive Stats */}
        <div className="rounded-xl border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">Archive Stats</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm">Messages archived</span>
              <span className="text-sm">
                {data?.archive.messages_archived.toLocaleString()}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Database size</span>
              <span className="text-sm">
                {data?.archive.database_size_mb} MB
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Oldest message</span>
              <span className="text-sm text-muted-foreground">
                {data?.archive.oldest_message
                  ? formatDateTime(data.archive.oldest_message)
                  : "N/A"}
              </span>
            </div>
          </div>
        </div>

        {/* Semantic Search */}
        <div className="rounded-xl border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">Semantic Search</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Build vector embeddings for semantic search across messages, discussions, people, and topics.
          </p>
          
          {reindexStatus && (
            <div className="space-y-3 mb-4">
              <div className="flex items-center justify-between">
                <span className="text-sm">Status</span>
                <span className="flex items-center gap-2 text-sm">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      reindexStatus.status === "running"
                        ? "bg-yellow-500 animate-pulse"
                        : reindexStatus.status === "completed"
                        ? "bg-green-500"
                        : reindexStatus.status === "failed"
                        ? "bg-red-500"
                        : "bg-gray-400"
                    }`}
                  />
                  {reindexStatus.status === "running"
                    ? "Indexing..."
                    : reindexStatus.status === "completed"
                    ? "Ready"
                    : reindexStatus.status === "failed"
                    ? "Failed"
                    : "Not indexed"}
                </span>
              </div>
              
              {reindexStatus.status === "running" && reindexStatus.progress && (
                <div className="space-y-2">
                  {Object.entries(reindexStatus.progress).map(([type, progress]) => (
                    <div key={type} className="space-y-1">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span className="capitalize">{type}s</span>
                        <span>{progress.completed} / {progress.total}</span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary transition-all duration-300"
                          style={{
                            width: `${progress.total > 0 ? (progress.completed / progress.total) * 100 : 0}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              
              {reindexStatus.last_completed_at && (
                <div className="flex items-center justify-between">
                  <span className="text-sm">Last indexed</span>
                  <span className="text-sm text-muted-foreground">
                    {formatDateTime(reindexStatus.last_completed_at)}
                  </span>
                </div>
              )}
              
              {reindexStatus.error && (
                <p className="text-sm text-red-500">
                  Error: {reindexStatus.error}
                </p>
              )}
            </div>
          )}
          
          <button
            onClick={handleReindex}
            disabled={reindexing || reindexStatus?.status === "running"}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {reindexing || reindexStatus?.status === "running"
              ? "Indexing..."
              : "Build Search Index"}
          </button>
        </div>

        {/* Security */}
        <div className="rounded-xl border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">Security</h2>
          <div className="flex items-center justify-between">
            <span className="text-sm">Archive Password</span>
            <button className="px-4 py-2 border rounded-lg text-sm hover:bg-muted transition-colors">
              Change Password
            </button>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
