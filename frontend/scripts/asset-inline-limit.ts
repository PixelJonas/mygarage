/**
 * `build.assetsInlineLimit` callback: fonts are never base64-inlined.
 *
 * Vite inlines any asset under 4 KiB as a `data:` URL. The JetBrains Mono
 * cyrillic-ext subset is ~2 KiB, so it was embedded in the main stylesheet and
 * the backend's `font-src 'self'` CSP refused it on every page load. Font
 * files, however small, stay files: fingerprinted under /assets, allowed by
 * 'self', and precached by the service worker (inject-sw-font-assets.ts only
 * sees emitted files). Everything else keeps Vite's size rule: `undefined`
 * means "apply the default logic".
 */
const FONT_FILE = /\.(woff2?|ttf|otf|eot)$/i

export function neverInlineFonts(filePath: string): boolean | undefined {
  return FONT_FILE.test(filePath) ? false : undefined
}
