"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppLayout } from "@/components/layout/app-layout";
import { people, type PersonFull, mxcToHttp } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { useRoom } from "@/contexts/room-context";

export default function PeoplePage() {
  const [data, setData] = useState<PersonFull[]>([]);
  const [loading, setLoading] = useState(true);
  const { currentRoom } = useRoom();

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const result = await people.list(undefined, currentRoom?.id);
        setData(result.people);
      } catch (error) {
        console.error("Failed to load people:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [currentRoom?.id]);

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
        <h1 className="text-2xl font-bold">People</h1>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {data.map((person) => (
            <Link
              key={person.id}
              href={`/people/${person.id}`}
              className="rounded-xl border bg-card p-6 hover:border-primary transition-colors"
            >
              <div className="flex flex-col items-center text-center">
                {mxcToHttp(person.avatar_url) ? (
                  <img
                    src={mxcToHttp(person.avatar_url)!}
                    alt={person.display_name || "Avatar"}
                    className="h-16 w-16 rounded-full object-cover mb-3"
                  />
                ) : (
                  <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center text-xl font-medium mb-3">
                    {person.display_name?.[0] || "?"}
                  </div>
                )}
                <h3 className="font-medium">
                  {person.display_name || "Unknown"}
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {person.message_count.toLocaleString()} messages
                </p>
                {person.last_message_at && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Last: {formatRelativeTime(person.last_message_at)}
                  </p>
                )}
                {person.fb_profile_url && (
                  <a
                    href={person.fb_profile_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-500 hover:underline mt-2"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Facebook Profile
                  </a>
                )}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </AppLayout>
  );
}
