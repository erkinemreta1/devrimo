"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { captureError } from "@/components/posthog-analytics";

/**
 * The route-level error boundary the app has never had.
 *
 * Without this, a render error blanks the page and leaves no record anywhere.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    captureError(error, { source: "route_error_boundary", digest: error.digest ?? null });
  }, [error]);

  return (
    <div role="alert" className="flex h-full min-h-svh flex-col items-center justify-center gap-4 px-6 text-center">
      <div>
        <p className="font-medium">Bir şeyler ters gitti</p>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          Bu sayfa yüklenemedi. Tekrar denemek sorunu genellikle çözer.
        </p>
      </div>
      <Button onClick={reset}>Tekrar dene</Button>
    </div>
  );
}
