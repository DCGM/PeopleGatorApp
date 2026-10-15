// Neutral, opaque surfaces for controls over a scan. Keep shared UI variants intact.
export const scanToolbarButtonClass = [
  'bg-background text-foreground hover:bg-muted hover:text-foreground',
  'dark:bg-background dark:hover:bg-muted',
  'aria-pressed:bg-muted dark:aria-pressed:bg-muted',
  'data-[state=on]:bg-muted data-[state=on]:text-foreground dark:data-[state=on]:bg-muted',
].join(' ')
