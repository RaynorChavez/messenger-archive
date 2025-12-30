"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { messages, type Message, type MessageListResponse } from "@/lib/api";
import { formatRelativeTime, truncate } from "@/lib/utils";
import { CornerDownRight } from "lucide-react";

export default function MessagesPage() {
  const [data, setData] = useState<MessageListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const result = await messages.list({ page, page_size: 50 });
        setData(result);
      } catch (error) {
        console.error("Failed to load messages:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [page]);

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
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Messages</h1>
        </div>

        {/* Messages list */}
        <div className="rounded-xl border bg-card divide-y">
          {data?.messages.map((msg) => (
            <div key={msg.id} className="p-4">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium shrink-0">
                  {msg.sender?.display_name?.[0] || "?"}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">
                      {msg.sender?.display_name || "Unknown"}
                    </span>
                    {msg.reply_to_sender && (
                      <span className="text-sm text-muted-foreground flex items-center gap-1">
                        <CornerDownRight className="h-3 w-3" />
                        Reply to {msg.reply_to_sender.display_name}
                      </span>
                    )}
                    <span className="text-sm text-muted-foreground ml-auto">
                      {formatRelativeTime(msg.timestamp)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm">{msg.content}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 rounded border disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {data.total_pages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
              disabled={page === data.total_pages}
              className="px-3 py-1 rounded border disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
