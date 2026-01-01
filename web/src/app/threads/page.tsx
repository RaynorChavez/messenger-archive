"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { threads, type Thread } from "@/lib/api";
import { formatRelativeTime, truncate } from "@/lib/utils";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useRoom } from "@/contexts/room-context";
import { Avatar } from "@/components/ui/avatar";

export default function ThreadsPage() {
  const [data, setData] = useState<Thread[]>([]);
  const [expandedThread, setExpandedThread] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const { currentRoom } = useRoom();

  useEffect(() => {
    async function load() {
      try {
        const result = await threads.list(undefined, currentRoom?.id);
        setData(result.threads);
      } catch (error) {
        console.error("Failed to load threads:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [currentRoom?.id]);

  const toggleThread = async (threadId: number) => {
    if (expandedThread === threadId) {
      setExpandedThread(null);
    } else {
      // Load full thread data
      try {
        const fullThread = await threads.get(threadId);
        setData((prev) =>
          prev.map((t) => (t.id === threadId ? fullThread : t))
        );
        setExpandedThread(threadId);
      } catch (error) {
        console.error("Failed to load thread:", error);
      }
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
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Threads</h1>

        <div className="space-y-4">
          {data.map((thread) => (
            <div key={thread.id} className="rounded-xl border bg-card">
              {/* Thread header */}
              <button
                onClick={() => toggleThread(thread.id)}
                className="w-full p-4 flex items-start gap-3 text-left hover:bg-muted/50 transition-colors"
              >
                {expandedThread === thread.id ? (
                  <ChevronDown className="h-5 w-5 mt-0.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-5 w-5 mt-0.5 text-muted-foreground" />
                )}
                <Avatar 
                  src={thread.started_by?.avatar_url} 
                  name={thread.started_by?.display_name} 
                  size="md" 
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">
                      {thread.started_by?.display_name || "Unknown"}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      · {thread.message_count} messages
                    </span>
                    <span className="text-sm text-muted-foreground ml-auto">
                      {formatRelativeTime(thread.last_message_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {truncate(thread.preview || "", 150)}
                  </p>
                </div>
              </button>

              {/* Expanded thread messages */}
              {expandedThread === thread.id && thread.messages && (
                <div className="border-t px-4 py-2">
                  {thread.messages.map((msg) => (
                    <div
                      key={msg.id}
                      className="py-2 flex gap-3"
                      style={{ paddingLeft: `${msg.depth * 24}px` }}
                    >
                      <Avatar 
                        src={msg.sender?.avatar_url} 
                        name={msg.sender?.display_name} 
                        size="sm" 
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">
                            {msg.sender?.display_name || "Unknown"}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {formatRelativeTime(msg.timestamp)}
                          </span>
                        </div>
                        <p className="text-sm mt-0.5">{msg.content}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          {data.length === 0 && (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No threads yet</p>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
