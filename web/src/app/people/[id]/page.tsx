"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import { people, type PersonFull, type Message, type PersonActivityResponse, mxcToHttp } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { ArrowLeft, Edit2, RefreshCw, Loader2, AlertCircle } from "lucide-react";
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
  const personId = Number(params.id);

  const [person, setPerson] = useState<PersonFull | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState("");
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  
  // Activity chart state
  const [activity, setActivity] = useState<PersonActivityResponse | null>(null);
  const [activityPeriod, setActivityPeriod] = useState<"month" | "3months" | "6months" | "year" | "all">("6months");
  const [activityGranularity, setActivityGranularity] = useState<"day" | "week" | "month">("week");

  useEffect(() => {
    async function load() {
      try {
        const [personData, messagesData, activityData] = await Promise.all([
          people.get(personId),
          people.messages(personId),
          people.activity(personId, activityPeriod, activityGranularity),
        ]);
        setPerson(personData);
        setNotes(personData.notes || "");
        setMessages(messagesData.messages);
        setActivity(activityData);
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
      const updated = await people.generateSummary(personId);
      setPerson(updated);
    } catch (error) {
      console.error("Failed to generate summary:", error);
      setSummaryError(error instanceof Error ? error.message : "Failed to generate summary");
    } finally {
      setGeneratingSummary(false);
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

              {/* AI Summary */}
              <div className="mt-4 rounded-lg border p-4 bg-muted/50">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">AI Summary</span>
                  <div className="flex items-center gap-2">
                    {person.ai_summary_generated_at && (
                      <span className="text-xs text-muted-foreground">
                        Generated {formatRelativeTime(person.ai_summary_generated_at)}
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
            </div>
          </div>
        </div>

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
