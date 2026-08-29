"use client";

import { unstable_useComposerInput } from "@assistant-ui/react";
import { BrandMark } from "@/components/brand-mark";
import { STARTER_PROMPTS } from "@/lib/campus";
import { Button } from "@/components/ui/button";

export function MetuWelcome() {
  return (
    <div className="mb-8 flex flex-col items-center px-4 text-center">
      <BrandMark className="mb-4 size-11 text-sm" />
      <p className="text-xs font-medium tracking-[0.18em] text-primary uppercase">
        For METU students
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
        What do you need on campus?
      </h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Devrimo can use campus MCPs — ODTÜClass, catalog, calendar, library, and
        maps — to answer with your real university context.
      </p>
    </div>
  );
}

export function MetuStarterPrompts() {
  const { setText, send, isDisabled } = unstable_useComposerInput();

  return (
    <div className="flex w-full flex-wrap items-center justify-center gap-2 px-1 pb-1">
      {STARTER_PROMPTS.map((prompt) => (
        <Button
          key={prompt}
          type="button"
          variant="outline"
          disabled={isDisabled}
          className="h-auto max-w-full rounded-full px-3.5 py-1.5 text-left text-sm font-normal whitespace-normal"
          onClick={() => {
            setText(prompt);
            send();
          }}
        >
          {prompt}
        </Button>
      ))}
    </div>
  );
}
