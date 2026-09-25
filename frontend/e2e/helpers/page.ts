import type { Page } from '@playwright/test'

// Abort every script request by RESOURCE TYPE, not URL glob. A glob on the
// build's assets path only matches a preview/production build's output; under
// the `chromium` project's dev server (`bun run dev`) the bundle is served as
// /src/main.tsx and /node_modules/.vite/deps/*.js, so that glob matches none of
// the ~90 requests a page load makes and React mounts while the test still
// passes. Filtering on resourceType() works for both URL shapes. With React
// never mounting, what the document did before first paint (the inline
// theme/accent script in index.html) is the only thing a test can measure.
export async function blockScripts(page: Page): Promise<void> {
  await page.route('**/*', (route) =>
    route.request().resourceType() === 'script' ? route.abort() : route.continue(),
  )
}
