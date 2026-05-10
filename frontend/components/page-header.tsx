import { type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  accent: string;
  iconBg: string;
  /** Optional content rendered to the right (e.g. action buttons). */
  trailing?: React.ReactNode;
};

export function PageHeader({ icon: Icon, title, subtitle, accent, iconBg, trailing }: Props) {
  return (
    <header className="relative pb-7 mb-8 animate-in">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3.5 min-w-0">
          <div
            className={cn(
              "w-10 h-10 rounded-xl grid place-items-center shrink-0 ring-1 ring-inset ring-white/5",
              iconBg,
            )}
          >
            <Icon size={18} className={accent} strokeWidth={2.2} />
          </div>
          <div className="min-w-0">
            <h1 className="text-[22px] sm:text-2xl font-semibold tracking-tight leading-tight">
              {title}
            </h1>
            <p className="text-text-secondary text-[13px] mt-0.5 leading-snug">
              {subtitle}
            </p>
          </div>
        </div>
        {trailing && <div className="flex items-center gap-2 shrink-0">{trailing}</div>}
      </div>

      {/* Subtle gradient divider */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-bg-borderHi to-transparent" />
    </header>
  );
}
