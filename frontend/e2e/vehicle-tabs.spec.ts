import { test, expect } from './helpers/fixtures'
import { TEST_VEHICLE } from './helpers/selectors'

/**
 * Vehicle detail tab navigation tests.
 *
 * Verifies that each primary tab and its sub-tabs load without errors.
 * Uses the seeded TEST_VEHICLE from global.setup.ts.
 */
test.describe('Vehicle Detail — Tab Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/vehicles/${TEST_VEHICLE.vin}`)
    await expect(
      page.getByRole('heading', { name: TEST_VEHICLE.nickname })
    ).toBeVisible({ timeout: 15000 })
  })

  test('Overview tab loads by default with vehicle info', async ({ page }) => {
    // Overview is the default active tab
    const overviewTab = page.getByRole('tab', { name: 'Overview' })
    await expect(overviewTab).toBeVisible()
    await expect(overviewTab).toHaveAttribute('aria-selected', 'true')

    // ★ BY HEADING ROLE, not by text. Each editable card now also holds a
    // focus-revealed "Edit <section>" button (issue #179), so a loose text
    // query for 'Basic Information' matches the card title AND that button's
    // label and trips strict mode. The role query says what this case actually
    // means: the card is on screen.
    await expect(
      page.getByRole('heading', { name: 'Basic Information' })
    ).toBeVisible({ timeout: 5000 })
    // Purchase + MSRP were folded into one "Pricing" card.
    await expect(page.getByRole('heading', { name: 'Pricing', exact: true })).toBeVisible()
  })

  test('Media tab — cycles through sub-tabs', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.getByRole('tab', { name: 'Media' }).click()

    // Each sub-tab body renders a stable English heading (verified in en/vehicles.json): PhotoGallery's
    // <h3> "Photo Gallery" (photoGallery.misc.title) and DocumentList's <h3> "Documents"
    // (documentList.title). Body-level render proof, not just "no toast". exact:true disambiguates each
    // from its own EmptyState fallback title (e.g. Documents vs "No documents yet"), which the freshly
    // seeded zero-record test vehicle renders — without exact, getByRole('heading',{name}) resolves 2
    // nodes and throws a strict-mode violation.
    const bodyHeading: Record<string, string> = {
      Photos: 'Photo Gallery',
      Documents: 'Documents',
    }
    const subTabs = ['Photos', 'Documents']
    for (const tabName of subTabs) {
      // M6: Media's Photos/Documents sub-tabs are UNCONDITIONAL (VehicleDetail.tsx subTabsConfig.media —
      // neither carries a `visible` gate), so assert each is present rather than silently skipping via
      // `if (await tab.isVisible())` — a removed/renamed/delayed tab must FAIL, not pass by omission.
      const tab = page.getByRole('tab', { name: tabName })
      await expect(tab).toBeVisible({ timeout: 5000 })
      await tab.click()
      await expect(page.getByRole('heading', { name: bodyHeading[tabName], exact: true })).toBeVisible({ timeout: 5000 })
      await expect(page.locator('[data-sonner-toast][data-type="error"]')).not.toBeVisible({ timeout: 2000 })
    }

    expect(pageErrors, pageErrors.join('\n')).toEqual([])
  })

  test('Maintenance tab — cycles through sub-tabs', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.getByRole('tab', { name: 'Maintenance' }).click()

    // Default sub-tab should be Service
    const serviceTab = page.getByRole('tab', { name: 'Service' })
    await expect(serviceTab).toBeVisible({ timeout: 5000 })

    // Each sub-tab body renders a stable heading — the English serviceList/
    // odometerList/recallList `.title` (verified in en/vehicles.json). This is a
    // body-level render proof, not just "no toast". (`Tabs` emits no role=tabpanel,
    // so anchor on the heading, not a panel role.)
    const bodyHeading: Record<string, string> = {
      Service: 'Service History',
      Odometer: 'Odometer Readings',
      Recalls: 'Safety Recalls',
    }
    const subTabs = ['Service', 'Odometer', 'Recalls']
    for (const tabName of subTabs) {
      // Service and Recalls are unconditional; Odometer is isMotorized-gated and the seeded
      // TEST_VEHICLE is a Car (motorized), so all three are present. Assert visibility rather
      // than skipping via `if (await tab.isVisible())` — a removed/renamed sub-tab must FAIL.
      const tab = page.getByRole('tab', { name: tabName })
      await expect(tab).toBeVisible({ timeout: 5000 })
      await tab.click()
      // The body actually rendered (survives loading), not an empty fallback:
      await expect(page.getByRole('heading', { name: bodyHeading[tabName] })).toBeVisible({ timeout: 5000 })
      // ...and no error toast.
      await expect(page.locator('[data-sonner-toast][data-type="error"]')).not.toBeVisible({ timeout: 2000 })
    }

    // No uncaught page error surfaced during the whole cycle.
    expect(pageErrors, pageErrors.join('\n')).toEqual([])
  })

  test('Fuel tab — loads fuel/DEF/propane sub-tabs', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    // Primary "Fuel" tab and the "Fuel" sub-tab share a name — scope the primary
    // click to the primary tablist to avoid a strict-mode collision.
    const primaryTabs = page.getByRole('tablist', { name: 'Vehicle sections' })
    await primaryTabs.getByRole('tab', { name: 'Fuel', exact: true }).click()

    // Fuel sub-tab is isMotorized-gated; the seeded TEST_VEHICLE is a Car (motorized),
    // so it is present and its body renders.
    await expect(page.getByText('Fuel History')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('[data-sonner-toast][data-type="error"]')).not.toBeVisible({ timeout: 2000 })

    // DEF / Propane are fuel-type-gated (hasDEF / hasPropane) and SubTabNav omits gated
    // sub-tabs from the DOM entirely (Tabs.tsx filters visible !== false). The seeded Car is
    // neither diesel nor propane-equipped, so both sub-tabs must be ABSENT — a positive proof
    // the gating holds, rather than an `if (isVisible)` no-op that skips silently.
    await expect(page.getByRole('tab', { name: 'DEF', exact: true })).toHaveCount(0)
    await expect(page.getByRole('tab', { name: 'Propane', exact: true })).toHaveCount(0)

    // No uncaught page error surfaced during the whole cycle.
    expect(pageErrors, pageErrors.join('\n')).toEqual([])
  })

  test('Tracking tab — cycles through sub-tabs', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.getByRole('tab', { name: 'Tracking' }).click()

    // Notes is the default; Reminders + Reports are the others. Each body renders a stable English heading
    // (NoteList <h3> "Notes" / ReminderList <h3> "Reminders" from en/vehicles.json; ReportsPanel <h2>
    // "Reports & Export" from en/analytics.json). exact:true disambiguates each from its own EmptyState
    // fallback title ("No notes yet" / "No pending reminders"), which the freshly seeded zero-record test
    // vehicle renders — without exact, getByRole('heading',{name}) resolves 2 nodes (strict-mode violation).
    const bodyHeading: Record<string, string> = {
      Notes: 'Notes',
      Reminders: 'Reminders',
      Reports: 'Reports & Export',
    }
    const subTabs = ['Notes', 'Reminders', 'Reports']
    for (const tabName of subTabs) {
      // M6: Tracking's Notes/Reminders/Reports sub-tabs are UNCONDITIONAL (VehicleDetail.tsx
      // subTabsConfig.tracking — none carries a `visible` gate), so assert each is present rather than
      // silently skipping via `if (await tab.isVisible())` — the newly-added Reminders cycle would
      // otherwise be defeated the moment it regressed.
      const tab = page.getByRole('tab', { name: tabName })
      await expect(tab).toBeVisible({ timeout: 5000 })
      await tab.click()
      await expect(page.getByRole('heading', { name: bodyHeading[tabName], exact: true })).toBeVisible({ timeout: 5000 })
      await expect(page.locator('[data-sonner-toast][data-type="error"]')).not.toBeVisible({ timeout: 2000 })
    }

    expect(pageErrors, pageErrors.join('\n')).toEqual([])
  })

  test('Financial tab — cycles through sub-tabs', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.getByRole('tab', { name: 'Financial' }).click()

    // Each Financial sub-tab body renders a stable English heading (verified in
    // en/vehicles.json + en/common.json). Body-level render proof, not just "no toast".
    // Warranties, Insurance, Tax & Registration, Tolls, Supplies are unconditional; Spot
    // Rentals is isRVOrFifthWheel-gated. The seeded TEST_VEHICLE is a Car, so the five
    // always-present tabs must render and Spot Rentals must be ABSENT.
    const bodyHeading: Record<string, string> = {
      Warranties: 'Warranties',
      Insurance: 'Insurance Policies',
      'Tax & Registration': 'Tax & Registration Records',
      Tolls: 'Toll Tags',
      Supplies: 'Supplies Used',
    }
    const subTabs = ['Warranties', 'Insurance', 'Tax & Registration', 'Tolls', 'Supplies']
    for (const tabName of subTabs) {
      const tab = page.getByRole('tab', { name: tabName })
      await expect(tab).toBeVisible({ timeout: 5000 })
      await tab.click()
      // The body actually rendered (survives loading), not an empty fallback. exact: true
      // disambiguates from each body's own EmptyState fallback title, which — for a
      // freshly seeded test vehicle with zero records in every Financial category —
      // case-insensitively contains the tab title as a substring (e.g. Warranties'
      // "Warranties" section heading vs its EmptyState "No warranties recorded yet";
      // same for Insurance/"Insurance Policies" and Tolls/"Toll Tags"). Without exact,
      // getByRole('heading', { name }) resolves to 2 elements and throws a strict-mode
      // violation — a locator ambiguity, not an empty-fallback failure.
      await expect(page.getByRole('heading', { name: bodyHeading[tabName], exact: true })).toBeVisible({ timeout: 5000 })
      // ...and no error toast.
      await expect(page.locator('[data-sonner-toast][data-type="error"]')).not.toBeVisible({ timeout: 2000 })
    }

    // Spot Rentals only shows for RV / fifth-wheel / travel-trailer vehicles; the seeded Car
    // must not expose it (SubTabNav omits gated sub-tabs from the DOM).
    await expect(page.getByRole('tab', { name: 'Spot Rentals', exact: true })).toHaveCount(0)

    // No uncaught page error surfaced during the whole cycle.
    expect(pageErrors, pageErrors.join('\n')).toEqual([])
  })

  test('switching between primary tabs preserves page stability', async ({ page }) => {
    const primaryTabs = ['Media', 'Maintenance', 'Fuel', 'Tracking', 'Financial', 'Overview']

    for (const tabName of primaryTabs) {
      await page.getByRole('tab', { name: tabName }).click()
      // Each tab switch should not cause a page crash or error
      await page.waitForTimeout(300)
      // The vehicle nickname should still be visible in the header
      await expect(
        page.getByRole('heading', { name: TEST_VEHICLE.nickname })
      ).toBeVisible()
    }
  })

  test('navigates to vehicle detail via URL tab parameter', async ({ page }) => {
    // Navigate with ?tab=fuel to go directly to the Fuel tab
    await page.goto(`/vehicles/${TEST_VEHICLE.vin}?tab=fuel`)
    await expect(
      page.getByRole('heading', { name: TEST_VEHICLE.nickname })
    ).toBeVisible({ timeout: 15000 })

    // Fuel sub-tab should be active
    await expect(page.getByText('Fuel History')).toBeVisible({ timeout: 10000 })
  })

  test('navigates to vehicle detail via URL tab=insurance', async ({ page }) => {
    await page.goto(`/vehicles/${TEST_VEHICLE.vin}?tab=insurance`)
    await expect(
      page.getByRole('heading', { name: TEST_VEHICLE.nickname })
    ).toBeVisible({ timeout: 15000 })

    // Insurance sub-tab should be active under Financial
    const insuranceTab = page.getByRole('tab', { name: 'Insurance' })
    await expect(insuranceTab).toBeVisible({ timeout: 5000 })
    await expect(insuranceTab).toHaveAttribute('aria-selected', 'true')
  })
})
