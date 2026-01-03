"use client";

import { RoomProvider } from "@/contexts/room-context";
import { AuthProvider } from "@/contexts/auth-context";
import { SidebarProvider } from "@/contexts/sidebar-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <RoomProvider>
        <SidebarProvider>{children}</SidebarProvider>
      </RoomProvider>
    </AuthProvider>
  );
}
