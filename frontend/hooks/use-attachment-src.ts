"use client";

import { useEffect, useState } from "react";
import { useAuiState } from "@assistant-ui/react";

const useFileSrc = (file: File | undefined) => {
  const [entry, setEntry] = useState<{ file: File; url: string } | undefined>(
    undefined,
  );

  useEffect(() => {
    let active = true;
    if (!file) {
      queueMicrotask(() => {
        if (active) setEntry(undefined);
      });
      return () => {
        active = false;
      };
    }

    const objectUrl = URL.createObjectURL(file);
    queueMicrotask(() => {
      if (active) setEntry({ file, url: objectUrl });
    });

    return () => {
      active = false;
      URL.revokeObjectURL(objectUrl);
    };
  }, [file]);

  return entry !== undefined && entry.file === file ? entry.url : undefined;
};

export const useAttachmentSrc = () => {
  const file = useAuiState((state) =>
    state.attachment.type === "image" ? state.attachment.file : undefined,
  );
  const src = useAuiState((state) => {
    if (state.attachment.type !== "image" || state.attachment.file) return undefined;
    return state.attachment.content?.find((item) => item.type === "image")?.image;
  });

  return useFileSrc(file) ?? src;
};
