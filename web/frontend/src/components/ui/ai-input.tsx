"use client";

import { CornerRightUp, Mic } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Textarea } from "@/components/ui/textarea";
import { useAutoResizeTextarea } from "@/components/hooks/use-auto-resize-textarea";

interface AIInputProps {
  id?: string;
  placeholder?: string;
  minHeight?: number;
  maxHeight?: number;
  disabled?: boolean;
  onSubmit?: (value: string) => void;
  className?: string;
}

export function AIInput({
  id = "ai-input",
  placeholder = "Ask about European data...",
  minHeight = 52,
  maxHeight = 200,
  disabled = false,
  onSubmit,
  className,
}: AIInputProps) {
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight,
    maxHeight,
  });

  const [inputValue, setInputValue] = useState("");

  const handleSubmit = () => {
    const value = inputValue.trim();
    if (!value || disabled) return;

    onSubmit?.(value);
    setInputValue("");
    adjustHeight(true);
  };

  return (
    <div className={cn("w-full py-4", className)}>
      <div className="relative mx-auto w-full max-w-xl">
        <Textarea
          id={id}
          ref={textareaRef}
          value={inputValue}
          disabled={disabled}
          placeholder={placeholder}
          style={{ minHeight, maxHeight }}
          className={cn(
            "w-full resize-none overflow-y-auto rounded-3xl border-none",
            "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
            "bg-black/5 px-6 py-4 pr-16 text-black",
            "placeholder:text-black/50",
            "focus-visible:ring-0 focus-visible:ring-offset-0",
            "dark:bg-white/5 dark:text-white dark:placeholder:text-white/50",
            "transition-[height] duration-100 ease-out"
          )}
          onChange={(event) => {
            setInputValue(event.target.value);
            adjustHeight();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              handleSubmit();
            }
          }}
        />

        <div
          className={cn(
            "absolute top-1/2 -translate-y-1/2 rounded-xl",
            "bg-black/5 px-1 py-1 transition-all duration-200",
            "dark:bg-white/5",
            inputValue ? "right-10" : "right-3"
          )}
        >
          <Mic className="h-4 w-4 text-black/70 dark:text-white/70" />
        </div>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !inputValue.trim()}
          className={cn(
            "absolute right-3 top-1/2 -translate-y-1/2 rounded-xl",
            "bg-black/5 px-1 py-1 transition-all duration-200",
            "dark:bg-white/5",
            inputValue.trim()
              ? "scale-100 opacity-100"
              : "pointer-events-none scale-95 opacity-0"
          )}
          aria-label="Send message"
        >
          <CornerRightUp className="h-4 w-4 text-black/70 dark:text-white/70" />
        </button>
      </div>
    </div>
  );
}
