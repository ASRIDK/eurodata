/* eslint-disable @next/next/no-img-element -- tiny remote CDN flags; next/image
   needs remotePatterns config and fixed dims for no benefit at this size */
import { cn } from "@/lib/utils";
import { countryName, flagUrl } from "@/lib/flags";

/** Real flag image for an ISO-3 code or country name; renders nothing if unknown. */
export function Flag({ code, className }: { code: unknown; className?: string }) {
  const url = flagUrl(code);
  if (!url) return null;
  return (
    <img
      src={url}
      srcSet={`${flagUrl(code, 80)} 2x`}
      alt=""
      className={cn("inline-block h-3.5 w-auto rounded-[2px] shadow-sm", className)}
    />
  );
}

/** Flag + display name: "FRA" or "France" -> [🏳 img] France. Unknown values render as plain text. */
export function FlagName({ value }: { value: unknown }) {
  const name = countryName(value);
  if (!name) return <>{String(value)}</>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <Flag code={value} />
      {name}
    </span>
  );
}
