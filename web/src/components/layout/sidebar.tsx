"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
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
  X,
  ChevronDown,
  Moon,
  Sun,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRoom } from "@/contexts/room-context";
import { useAuth } from "@/contexts/auth-context";
import { useSidebar } from "@/contexts/sidebar-context";
import { auth, Scope } from "@/lib/api";

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

// Define which nav items each scope can see
const scopeNavAccess: Record<Scope, string[]> = {
  admin: ["Dashboard", "Search", "Messages", "Threads", "Discussions", "Virtual Chat", "People", "Database", "Settings"],
  general: ["Dashboard", "Search", "Messages", "Threads", "Discussions", "Virtual Chat", "People", "Database"],
  immersion: ["Dashboard", "Search", "Messages", "Threads", "Discussions", "Virtual Chat", "People", "Database"],
};

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { currentRoom, rooms, setCurrentRoomId, isLoading } = useRoom();
  const { scope } = useAuth();
  const { close } = useSidebar();
  
  const [darkMode, setDarkMode] = useState(false);
  const [roomDropdownOpen, setRoomDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Dark mode initialization
  useEffect(() => {
    const stored = localStorage.getItem("darkMode");
    if (stored !== null) {
      setDarkMode(stored === "true");
    } else {
      setDarkMode(window.matchMedia("(prefers-color-scheme: dark)").matches);
    }
  }, []);

  // Apply dark mode
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    localStorage.setItem("darkMode", String(darkMode));
  }, [darkMode]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setRoomDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Get short room name
  const getShortName = (name: string | null | undefined) => {
    if (!name) return "Select Room";
    return name.replace(/ - Manila Dialectics Society$/, "").trim();
  };

  const roomName = getShortName(currentRoom?.name);

  // Filter navigation based on scope
  const visibleNav = scope
    ? navigation.filter((item) => scopeNavAccess[scope]?.includes(item.name))
    : navigation;

  const handleNavClick = () => {
    // Close sidebar on mobile when navigating
    close();
  };

  const handleRoomSelect = (roomId: number) => {
    setCurrentRoomId(roomId);
    setRoomDropdownOpen(false);
  };

  const handleLogout = async () => {
    try {
      await auth.logout();
      router.push("/login");
    } catch (error) {
      console.error("Logout failed:", error);
    }
  };

  return (
    <div className="flex h-full w-64 flex-col bg-card border-r">
      {/* Header with logo and close button */}
      <div className="flex h-16 items-center justify-between px-6 border-b">
        <h1 className="text-lg font-semibold">Messenger Archive</h1>
        <button
          onClick={close}
          className="flex items-center justify-center rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors md:hidden"
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Room Selector */}
      <div className="px-3 py-3 border-b" ref={dropdownRef}>
        <button
          onClick={() => setRoomDropdownOpen(!roomDropdownOpen)}
          className="flex w-full items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm font-medium hover:bg-accent transition-colors"
          disabled={isLoading}
        >
          <MessageSquare className="h-4 w-4 text-muted-foreground" />
          <span className="flex-1 text-left truncate">
            {isLoading ? "Loading..." : getShortName(currentRoom?.name)}
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform",
              roomDropdownOpen && "rotate-180"
            )}
          />
        </button>

        {roomDropdownOpen && rooms.length > 0 && (
          <div className="mt-1 rounded-lg border bg-card shadow-lg">
            <div className="p-1">
              {rooms.map((room) => (
                <button
                  key={room.id}
                  onClick={() => handleRoomSelect(room.id)}
                  className={cn(
                    "w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm text-left hover:bg-accent transition-colors",
                    currentRoom?.id === room.id && "bg-accent"
                  )}
                >
                  <MessageSquare className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{getShortName(room.name)}</div>
                    <div className="text-xs text-muted-foreground">
                      {room.message_count.toLocaleString()} messages
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Current Room Indicator */}
      {currentRoom && (
        <div className="px-4 py-3 border-b bg-muted/30">
          <div className="flex items-center gap-2 text-sm">
            <Hash className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium truncate">{roomName}</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 pl-6">
            {currentRoom.message_count?.toLocaleString()} messages
          </p>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
        {visibleNav.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));

          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={handleNavClick}
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

      {/* Footer with dark mode and logout */}
      <div className="border-t px-3 py-3 space-y-1">
        {/* Dark mode toggle */}
        <button
          onClick={() => setDarkMode(!darkMode)}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          {darkMode ? "Light Mode" : "Dark Mode"}
        </button>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <LogOut className="h-5 w-5" />
          Logout
        </button>
      </div>
    </div>
  );
}
