"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  MessageCircle,
  GitBranch,
  Users,
  Settings,
  Database,
  Sparkles,
  Search,
  Hash,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRoom } from "@/contexts/room-context";

const navigation = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Search", href: "/search", icon: Search },
  { name: "Messages", href: "/messages", icon: MessageSquare },
  { name: "Threads", href: "/threads", icon: GitBranch },
  { name: "Discussions", href: "/discussions", icon: Sparkles },
  { name: "Virtual Chat", href: "/virtual-chat", icon: MessageCircle },
  { name: "People", href: "/people", icon: Users },
  { name: "Database", href: "/database", icon: Database },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { currentRoom } = useRoom();

  // Get short room name (remove common suffixes)
  const getShortName = (name: string | null | undefined) => {
    if (!name) return null;
    return name.replace(/ - Manila Dialectics Society$/, "").trim();
  };

  const roomName = getShortName(currentRoom?.name);

  return (
    <div className="flex h-full w-64 flex-col bg-card border-r">
      {/* Logo */}
      <div className="flex h-16 items-center px-6 border-b">
        <h1 className="text-lg font-semibold">Messenger Archive</h1>
      </div>

      {/* Current Room Indicator */}
      {roomName && (
        <div className="px-4 py-3 border-b bg-muted/30">
          <div className="flex items-center gap-2 text-sm">
            <Hash className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium truncate">{roomName}</span>
          </div>
          {currentRoom && (
            <p className="text-xs text-muted-foreground mt-1 pl-6">
              {currentRoom.message_count?.toLocaleString()} messages
            </p>
          )}
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));

          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.name}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
