"use client";

import { useEffect, useState, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import { messages, people, type Message, type MessageListResponse, type PersonFull, mxcToHttp } from "@/lib/api";
import { formatRelativeTime, truncate } from "@/lib/utils";
import { CornerDownRight, X, ArrowLeft } from "lucide-react";
import { useRoom } from "@/contexts/room-context";

function Avatar({ url, name }: { url: string | null | undefined; name: string | null | undefined }) {
  const avatarUrl = mxcToHttp(url);
  const initial = name?.[0] || "?";
  
  return (
    <div className="relative h-10 w-10 shrink-0">
      {avatarUrl && (
        <img
          src={avatarUrl}
          alt={name || ""}
          className="h-10 w-10 rounded-full object-cover bg-muted absolute inset-0"
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      )}
      <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium">
        {initial}
      </div>
    </div>
  );
}

function MessagesContent() {
  const searchParams = useSearchParams();
  const senderId = searchParams.get("sender_id");
  const { currentRoom } = useRoom();
  
  const [data, setData] = useState<MessageListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [sender, setSender] = useState<PersonFull | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load sender info if filtering by sender
  useEffect(() => {
    if (senderId) {
      people.get(Number(senderId)).then(setSender).catch(console.error);
    } else {
      setSender(null);
    }
  }, [senderId]);

  // Reset page when sender or room changes
  useEffect(() => {
    setPage(1);
  }, [senderId, currentRoom?.id]);

  useEffect(() => {
    async function load() {
      try {
        const params: { page: number; page_size: number; sender_id?: number; room_id?: number } = { 
          page, 
          page_size: 50 
        };
        if (senderId) {
          params.sender_id = Number(senderId);
        }
        if (currentRoom?.id) {
          params.room_id = currentRoom.id;
        }
        const result = await messages.list(params);
        setData(result);
        scrollRef.current?.scrollTo(0, 0);
      } catch (error) {
        console.error("Failed to load messages:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [page, senderId, currentRoom?.id]);

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
      <div className="flex flex-col h-full">
        {/* Back link when filtering */}
        {sender && (
          <Link
            href={`/people/${sender.id}`}
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to {sender.display_name}
          </Link>
        )}
        
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Messages</h1>
            {sender && (
              <div className="flex items-center gap-2 px-3 py-1 bg-muted rounded-full text-sm">
                <span>by {sender.display_name}</span>
                <Link
                  href="/messages"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </Link>
              </div>
            )}
          </div>
          {data && (
            <span className="text-sm text-muted-foreground">
              {data.total.toLocaleString()} messages
            </span>
          )}
        </div>

        {/* Messages list - scrollable */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto rounded-xl border bg-card">
          <div className="p-4 space-y-3">
            {data?.messages.map((msg) => (
              <div key={msg.id} className="flex items-start gap-3">
                <Avatar url={msg.sender?.avatar_url} name={msg.sender?.display_name} />
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
            ))}
          </div>
        </div>

        {/* Pagination - fixed at bottom */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-center gap-2 pt-4">
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

export default function MessagesPage() {
  return (
    <Suspense fallback={
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </AppLayout>
    }>
      <MessagesContent />
    </Suspense>
  );
}
