// Which line plays next. "Play" runs the dialogue from a line to the end, skipping lines with no
// audio; a line's own replay button plays that line alone. With "Repeat line" on, the line that
// just finished plays again, until it's turned off.
type HasAudio = { audio: boolean };

export function firstLine(lines: HasAudio[], from = 0): number | null {
  for (let i = Math.max(0, from); i < lines.length; i++) if (lines[i].audio) return i;
  return null;
}

export function nextLine(
  lines: HasAudio[],
  finished: number,
  playingAll: boolean,
  repeat = false,
): number | null {
  if (repeat) return finished;
  return playingAll ? firstLine(lines, finished + 1) : null;
}
