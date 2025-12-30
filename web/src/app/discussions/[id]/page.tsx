"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import { discussions, type DiscussionFull, type ContextMessage, type GapInfo, mxcToHttp } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { ArrowLeft, Sparkles, Users, MessageSquare, Calendar, ChevronUp, ChevronDown, Loader2 } from "lucide-react";

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

function ContextMessageItem({ msg }: { msg: ContextMessage }) {
  return (
    <div className="flex items-start gap-3 opacity-60">
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
        </div>
        <div className="mt-1 p-3 rounded-lg bg-muted/30 border border-dashed inline-block max-w-[85%]">
          <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
        </div>
      </div>
    </div>
  );
}

interface ContextExpanderProps {
  discussionId: number;
  position: "before" | "after";
}

function ContextExpander({ discussionId, position }: ContextExpanderProps) {
  const [messages, setMessages] = useState<ContextMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const loadContext = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    try {
      // Load 5 more messages each time
      const currentCount = messages.length;
      const result = await discussions.context(discussionId, position, currentCount + 5);
      setMessages(result.messages);
      setHasMore(result.has_more);
      setExpanded(true);
    } catch (error) {
      console.error("Failed to load context:", error);
    } finally {
      setLoading(false);
    }
  }, [discussionId, position, messages.length, loading]);

  const Icon = position === "before" ? ChevronUp : ChevronDown;
  const label = position === "before" ? "Show earlier messages" : "Show later messages";

  if (!expanded) {
    return (
      <button
        onClick={loadContext}
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground hover:text-foreground border-y border-dashed bg-muted/20 hover:bg-muted/40 transition-colors"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Icon className="h-4 w-4" />
        )}
        {label}
      </button>
    );
  }

  return (
    <div className="space-y-4">
      {position === "before" && hasMore && (
        <button
          onClick={loadContext}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground hover:text-foreground border-y border-dashed bg-muted/20 hover:bg-muted/40 transition-colors"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ChevronUp className="h-4 w-4" />
          )}
          Load more context
        </button>
      )}
      
      {messages.map((msg) => (
        <ContextMessageItem key={msg.id} msg={msg} />
      ))}
      
      {position === "after" && hasMore && (
        <button
          onClick={loadContext}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground hover:text-foreground border-y border-dashed bg-muted/20 hover:bg-muted/40 transition-colors"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
          Load more context
        </button>
      )}
      
      {/* Separator between context and discussion */}
      <div className="flex items-center gap-3 py-2">
        <div className="flex-1 border-t-2 border-primary/30" />
        <span className="text-xs text-primary font-medium px-2">
          {position === "before" ? "Discussion starts" : "Discussion ends"}
        </span>
        <div className="flex-1 border-t-2 border-primary/30" />
      </div>
    </div>
  );
}

interface GapExpanderProps {
  discussionId: number;
  gap: GapInfo;
}

function GapExpander({ discussionId, gap }: GapExpanderProps) {
  const [messages, setMessages] = useState<ContextMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const loadGapMessages = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    try {
      const result = await discussions.gapMessages(
        discussionId,
        gap.after_message_id,
        gap.before_message_id
      );
      setMessages(result.messages);
      setExpanded(true);
    } catch (error) {
      console.error("Failed to load gap messages:", error);
    } finally {
      setLoading(false);
    }
  }, [discussionId, gap, loading]);

  if (!expanded) {
    return (
      <button
        onClick={loadGapMessages}
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 py-2 my-2 text-sm text-muted-foreground hover:text-foreground border border-dashed rounded-lg bg-muted/20 hover:bg-muted/40 transition-colors"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <>
            <MessageSquare className="h-4 w-4" />
            Show {gap.count} hidden message{gap.count !== 1 ? "s" : ""}
          </>
        )}
      </button>
    );
  }

  return (
    <div className="space-y-4 my-4 py-4 border-y border-dashed">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <div className="flex-1 border-t border-dashed" />
        <span>{gap.count} message{gap.count !== 1 ? "s" : ""} not in this discussion</span>
        <div className="flex-1 border-t border-dashed" />
      </div>
      {messages.map((msg) => (
        <ContextMessageItem key={msg.id} msg={msg} />
      ))}
    </div>
  );
}

export default function DiscussionDetailPage() {
  const params = useParams();
  const discussionId = Number(params.id);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [discussion, setDiscussion] = useState<DiscussionFull | null>(null);
  const [gaps, setGaps] = useState<GapInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [discussionData, gapsData] = await Promise.all([
          discussions.get(discussionId),
          discussions.gaps(discussionId),
        ]);
        setDiscussion(discussionData);
        setGaps(gapsData.gaps);
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
            {/* Context before discussion */}
            <ContextExpander discussionId={discussionId} position="before" />
            
            {/* Discussion messages with gap expanders */}
            {discussion.messages.map((msg, index) => {
              // Check if there's a gap after this message
              const gapAfterThis = gaps.find(g => g.after_message_id === msg.id);
              
              return (
                <div key={msg.id}>
                  <div className="flex items-start gap-3 group">
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
                  
                  {/* Gap expander after this message */}
                  {gapAfterThis && (
                    <GapExpander
                      discussionId={discussionId}
                      gap={gapAfterThis}
                    />
                  )}
                </div>
              );
            })}
            
            {/* Context after discussion */}
            <ContextExpander discussionId={discussionId} position="after" />
            
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
