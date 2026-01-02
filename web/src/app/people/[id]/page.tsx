"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import { people, type PersonFull, type Message, type PersonActivityResponse, type PersonRoomStats, type SummaryVersion, mxcToHttp } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { ArrowLeft, Edit2, RefreshCw, Loader2, AlertCircle, MessageCircle, Hash, Shield, ShieldOff, ChevronLeft, ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { virtualChat } from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export default function PersonDetailPage() {
  const params = useParams();
  const router = useRouter();
  const personId = Number(params.id);

  const [person, setPerson] = useState<PersonFull | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState("");
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [startingChat, setStartingChat] = useState(false);
  
  // Summary version navigation
  const [summaryVersions, setSummaryVersions] = useState<SummaryVersion[]>([]);
  const [currentVersionIndex, setCurrentVersionIndex] = useState(0);
  const [loadingVersions, setLoadingVersions] = useState(false);
  
  // Activity chart state
  const [activity, setActivity] = useState<PersonActivityResponse | null>(null);
  const [activityPeriod, setActivityPeriod] = useState<"month" | "3months" | "6months" | "year" | "all">("6months");
  const [activityGranularity, setActivityGranularity] = useState<"day" | "week" | "month">("day");
  
  // Room breakdown state
  const [roomStats, setRoomStats] = useState<PersonRoomStats[]>([]);
  
  // AI Chat opt-out state
  const [aiChatEnabled, setAiChatEnabled] = useState<boolean>(true);
  const [aiChatHasPassword, setAiChatHasPassword] = useState<boolean>(false);
  const [showAiChatModal, setShowAiChatModal] = useState<"disable" | "enable" | null>(null);
  const [aiChatPassword, setAiChatPassword] = useState("");
  const [aiChatConfirmPassword, setAiChatConfirmPassword] = useState("");
  const [aiChatError, setAiChatError] = useState<string | null>(null);
  const [aiChatLoading, setAiChatLoading] = useState(false);

  // Load summary versions
  const loadSummaryVersions = async () => {
    try {
      setLoadingVersions(true);
      const response = await people.summaryVersions(personId);
      setSummaryVersions(response.versions);
      setCurrentVersionIndex(0); // Latest is always first
    } catch (error) {
      console.error("Failed to load summary versions:", error);
    } finally {
      setLoadingVersions(false);
    }
  };

  useEffect(() => {
    async function load() {
      try {
        const [personData, messagesData, activityData, roomsData, aiChatStatus, versionsData] = await Promise.all([
          people.get(personId),
          people.messages(personId),
          people.activity(personId, activityPeriod, activityGranularity),
          people.rooms(personId),
          people.aiChatStatus(personId),
          people.summaryVersions(personId).catch(() => ({ versions: [], total: 0, current_index: 0 })),
        ]);
        setPerson(personData);
        setNotes(personData.notes || "");
        setMessages(messagesData.messages);
        setActivity(activityData);
        setRoomStats(roomsData.rooms);
        setAiChatEnabled(aiChatStatus.enabled);
        setAiChatHasPassword(aiChatStatus.has_password);
        setSummaryVersions(versionsData.versions);
        setCurrentVersionIndex(0);
      } catch (error) {
        console.error("Failed to load person:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [personId, activityPeriod, activityGranularity]);

  const handleSaveNotes = async () => {
    try {
      const updated = await people.update(personId, notes);
      setPerson(updated);
      setEditingNotes(false);
    } catch (error) {
      console.error("Failed to save notes:", error);
    }
  };

  const handleGenerateSummary = async () => {
    setGeneratingSummary(true);
    setSummaryError(null);
    try {
      await people.generateSummary(personId);
      // Start polling for completion
      pollSummaryStatus();
    } catch (error) {
      console.error("Failed to generate summary:", error);
      setSummaryError(error instanceof Error ? error.message : "Failed to generate summary");
      setGeneratingSummary(false);
    }
  };

  const pollSummaryStatus = async () => {
    const poll = async () => {
      try {
        const status = await people.summaryStatus(personId);
        if (status.status === "completed") {
          // Reload person data and summary versions
          const [updatedPerson, versionsData] = await Promise.all([
            people.get(personId),
            people.summaryVersions(personId),
          ]);
          setPerson(updatedPerson);
          setSummaryVersions(versionsData.versions);
          setCurrentVersionIndex(0); // Show latest
          setGeneratingSummary(false);
        } else if (status.status === "failed") {
          setSummaryError(status.error || "Failed to generate summary");
          setGeneratingSummary(false);
        } else if (status.status === "running") {
          // Continue polling
          setTimeout(poll, 1000);
        } else {
          setGeneratingSummary(false);
        }
      } catch (error) {
        console.error("Failed to check summary status:", error);
        setSummaryError("Failed to check status");
        setGeneratingSummary(false);
      }
    };
    poll();
  };

  const handleStartChat = async () => {
    setStartingChat(true);
    try {
      const conv = await virtualChat.createConversation([personId]);
      router.push(`/virtual-chat?id=${conv.id}`);
    } catch (error) {
      console.error("Failed to start chat:", error);
    } finally {
      setStartingChat(false);
    }
  };

  const handleDisableAiChat = async () => {
    if (aiChatPassword !== aiChatConfirmPassword) {
      setAiChatError("Passwords don't match");
      return;
    }
    if (aiChatPassword.length < 4) {
      setAiChatError("Password must be at least 4 characters");
      return;
    }
    
    setAiChatLoading(true);
    setAiChatError(null);
    try {
      await people.disableAIChat(personId, aiChatPassword);
      setAiChatEnabled(false);
      setAiChatHasPassword(true);
      setShowAiChatModal(null);
      setAiChatPassword("");
      setAiChatConfirmPassword("");
    } catch (error) {
      setAiChatError(error instanceof Error ? error.message : "Failed to disable AI chat");
    } finally {
      setAiChatLoading(false);
    }
  };

  const handleEnableAiChat = async () => {
    if (!aiChatPassword) {
      setAiChatError("Password is required");
      return;
    }
    
    setAiChatLoading(true);
    setAiChatError(null);
    try {
      await people.enableAIChat(personId, aiChatPassword);
      setAiChatEnabled(true);
      setAiChatHasPassword(false);
      setShowAiChatModal(null);
      setAiChatPassword("");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to enable AI chat";
      if (message.includes("403")) {
        setAiChatError("Incorrect password");
      } else {
        setAiChatError(message);
      }
    } finally {
      setAiChatLoading(false);
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

  if (!person) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground">Person not found</p>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <Link
          href="/people"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to People
        </Link>

        {/* Profile card */}
        <div className="rounded-xl border bg-card p-6">
          <div className="flex items-start gap-6">
            {mxcToHttp(person.avatar_url) ? (
              <img
                src={mxcToHttp(person.avatar_url)!}
                alt={person.display_name || "Avatar"}
                className="h-20 w-20 rounded-full object-cover"
              />
            ) : (
              <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center text-2xl font-medium">
                {person.display_name?.[0] || "?"}
              </div>
            )}
            <div className="flex-1">
              <h1 className="text-2xl font-bold">
                {person.display_name || "Unknown"}
              </h1>
              <div className="flex items-center gap-3 mt-1">
                <p className="text-muted-foreground">
                  {person.message_count.toLocaleString()} messages · Member since{" "}
                  {new Date(person.created_at).toLocaleDateString()}
                </p>
                {person.fb_profile_url && (
                  <a
                    href={person.fb_profile_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-500 hover:underline"
                  >
                    Facebook Profile
                  </a>
                )}
              </div>
              
              {/* Virtual Chat Button */}
              <button
                onClick={handleStartChat}
                disabled={startingChat || !aiChatEnabled}
                title={!aiChatEnabled ? "This persona has opted out of AI virtual chat" : undefined}
                className={`mt-3 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed ${
                  aiChatEnabled 
                    ? "bg-primary text-primary-foreground hover:bg-primary/90" 
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {startingChat ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Starting chat...
                  </>
                ) : !aiChatEnabled ? (
                  <>
                    <ShieldOff className="h-4 w-4" />
                    Virtual Chat Disabled
                  </>
                ) : (
                  <>
                    <MessageCircle className="h-4 w-4" />
                    Virtual Chat with {person.display_name?.split(" ")[0] || "this person"}
                  </>
                )}
              </button>

              {/* AI Summary */}
              <div className="mt-4 rounded-lg border p-4 bg-muted/50">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">AI Summary</span>
                    {/* Version navigation */}
                    {summaryVersions.length > 1 && (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <button
                          onClick={() => setCurrentVersionIndex(Math.min(currentVersionIndex + 1, summaryVersions.length - 1))}
                          disabled={currentVersionIndex >= summaryVersions.length - 1}
                          className="p-0.5 hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed"
                          title="Older version"
                        >
                          <ChevronLeft className="h-4 w-4" />
                        </button>
                        <span className="min-w-[3ch] text-center">
                          {summaryVersions.length - currentVersionIndex}/{summaryVersions.length}
                        </span>
                        <button
                          onClick={() => setCurrentVersionIndex(Math.max(currentVersionIndex - 1, 0))}
                          disabled={currentVersionIndex <= 0}
                          className="p-0.5 hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed"
                          title="Newer version"
                        >
                          <ChevronRight className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {summaryVersions[currentVersionIndex]?.generated_at && (
                      <span className="text-xs text-muted-foreground">
                        Generated {formatRelativeTime(summaryVersions[currentVersionIndex].generated_at)}
                        {currentVersionIndex > 0 && " (older)"}
                      </span>
                    )}
                    <button
                      onClick={handleGenerateSummary}
                      disabled={generatingSummary}
                      className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed"
                      title={person.ai_summary ? "Regenerate summary" : "Generate summary"}
                    >
                      {generatingSummary ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>

                {summaryError && (
                  <div className="flex items-center gap-2 text-sm text-red-500 mb-2">
                    <AlertCircle className="h-4 w-4" />
                    {summaryError}
                  </div>
                )}

                {generatingSummary ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Analyzing {person.message_count.toLocaleString()} messages...
                  </div>
                ) : summaryVersions.length > 0 ? (
                  <>
                    <p className="text-sm whitespace-pre-wrap">{summaryVersions[currentVersionIndex]?.summary}</p>
                    {currentVersionIndex === 0 && person.ai_summary_stale && (
                      <p className="text-xs text-amber-500 mt-2 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" />
                        30+ new messages since last summary - click to regenerate
                      </p>
                    )}
                    {summaryVersions[currentVersionIndex]?.message_count > 0 && (
                      <p className="text-xs text-muted-foreground mt-2">
                        Based on {summaryVersions[currentVersionIndex].message_count.toLocaleString()} messages
                      </p>
                    )}
                  </>
                ) : person.ai_summary ? (
                  <>
                    <p className="text-sm whitespace-pre-wrap">{person.ai_summary}</p>
                    {person.ai_summary_stale && (
                      <p className="text-xs text-amber-500 mt-2 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" />
                        30+ new messages since last summary - click to regenerate
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No summary yet. Click the refresh button to generate one.
                  </p>
                )}
              </div>

              {/* Notes */}
              <div className="mt-4 rounded-lg border p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">Notes</span>
                  {editingNotes ? (
                    <div className="flex gap-2">
                      <button
                        onClick={() => setEditingNotes(false)}
                        className="text-xs text-muted-foreground hover:text-foreground"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSaveNotes}
                        className="text-xs text-primary hover:text-primary/80"
                      >
                        Save
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setEditingNotes(true)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
                {editingNotes ? (
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full min-h-[100px] text-sm bg-background border rounded p-2 outline-none focus:ring-2 focus:ring-primary"
                    placeholder="Add notes about this person..."
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {person.notes || "No notes yet"}
                  </p>
                )}
              </div>

              {/* AI Chat Opt-Out */}
              <div className="mt-4 rounded-lg border p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {aiChatEnabled ? (
                      <Shield className="h-4 w-4 text-green-500" />
                    ) : (
                      <ShieldOff className="h-4 w-4 text-red-500" />
                    )}
                    <span className="text-sm font-medium">AI Virtual Chat</span>
                  </div>
                  <button
                    onClick={() => {
                      setAiChatError(null);
                      setAiChatPassword("");
                      setAiChatConfirmPassword("");
                      setShowAiChatModal(aiChatEnabled ? "disable" : "enable");
                    }}
                    className={`text-xs px-3 py-1 rounded ${
                      aiChatEnabled 
                        ? "bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400" 
                        : "bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400"
                    }`}
                  >
                    {aiChatEnabled ? "Disable" : "Enable"}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  {aiChatEnabled 
                    ? "This persona is available for AI virtual chat. Disable to opt-out."
                    : "This persona has opted out of AI virtual chat."}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* AI Chat Modal */}
        {showAiChatModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-card border rounded-xl p-6 w-full max-w-md mx-4">
              <h3 className="text-lg font-semibold mb-4">
                {showAiChatModal === "disable" ? "Disable AI Virtual Chat" : "Enable AI Virtual Chat"}
              </h3>
              
              {showAiChatModal === "disable" ? (
                <>
                  <p className="text-sm text-muted-foreground mb-4">
                    Set a password to disable this persona from AI virtual chat. Only someone with this password can re-enable it.
                  </p>
                  <div className="space-y-3">
                    <input
                      type="password"
                      placeholder="Password"
                      value={aiChatPassword}
                      onChange={(e) => setAiChatPassword(e.target.value)}
                      className="w-full px-3 py-2 text-sm bg-background border rounded-lg outline-none focus:ring-2 focus:ring-primary"
                    />
                    <input
                      type="password"
                      placeholder="Confirm password"
                      value={aiChatConfirmPassword}
                      onChange={(e) => setAiChatConfirmPassword(e.target.value)}
                      className="w-full px-3 py-2 text-sm bg-background border rounded-lg outline-none focus:ring-2 focus:ring-primary"
                    />
                  </div>
                </>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground mb-4">
                    Enter the password that was set when disabling to re-enable AI virtual chat for this persona.
                  </p>
                  <input
                    type="password"
                    placeholder="Password"
                    value={aiChatPassword}
                    onChange={(e) => setAiChatPassword(e.target.value)}
                    className="w-full px-3 py-2 text-sm bg-background border rounded-lg outline-none focus:ring-2 focus:ring-primary"
                  />
                </>
              )}

              {aiChatError && (
                <div className="flex items-center gap-2 text-sm text-red-500 mt-3">
                  <AlertCircle className="h-4 w-4" />
                  {aiChatError}
                </div>
              )}

              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setShowAiChatModal(null)}
                  className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </button>
                <button
                  onClick={showAiChatModal === "disable" ? handleDisableAiChat : handleEnableAiChat}
                  disabled={aiChatLoading}
                  className={`px-4 py-2 text-sm font-medium rounded-lg disabled:opacity-50 ${
                    showAiChatModal === "disable"
                      ? "bg-red-600 text-white hover:bg-red-700"
                      : "bg-green-600 text-white hover:bg-green-700"
                  }`}
                >
                  {aiChatLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : showAiChatModal === "disable" ? (
                    "Disable"
                  ) : (
                    "Enable"
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Activity Chart */}
        <div className="rounded-xl border bg-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Activity</h2>
            <div className="flex items-center gap-2">
              <select
                value={activityPeriod}
                onChange={(e) => setActivityPeriod(e.target.value as typeof activityPeriod)}
                className="text-sm bg-muted border-0 rounded px-2 py-1"
              >
                <option value="month">Last month</option>
                <option value="3months">Last 3 months</option>
                <option value="6months">Last 6 months</option>
                <option value="year">Last year</option>
                <option value="all">All time</option>
              </select>
              <select
                value={activityGranularity}
                onChange={(e) => setActivityGranularity(e.target.value as typeof activityGranularity)}
                className="text-sm bg-muted border-0 rounded px-2 py-1"
              >
                <option value="day">Daily</option>
                <option value="week">Weekly</option>
                <option value="month">Monthly</option>
              </select>
            </div>
          </div>
          
          {activity && activity.data.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={activity.data}>
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(value) =>
                      new Date(value).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })
                    }
                  />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip
                    labelFormatter={(value) => new Date(value).toLocaleDateString()}
                    formatter={(value: number) => [`${value} messages`, "Count"]}
                  />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={2} />
                </BarChart>
              </ResponsiveContainer>
              <div className="flex items-center justify-center gap-6 mt-4 text-sm text-muted-foreground">
                {activity.most_active_day && (
                  <span>Most active: <strong>{activity.most_active_day}</strong></span>
                )}
                {activity.most_active_hour !== null && (
                  <span>Peak hour: <strong>{activity.most_active_hour}:00</strong></span>
                )}
                <span>Total: <strong>{activity.total_messages.toLocaleString()}</strong> messages</span>
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-[200px]">
              <p className="text-sm text-muted-foreground">No activity data</p>
            </div>
          )}
        </div>

        {/* Room Breakdown */}
        {roomStats.length > 1 && (
          <div className="rounded-xl border bg-card p-6">
            <h2 className="text-lg font-semibold mb-4">Room Breakdown</h2>
            <div className="space-y-3">
              {roomStats.map((room) => {
                const percentage = person ? Math.round((room.message_count / person.message_count) * 100) : 0;
                return (
                  <div key={room.room_id} className="flex items-center gap-4">
                    <div className="flex items-center gap-2 min-w-[180px]">
                      <Hash className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium truncate">
                        {room.room_name?.replace(/ - Manila Dialectics Society$/, "") || `Room ${room.room_id}`}
                      </span>
                    </div>
                    <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                    <div className="text-sm text-muted-foreground min-w-[120px] text-right">
                      {room.message_count.toLocaleString()} ({percentage}%)
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 pt-4 border-t grid grid-cols-2 gap-4 text-sm">
              {roomStats.map((room) => (
                <div key={room.room_id} className="text-muted-foreground">
                  <span className="font-medium text-foreground">
                    {room.room_name?.replace(/ - Manila Dialectics Society$/, "") || `Room ${room.room_id}`}:
                  </span>{" "}
                  {room.first_seen_at && (
                    <>First seen {new Date(room.first_seen_at).toLocaleDateString()}</>
                  )}
                  {room.first_seen_at && room.last_seen_at && ", "}
                  {room.last_seen_at && (
                    <>last active {new Date(room.last_seen_at).toLocaleDateString()}</>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent messages */}
        <div className="rounded-xl border bg-card p-6">
          <h2 className="text-lg font-semibold mb-4">
            Recent Messages by {person.display_name}
          </h2>
          <div className="divide-y">
            {messages.slice(0, 10).map((msg) => (
              <div key={msg.id} className="py-3">
                <p className="text-sm">{msg.content}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {formatRelativeTime(msg.timestamp)}
                </p>
              </div>
            ))}
          </div>
          {messages.length > 10 && (
            <Link
              href={`/messages?sender_id=${person.id}`}
              className="inline-block mt-4 text-sm text-primary hover:text-primary/80"
            >
              View All Messages →
            </Link>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
