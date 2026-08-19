import React from "react";
import { cn } from "@/lib/utils";

const StageMetricsList = ({
  metrics,
  className,
  itemClassName = "flex items-center justify-between rounded-md border border-transparent px-2 py-1 hover:border-slate-200",
  labelClassName = "font-medium text-slate-500",
  valueClassName = "text-sm font-semibold text-slate-900",
}) => {
  if (!metrics?.length) return null;

  return (
    <div className={cn("space-y-1 text-xs text-slate-600", className)}>
      {metrics.map((metric) => (
        <div key={metric.label} className={itemClassName}>
          <span className={labelClassName}>{metric.label}</span>
          <span className={valueClassName}>
            {metric.value !== undefined && metric.value !== null 
              ? (typeof metric.value === 'number' ? metric.value : metric.value)
              : '—'}
          </span>
        </div>
      ))}
    </div>
  );
};

export default StageMetricsList;


