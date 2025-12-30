"use client";

import { useEffect, useState } from "react";
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
      <div className="space-y-6">
        <Link
          href="/discussions"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Discussions
        </Link>

        {/* Discussion header */}
        <div className="rounded-xl border bg-card p-6">
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

        {/* Messages */}
        <div className="rounded-xl border bg-card">
          <div className="p-4 border-b">
            <h2 className="font-semibold">Messages in this discussion</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Confidence score indicates how relevant each message is to this discussion
            </p>
          </div>
          <div className="divide-y">
            {discussion.messages.map((msg) => (
              <div key={msg.id} className="p-4 hover:bg-muted/30 transition-colors">
                <div className="flex items-start gap-3">
                  {msg.sender?.avatar_url && mxcToHttp(msg.sender.avatar_url) ? (
                    <img
                      src={mxcToHttp(msg.sender.avatar_url)!}
                      alt={msg.sender.display_name || "Avatar"}
                      className="h-8 w-8 rounded-full object-cover"
                    />
                  ) : (
                    <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-sm font-medium">
                      {msg.sender?.display_name?.[0] || "?"}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm">
                        {msg.sender?.display_name || "Unknown"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatRelativeTime(msg.timestamp)}
                      </span>
                      <ConfidenceBadge confidence={msg.confidence} />
                    </div>
                    <p className="mt-1 text-sm">{msg.content}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
