import React from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const ComplianceTagList = ({
  tags,
  className,
  badgeClassName = "rounded-full border-slate-200 bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600",
}) => {
  if (!tags?.length) return null;

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {tags.map((tag) => (
        <Badge key={tag} className={badgeClassName}>
          {tag}
        </Badge>
      ))}
    </div>
  );
};

export default ComplianceTagList;


