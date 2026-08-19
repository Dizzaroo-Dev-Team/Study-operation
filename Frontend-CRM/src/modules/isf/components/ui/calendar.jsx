import * as React from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { DayPicker } from "react-day-picker"

import { cn } from "@/lib/utils"

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn("p-4 bg-white", className)}
      classNames={{
        months: "flex flex-col sm:flex-row space-y-6 sm:space-x-8 sm:space-y-0",
        month: "space-y-4",
        caption: "flex justify-center pt-2 pb-4 relative items-center mb-2",
        caption_label: "text-base font-semibold text-slate-900 tracking-tight",
        nav: "space-x-1 flex items-center",
        nav_button: cn(
          "h-8 w-8 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 hover:border-slate-300 transition-all duration-200 flex items-center justify-center text-slate-600 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 disabled:opacity-30 disabled:cursor-not-allowed"
        ),
        nav_button_previous: "absolute left-0",
        nav_button_next: "absolute right-0",
        table: "w-full border-collapse",
        head_row: "flex mb-2",
        head_cell:
          "text-slate-500 rounded-md w-10 h-8 font-medium text-xs uppercase tracking-wider text-center flex items-center justify-center",
        row: "flex w-full mb-1",
        cell: cn(
          "relative p-0 text-center text-sm focus-within:relative focus-within:z-20 h-10 w-10",
          props.mode === "range"
            ? "[&:has(>.day-range-end)]:rounded-r-lg [&:has(>.day-range-start)]:rounded-l-lg first:[&:has([aria-selected])]:rounded-l-lg last:[&:has([aria-selected])]:rounded-r-lg"
            : "[&:has([aria-selected])]:rounded-lg"
        ),
        day: cn(
          "h-10 w-10 p-0 font-medium text-sm rounded-lg transition-all duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-1 aria-selected:opacity-100"
        ),
        day_range_start: "day-range-start rounded-l-lg",
        day_range_end: "day-range-end rounded-r-lg",
        day_selected:
          "bg-[hsl(var(--dz-primary))] text-white hover:bg-[hsl(var(--dz-primary-hover))] hover:text-white focus:bg-[hsl(var(--dz-primary))] focus:text-white font-semibold shadow-sm",
        day_today: "bg-slate-100 text-slate-900 font-semibold border-2 border-slate-300",
        day_outside:
          "day-outside text-slate-400 aria-selected:bg-slate-50 aria-selected:text-slate-400 aria-selected:opacity-50",
        day_disabled: "text-slate-300 opacity-40 cursor-not-allowed hover:bg-transparent",
        day_range_middle:
          "aria-selected:bg-slate-100 aria-selected:text-slate-900",
        ...classNames,
      }}
      components={{
        IconLeft: ({ ...props }) => <ChevronLeft className="h-4 w-4" />,
        IconRight: ({ ...props }) => <ChevronRight className="h-4 w-4" />,
      }}
      {...props}
    />
  )
}
Calendar.displayName = "Calendar"

export { Calendar }
