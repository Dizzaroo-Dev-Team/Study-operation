import * as React from "react"
import * as Primitive from "@radix-ui/react-scroll-area"

import { cn } from "@/lib/utils"

const ScrollArea = React.forwardRef((props, ref) => (
  <Primitive.Root
    ref={ref}
    className={cn("relative overflow-hidden", props.className)}
    {...props}
  >
    <Primitive.Viewport className="h-full w-full rounded-[inherit]" />
    <Primitive.Scrollbar
      orientation="vertical"
      className="flex h-full w-full flex-1"
    >
      {props.children}
    </Primitive.Scrollbar>
    <Primitive.Corner className="bg-border" />
  </Primitive.Root>
))
ScrollArea.displayName = Primitive.Root.displayName

export { ScrollArea }
