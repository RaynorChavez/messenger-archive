"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { rooms, type RoomListItem } from "@/lib/api";

interface RoomContextType {
  rooms: RoomListItem[];
  currentRoom: RoomListItem | null;
  setCurrentRoomId: (id: number) => void;
  isLoading: boolean;
}

const RoomContext = createContext<RoomContextType | undefined>(undefined);

export function RoomProvider({ children }: { children: ReactNode }) {
  const [roomList, setRoomList] = useState<RoomListItem[]>([]);
  const [currentRoomId, setCurrentRoomId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load rooms on mount
  useEffect(() => {
    async function loadRooms() {
      try {
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
      } finally {
        setIsLoading(false);
      }
    }
    loadRooms();
  }, []);

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
        isLoading,
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
