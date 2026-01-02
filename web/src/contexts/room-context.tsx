"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { rooms, type RoomListItem } from "@/lib/api";
import { useAuth } from "./auth-context";

interface RoomContextType {
  rooms: RoomListItem[];
  currentRoom: RoomListItem | null;
  setCurrentRoomId: (id: number) => void;
  isLoading: boolean;
  refetch: () => Promise<void>;
}

const RoomContext = createContext<RoomContextType | undefined>(undefined);

export function RoomProvider({ children }: { children: ReactNode }) {
  const [roomList, setRoomList] = useState<RoomListItem[]>([]);
  const [currentRoomId, setCurrentRoomId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { scope, isLoading: authLoading } = useAuth();

  const loadRooms = useCallback(async () => {
    if (!scope) {
      // Not authenticated, clear rooms
      setRoomList([]);
      setCurrentRoomId(null);
      setIsLoading(false);
      return;
    }
    
    try {
      setIsLoading(true);
      const response = await rooms.list();
      setRoomList(response.rooms);
      
      // Set default room from localStorage or first room
      const savedRoomId = localStorage.getItem("currentRoomId");
      if (savedRoomId && response.rooms.some(r => r.id === Number(savedRoomId))) {
        setCurrentRoomId(Number(savedRoomId));
      } else if (response.rooms.length > 0) {
        setCurrentRoomId(response.rooms[0].id);
      }
    } catch (error) {
      console.error("Failed to load rooms:", error);
      setRoomList([]);
    } finally {
      setIsLoading(false);
    }
  }, [scope]);

  // Load rooms when auth is ready and scope changes
  useEffect(() => {
    if (!authLoading) {
      loadRooms();
    }
  }, [authLoading, loadRooms]);

  // Save current room to localStorage
  useEffect(() => {
    if (currentRoomId !== null) {
      localStorage.setItem("currentRoomId", String(currentRoomId));
    }
  }, [currentRoomId]);

  const currentRoom = roomList.find(r => r.id === currentRoomId) || null;

  return (
    <RoomContext.Provider
      value={{
        rooms: roomList,
        currentRoom,
        setCurrentRoomId,
        isLoading: isLoading || authLoading,
        refetch: loadRooms,
      }}
    >
      {children}
    </RoomContext.Provider>
  );
}

export function useRoom() {
  const context = useContext(RoomContext);
  if (context === undefined) {
    throw new Error("useRoom must be used within a RoomProvider");
  }
  return context;
}
