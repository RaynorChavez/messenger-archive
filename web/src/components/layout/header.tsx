"use client";

import { Search, LogOut, Moon, Sun, ChevronDown, MessageSquare } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import { auth } from "@/lib/api";
import { useRoom } from "@/contexts/room-context";

export function Header() {
  const router = useRouter();
  const [darkMode, setDarkMode] = useState(false);
  const [roomDropdownOpen, setRoomDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const { rooms, currentRoom, setCurrentRoomId, isLoading } = useRoom();

  useEffect(() => {
    // Check localStorage or system preference on mount
    const stored = localStorage.getItem("darkMode");
    if (stored !== null) {
      setDarkMode(stored === "true");
    } else {
      setDarkMode(window.matchMedia("(prefers-color-scheme: dark)").matches);
    }
  }, []);

  useEffect(() => {
    // Apply dark mode class to html element
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

  const handleLogout = async () => {
    try {
      await auth.logout();
      router.push("/login");
    } catch (error) {
      console.error("Logout failed:", error);
    }
  };

  const handleRoomSelect = (roomId: number) => {
    setCurrentRoomId(roomId);
    setRoomDropdownOpen(false);
  };

  // Get short room name (remove common suffixes)
  const getShortName = (name: string | null | undefined) => {
    if (!name) return "Select Room";
    return name.replace(/ - Manila Dialectics Society$/, "").trim();
  };

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      {/* Left side - Room selector and Search */}
      <div className="flex items-center gap-4">
        {/* Room Selector Dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setRoomDropdownOpen(!roomDropdownOpen)}
            className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm font-medium hover:bg-accent transition-colors min-w-[180px]"
            disabled={isLoading}
          >
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
            <span className="flex-1 text-left truncate">
              {isLoading ? "Loading..." : getShortName(currentRoom?.name)}
            </span>
            <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${roomDropdownOpen ? "rotate-180" : ""}`} />
          </button>

          {roomDropdownOpen && rooms.length > 0 && (
            <div className="absolute top-full left-0 mt-1 w-72 rounded-lg border bg-card shadow-lg z-50">
              <div className="p-1">
                {rooms.map((room) => (
                  <button
                    key={room.id}
                    onClick={() => handleRoomSelect(room.id)}
                    className={`w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm text-left hover:bg-accent transition-colors ${
                      currentRoom?.id === room.id ? "bg-accent" : ""
                    }`}
                  >
                    <MessageSquare className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{getShortName(room.name)}</div>
                      <div className="text-xs text-muted-foreground">
                        {room.message_count.toLocaleString()} messages · {room.member_count} members
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Search */}
        <div className="flex items-center gap-2 rounded-lg border bg-background px-3 py-2 w-80">
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
      </div>

      {/* Right side actions */}
      <div className="flex items-center gap-2">
        {/* Dark mode toggle */}
        <button
          onClick={() => setDarkMode(!darkMode)}
          className="flex items-center justify-center rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
        >
          {darkMode ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </header>
  );
}
