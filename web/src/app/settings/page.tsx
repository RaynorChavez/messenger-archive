"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { settings, type SettingsStatus } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function SettingsPage() {
  const [data, setData] = useState<SettingsStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const result = await settings.status();
        setData(result);
      } catch (error) {
        console.error("Failed to load settings:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

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
