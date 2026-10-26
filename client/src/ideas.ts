// Topic ideas a few at a time; "More ideas" moves to the next few and wraps back to the start.
export const IDEAS_SHOWN = 6;

export function ideaPage<T>(ideas: T[], page: number, size = IDEAS_SHOWN): T[] {
  if (ideas.length === 0) return [];
  const pages = Math.ceil(ideas.length / size);
  const start = (((page % pages) + pages) % pages) * size;
  return ideas.slice(start, start + size);
}
