"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { stats, type Stats, type Message } from "@/lib/api";
import { formatRelativeTime, truncate } from "@/lib/utils";
import { MessageSquare, GitBranch, Users } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useRoom } from "@/contexts/room-context";
import { Avatar } from "@/components/ui/avatar";

function StatCard({
  title,
  value,
  icon: Icon,
}: {
  title: string;
  value: number;
  icon: React.ElementType;
}) {
  return (
    <div className="rounded-xl border bg-card p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-3xl font-bold">{value.toLocaleString()}</p>
          <p className="text-sm text-muted-foreground">{title}</p>
        </div>
        <Icon className="h-8 w-8 text-muted-foreground" />
      </div>
    </div>
  );
}

function RecentMessage({ message }: { message: Message }) {
  return (
    <div className="flex items-start gap-3 py-3 border-b last:border-0">
      <Avatar 
        src={message.sender?.avatar_url} 
        name={message.sender?.display_name} 
        size="md" 
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">
            {message.sender?.display_name || "Unknown"}
          </span>
          {message.reply_to_sender && (
            <span className="text-xs text-muted-foreground">
              replied to {message.reply_to_sender.display_name}
            </span>
          )}
          <span className="text-xs text-muted-foreground ml-auto">
            {formatRelativeTime(message.timestamp)}
          </span>
        </div>
        <p className="text-sm text-muted-foreground truncate">
          {truncate(message.content || "", 100)}
        </p>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<Stats | null>(null);
  const [recent, setRecent] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const { currentRoom } = useRoom();

  useEffect(() => {
    async function load() {
      try {
        const roomId = currentRoom?.id;
        const [statsData, recentData] = await Promise.all([
          stats.get(roomId),
          stats.recent(10, roomId),
        ]);
        setData(statsData);
        setRecent(recentData);
      } catch (error) {
        console.error("Failed to load dashboard:", error);
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
        <h1 className="text-2xl font-bold">Dashboard</h1>

        {/* Stats cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard
            title="Messages"
            value={data?.total_messages || 0}
            icon={MessageSquare}
          />
          <StatCard
            title="Threads"
            value={data?.total_threads || 0}
            icon={GitBranch}
          />
          <StatCard
            title="People"
            value={data?.total_people || 0}
            icon={Users}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent Activity */}
          <div className="rounded-xl border bg-card p-6">
            <h2 className="text-lg font-semibold mb-4">Recent Activity</h2>
            <div className="space-y-1">
              {recent.length > 0 ? (
                recent.map((msg) => <RecentMessage key={msg.id} message={msg} />)
              ) : (
                <p className="text-sm text-muted-foreground">No messages yet</p>
              )}
            </div>
          </div>

          {/* Activity Graph */}
          <div className="rounded-xl border bg-card p-6">
            <h2 className="text-lg font-semibold mb-4">
              Activity (last 30 days)
            </h2>
            {data?.activity && data.activity.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={data.activity}>
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
                    labelFormatter={(value) =>
                      new Date(value).toLocaleDateString()
                    }
                  />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={2} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[250px]">
                <p className="text-sm text-muted-foreground">No activity data</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
