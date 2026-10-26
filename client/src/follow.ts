// Keeping the line being spoken on screen: where to scroll, or null when it's already in view.
// Lines are measured in the scroll view's content, so their `y` and the scroll offset compare.
export type Box = { y: number; height: number };

export function scrollTarget(line: Box, scrollY: number, viewHeight: number, margin = 16): number | null {
  const fits = line.y >= scrollY && line.y + line.height <= scrollY + viewHeight;
  return fits ? null : Math.max(0, line.y - margin);
}
