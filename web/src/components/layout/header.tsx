"use client";

import { Search, Menu } from "lucide-react";
import { useRouter } from "next/navigation";
import { useSidebar } from "@/contexts/sidebar-context";

export function Header() {
  const router = useRouter();
  const { open } = useSidebar();

  return (
    <header className="flex h-16 items-center gap-4 border-b bg-card px-4 md:px-6">
      {/* Hamburger menu - mobile only */}
      <button
        onClick={open}
        className="flex items-center justify-center rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors md:hidden"
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Search - full width on mobile, capped on desktop */}
      <div className="flex flex-1 items-center gap-2 rounded-lg border bg-background px-3 py-2 max-w-xl">
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
    </header>
  );
}
