import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import pngToIco from 'png-to-ico'
import sharp from 'sharp'

const root = resolve(import.meta.dirname, '..')
const publicDir = resolve(root, 'public')
const sourceSvg = await readFile(resolve(publicDir, 'peoplegator-icon.svg'), 'utf8')
const stylesheet = await readFile(resolve(root, 'src/style.css'), 'utf8')

function cssColor(name, selector = ':root') {
  const block = stylesheet.match(
    new RegExp(`${selector.replace('.', '\\.')}\\s*\\{([^}]*)}`, 'i'),
  )?.[1]
  const match = block?.match(new RegExp(`^\\s*--${name}:\\s*(#[0-9a-f]{6});`, 'im'))
  if (!match) throw new Error(`Missing --${name} color in src/style.css`)
  return match[1]
}

const colors = {
  background: cssColor('background'),
  primary: cssColor('primary'),
  accent: cssColor('accent'),
  darkPrimary: cssColor('primary', '.dark'),
}

function coloredSvg({ color, strokeWidth = 2 }) {
  return sourceSvg
    .replace('stroke="currentColor"', `stroke="${color}"`)
    .replaceAll('fill="currentColor"', `fill="${color}"`)
    .replace('stroke-width="2"', `stroke-width="${strokeWidth}"`)
}

async function renderIcon({ output, size, color, background, strokeWidth = 2, inset = 0 }) {
  const markSize = Math.round(size * (1 - inset * 2))
  const mark = await sharp(Buffer.from(coloredSvg({ color, strokeWidth })))
    .resize(markSize, markSize)
    .png()
    .toBuffer()

  await sharp({
    create: {
      width: size,
      height: size,
      channels: 4,
      background,
    },
  })
    .composite([{ input: mark, gravity: 'center' }])
    .png()
    .toFile(resolve(publicDir, output))
}

const icons = [
  { output: 'favicon-16x16.png', size: 16, color: colors.primary, background: colors.background },
  { output: 'favicon-32x32.png', size: 32, color: colors.primary, background: colors.background },
  {
    output: 'apple-touch-icon.png',
    size: 180,
    color: colors.background,
    background: colors.primary,
    inset: 0.18,
  },
  {
    output: 'icon-192.png',
    size: 192,
    color: colors.background,
    background: colors.primary,
    inset: 0.18,
  },
  {
    output: 'icon-512.png',
    size: 512,
    color: colors.background,
    background: colors.primary,
    inset: 0.18,
  },
  {
    output: 'icon-maskable-512.png',
    size: 512,
    color: colors.background,
    background: colors.accent,
    strokeWidth: 2.35,
    inset: 0.2,
  },
]

await Promise.all(icons.map(renderIcon))

const faviconStyles = `<style>
    :root { color: ${colors.primary}; }
    @media (prefers-color-scheme: dark) { :root { color: ${colors.darkPrimary}; } }
  </style>`
const faviconSvg = sourceSvg
  .replace('<svg', '<svg style="color-scheme: light dark"')
  .replace(/(<svg[^>]*>)/, `$1\n  ${faviconStyles}`)
await writeFile(resolve(publicDir, 'favicon.svg'), faviconSvg)

const faviconIco = await pngToIco([
  resolve(publicDir, 'favicon-16x16.png'),
  resolve(publicDir, 'favicon-32x32.png'),
])
await writeFile(resolve(publicDir, 'favicon.ico'), faviconIco)

console.log(`Generated ${icons.length + 2} icons from public/peoplegator-icon.svg`)
