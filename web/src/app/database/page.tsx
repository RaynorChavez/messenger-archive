"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/app-layout";
import { database, type TableResponse } from "@/lib/api";

type TableName = "messages" | "people" | "rooms" | "discussions" | "discussion_messages" | "topics" | "discussion_topics";

const tableColumns: Record<TableName, string[]> = {
  messages: ["id", "matrix_event_id", "room_id", "sender_id", "content", "reply_to_message_id", "timestamp", "created_at"],
  people: ["id", "matrix_user_id", "display_name", "avatar_url", "notes", "created_at", "updated_at"],
  rooms: ["id", "matrix_room_id", "name", "is_group", "created_at"],
  discussions: ["id", "analysis_run_id", "title", "summary", "started_at", "ended_at", "message_count", "participant_count"],
  discussion_messages: ["discussion_id", "message_id", "confidence"],
  topics: ["id", "name", "description", "color", "created_at"],
  discussion_topics: ["discussion_id", "topic_id"],
};

function getColumnsForTable(table: TableName): string[] {
  return tableColumns[table];
}

export default function DatabasePage() {
  const [activeTable, setActiveTable] = useState<TableName>("messages");
  const [data, setData] = useState<TableResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const result = await database[activeTable](page, 25);
        setData(result);
      } catch (error) {
        console.error("Failed to load table:", error);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [activeTable, page]);

  // Reset page when switching tables
  useEffect(() => {
    setPage(1);
  }, [activeTable]);

  const columns = data?.rows[0] ? Object.keys(data.rows[0]) : [];

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Raw Database</h1>
        </div>

        {/* Table selector */}
        <div className="flex gap-2 flex-wrap">
          {(["messages", "people", "rooms", "discussions", "discussion_messages", "topics", "discussion_topics"] as TableName[]).map((table) => (
            <button
              key={table}
              onClick={() => setActiveTable(table)}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                activeTable === table
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted hover:bg-muted/80"
              }`}
            >
              {table}
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="rounded-xl border bg-card overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">
              Loading...
            </div>
          ) : data?.rows.length === 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    {getColumnsForTable(activeTable).map((col) => (
                      <th
                        key={col}
                        className="px-4 py-3 text-left font-medium text-muted-foreground"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td
                      colSpan={getColumnsForTable(activeTable).length}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      No data in {activeTable} table
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    {columns.map((col) => (
                      <th
                        key={col}
                        className="px-4 py-3 text-left font-medium text-muted-foreground"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data?.rows.map((row, i) => (
                    <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                      {columns.map((col) => (
                        <td key={col} className="px-4 py-3 max-w-xs truncate">
                          {row[col] === null ? (
                            <span className="text-muted-foreground italic">null</span>
                          ) : typeof row[col] === "boolean" ? (
                            row[col] ? "true" : "false"
                          ) : (
                            String(row[col])
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
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
              Page {page} of {data.total_pages} ({data.total} rows)
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

        {/* Total count */}
        {data && (
          <div className="text-sm text-muted-foreground text-center">
            Total: {data.total} rows
          </div>
        )}
      </div>
    </AppLayout>
  );
}
