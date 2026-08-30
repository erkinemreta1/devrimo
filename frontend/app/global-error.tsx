"use client";

import { useEffect } from "react";
import { captureError } from "@/components/posthog-analytics";

/**
 * The last resort: an error thrown by the root layout itself.
 *
 * Replaces the whole document, so it must render its own `html` and `body` and
 * cannot rely on any provider — including the theme — being mounted. Styles are
 * inline for the same reason.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    captureError(error, { source: "global_error_boundary", digest: error.digest ?? null });
  }, [error]);

  return (
    <html lang="tr">
      <body
        style={{
          display: "flex",
          minHeight: "100vh",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "1rem",
          padding: "1.5rem",
          textAlign: "center",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <div>
          <p style={{ fontWeight: 500 }}>Devrimo açılamadı</p>
          <p style={{ marginTop: "0.25rem", fontSize: "0.875rem", opacity: 0.7 }}>
            Beklenmeyen bir hata oluştu. Sayfayı yenilemeyi dene.
          </p>
        </div>
        <button
          onClick={reset}
          style={{
            borderRadius: "0.5rem",
            border: "1px solid currentColor",
            padding: "0.5rem 1rem",
            fontSize: "0.875rem",
            cursor: "pointer",
            background: "transparent",
            color: "inherit",
          }}
        >
          Tekrar dene
        </button>
      </body>
    </html>
  );
}
