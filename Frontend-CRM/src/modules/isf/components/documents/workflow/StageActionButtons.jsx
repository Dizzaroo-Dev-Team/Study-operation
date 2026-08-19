import React from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const StageActionButtons = ({
  actions = {},
  layout = "vertical",
  onPrimary,
  onSecondary,
  onTertiary,
  disabled = false,
  className,
}) => {
  const items = [actions?.primary, actions?.secondary, actions?.tertiary].filter(Boolean);
  if (!items.length) return null;

  const isHorizontal = layout === "horizontal";

  return (
    <div className={cn(isHorizontal ? "flex gap-2" : "flex flex-col gap-2", className)}>
      {items.map((action, index) => {
        const isPrimary = index === 0;
        const isSecondary = index === 1;
        const isTertiary = index === 2;
        const clickHandler = isPrimary ? onPrimary : isSecondary ? onSecondary : onTertiary;
        const variant = isPrimary ? "default" : "outline";
        const defaultLabel = isPrimary ? "Open Stage" : isSecondary ? "View Resources" : "Additional Action";

        return (
          <Button
            key={action?.label ?? index}
            size="sm"
            variant={variant}
            className={cn(
              "flex items-center justify-center gap-2",
              isPrimary
                ? "bg-sky-600 text-white hover:bg-sky-600/90"
                : isTertiary
                ? "border-slate-300 text-slate-700 hover:bg-slate-100 bg-slate-50"
                : "border-slate-200 text-slate-600 hover:bg-slate-100"
            )}
            onClick={clickHandler}
            disabled={disabled || !clickHandler}
          >
            {action?.icon ? <action.icon className="h-4 w-4" /> : null}
            {action?.label || defaultLabel}
          </Button>
        );
      })}
    </div>
  );
};

export default StageActionButtons;


