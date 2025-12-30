"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import { people, type PersonFull, type Message } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { ArrowLeft, Edit2 } from "lucide-react";

export default function PersonDetailPage() {
  const params = useParams();
  const personId = Number(params.id);

  const [person, setPerson] = useState<PersonFull | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [personData, messagesData] = await Promise.all([
          people.get(personId),
          people.messages(personId),
        ]);
        setPerson(personData);
        setNotes(personData.notes || "");
        setMessages(messagesData.messages);
      } catch (error) {
        console.error("Failed to load person:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [personId]);

  const handleSaveNotes = async () => {
    try {
      const updated = await people.update(personId, notes);
      setPerson(updated);
      setEditingNotes(false);
    } catch (error) {
      console.error("Failed to save notes:", error);
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
            <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center text-2xl font-medium">
              {person.display_name?.[0] || "?"}
            </div>
            <div className="flex-1">
              <h1 className="text-2xl font-bold">
                {person.display_name || "Unknown"}
              </h1>
              <p className="text-muted-foreground mt-1">
                {person.message_count.toLocaleString()} messages · Member since{" "}
                {new Date(person.created_at).toLocaleDateString()}
              </p>

              {/* AI Summary placeholder */}
              <div className="mt-4 rounded-lg border p-4 bg-muted/50">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">AI Summary</span>
                  <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
                    Coming Soon
                  </span>
                </div>
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
