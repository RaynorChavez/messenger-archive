"use client";

import { AppLayout } from "@/components/layout/app-layout";

export default function TopicsPage() {
  return (
    <AppLayout>
      <div className="flex flex-col items-center justify-center h-full">
        <div className="max-w-md text-center space-y-4">
          <div className="text-6xl">Coming Soon</div>
          <h1 className="text-2xl font-bold">Topics</h1>
          <p className="text-muted-foreground">
            AI-powered topic organization will automatically categorize your
            philosophical discussions.
          </p>
          <ul className="text-sm text-muted-foreground space-y-1">
            <li>- Ethics & Morality</li>
            <li>- Epistemology</li>
            <li>- Metaphysics</li>
            <li>- Political Philosophy</li>
            <li>- Philosophy of Mind</li>
            <li>- ...and more</li>
          </ul>
        </div>
      </div>
    </AppLayout>
  );
}
