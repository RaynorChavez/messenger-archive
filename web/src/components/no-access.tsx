"use client";

import { ShieldX } from "lucide-react";

interface NoAccessProps {
  message?: string;
}

export function NoAccess({ message = "You don't have access to this feature" }: NoAccessProps) {
  return (
    <div className="flex items-center justify-center h-full min-h-[400px]">
      <div className="text-center">
        <ShieldX className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
        <h2 className="text-xl font-semibold">Access Denied</h2>
        <p className="text-muted-foreground mt-2">{message}</p>
      </div>
    </div>
  );
}
