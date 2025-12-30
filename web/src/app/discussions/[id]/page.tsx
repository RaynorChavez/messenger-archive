"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import { discussions, type DiscussionFull, mxcToHttp } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { ArrowLeft, Sparkles, Users, MessageSquare, Calendar } from "lucide-react";

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const percent = Math.round(confidence * 100);
  let colorClass = "bg-green-500/20 text-green-500";
  if (percent < 70) colorClass = "bg-yellow-500/20 text-yellow-500";
  if (percent < 50) colorClass = "bg-red-500/20 text-red-500";

  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${colorClass}`}>
      {percent}%
    </span>
  );
}

export default function DiscussionDetailPage() {
  const params = useParams();
  const discussionId = Number(params.id);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [discussion, setDiscussion] = useState<DiscussionFull | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await discussions.get(discussionId);
        setDiscussion(data);
      } catch (error) {
        console.error("Failed to load discussion:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [discussionId]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </AppLayout>
    );
  }

  if (!discussion) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground">Discussion not found</p>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="h-full flex flex-col">
        <Link
          href="/discussions"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Discussions
        </Link>

        {/* Discussion header */}
        <div className="rounded-xl border bg-card p-6 mb-4 flex-shrink-0">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-lg bg-primary/10">
              <Sparkles className="h-6 w-6 text-primary" />
            </div>
            <div className="flex-1">
              <h1 className="text-2xl font-bold">{discussion.title}</h1>
              <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <MessageSquare className="h-4 w-4" />
                  {discussion.message_count} messages
                </span>
                <span className="flex items-center gap-1">
                  <Users className="h-4 w-4" />
                  {discussion.participant_count} participants
                </span>
                <span className="flex items-center gap-1">
                  <Calendar className="h-4 w-4" />
                  {new Date(discussion.started_at).toLocaleDateString()} - {new Date(discussion.ended_at).toLocaleDateString()}
                </span>
              </div>

              {discussion.summary && (
                <div className="mt-4 p-4 rounded-lg bg-muted/50 border">
                  <p className="text-sm font-medium mb-2">AI Summary</p>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                    {discussion.summary}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Messages - scrollable chat window */}
        <div className="rounded-xl border bg-card flex-1 flex flex-col min-h-0">
          <div className="p-4 border-b flex-shrink-0">
            <h2 className="font-semibold">Messages in this discussion</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Confidence score indicates how relevant each message is to this discussion
            </p>
          </div>
          
          {/* Scrollable messages container */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {discussion.messages.map((msg) => (
              <div key={msg.id} className="flex items-start gap-3 group">
                {msg.sender?.avatar_url && mxcToHttp(msg.sender.avatar_url) ? (
                  <img
                    src={mxcToHttp(msg.sender.avatar_url)!}
                    alt={msg.sender.display_name || "Avatar"}
                    className="h-10 w-10 rounded-full object-cover flex-shrink-0"
                  />
                ) : (
                  <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center text-sm font-medium flex-shrink-0">
                    {msg.sender?.display_name?.[0] || "?"}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">
                      {msg.sender?.display_name || "Unknown"}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(msg.timestamp).toLocaleString()}
                    </span>
                    <ConfidenceBadge confidence={msg.confidence} />
                  </div>
                  <div className="mt-1 p-3 rounded-lg bg-muted/50 inline-block max-w-[85%]">
                    <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
