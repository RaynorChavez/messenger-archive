"use client";

import { useState } from "react";
import { mxcToHttp } from "@/lib/api";
import { cn } from "@/lib/utils";

interface AvatarProps {
  src?: string | null;
  name?: string | null;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

const sizeClasses = {
  sm: "h-6 w-6 text-xs",
  md: "h-8 w-8 text-sm",
  lg: "h-10 w-10 text-base",
  xl: "h-16 w-16 text-xl",
};

export function Avatar({ src, name, size = "md", className }: AvatarProps) {
  const [hasError, setHasError] = useState(false);
  const avatarUrl = mxcToHttp(src);
  const initials = name?.[0]?.toUpperCase() || "?";
  
  const showImage = avatarUrl && !hasError;

  return (
    <div className={cn("relative flex-shrink-0", className)}>
      {showImage ? (
        <img
          src={avatarUrl}
          alt={name || ""}
          className={cn(
            "rounded-full object-cover bg-muted",
            sizeClasses[size]
          )}
          onError={() => setHasError(true)}
        />
      ) : (
        <div
          className={cn(
            "rounded-full bg-muted flex items-center justify-center font-medium text-muted-foreground",
            sizeClasses[size]
          )}
        >
          {initials}
        </div>
      )}
    </div>
  );
}
