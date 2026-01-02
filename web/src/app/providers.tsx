"use client";

import { RoomProvider } from "@/contexts/room-context";
import { AuthProvider } from "@/contexts/auth-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <RoomProvider>{children}</RoomProvider>
    </AuthProvider>
  );
}
