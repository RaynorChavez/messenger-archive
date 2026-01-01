"use client";

import { RoomProvider } from "@/contexts/room-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return <RoomProvider>{children}</RoomProvider>;
}
