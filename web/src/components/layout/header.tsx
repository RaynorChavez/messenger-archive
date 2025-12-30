"use client";

import { Search, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/api";

export function Header() {
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await auth.logout();
      router.push("/login");
    } catch (error) {
      console.error("Logout failed:", error);
    }
  };

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      {/* Search */}
      <div className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 w-96">
        <Search className="h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search messages..."
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          onKeyDown={(e) => {
            if (e.key === "Enter" && e.currentTarget.value) {
              router.push(`/search?q=${encodeURIComponent(e.currentTarget.value)}`);
            }
          }}
        />
      </div>

      {/* User menu */}
      <button
        onClick={handleLogout}
        className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
      >
        <LogOut className="h-4 w-4" />
        Logout
      </button>
    </header>
  );
}
