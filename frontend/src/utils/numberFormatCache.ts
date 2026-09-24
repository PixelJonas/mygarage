/**
 * One cache of `Intl.NumberFormat` instances, shared by every module that
 * formats a number.
 *
 * Constructing a formatter resolves the locale's number data and is the
 * expensive half of formatting; calling `.format` on it is the cheap half. The
 * formatting entry points here run once per rendered quantity, so before this
 * existed a vehicle list or a pack preview built and discarded a formatter per
 * number on screen.
 *
 * ★ IT IMPORTS NOTHING, AND THAT IS THE POINT. This started as a private helper
 * inside `unitFormat.ts`, which cannot be shared: `unitFormat` imports
 * `unitAdapters`, which imports `units`, so `units.ts` reaching back for it
 * would close a cycle. A leaf module with no imports can be depended on by all
 * of them.
 *
 * ★ THE KEY MUST NAME EVERYTHING THE OUTPUT DEPENDS ON, and the locale is the
 * one that is easy to forget. `getActiveLocale()` changes when the reader picks
 * a language, so a key without it would answer the first language's formatter
 * forever and separators would silently stop following the setting.
 * `localeFormatting.test.ts` is the guard for that.
 *
 * Callers pass the key rather than having it derived from the options, so no
 * serialization runs on the hot path. Write the key on the line above the
 * options it stands for, so the two cannot drift apart unseen, and never key on
 * something the options do not use or two callers will fight over one entry.
 *
 * ★ WHEN THE RESULT IS SMALL, CACHE THE RESULT INSTEAD. Two callers correctly do
 * not use this: `currency.getCurrencySymbol` caches the resolved symbol string,
 * and `decimalInput.localeDecimalSeparator` caches the one separator character.
 * Both build a formatter only to read a fragment out of it, so caching the
 * fragment is strictly cheaper than caching the machine that produced it.
 */

const formatters = new Map<string, Intl.NumberFormat>()

/**
 * The `Intl.NumberFormat` for `key`, constructed at most once.
 *
 * @param key Everything the formatter's output depends on, locale included.
 * @param make Builds the formatter on a miss. Anything it throws propagates and
 *   nothing is cached, so a caller guarding an invalid currency code with
 *   try/catch keeps behaving exactly as it did without the cache.
 * @returns The cached or newly built formatter.
 */
export function cachedNumberFormat(
  key: string,
  make: () => Intl.NumberFormat
): Intl.NumberFormat {
  let formatter = formatters.get(key)
  if (formatter === undefined) {
    // Bounded by the languages, precisions and currencies actually in use (a
    // handful of each), so there is nothing to evict.
    formatter = make()
    formatters.set(key, formatter)
  }
  return formatter
}

/**
 * A currency formatter at a fixed number of decimals.
 *
 * ★ IT EXISTS SO THE KEY CANNOT DISAGREE WITH THE OPTIONS. Three call sites want
 * this exact shape, and each spelled its own key beside its own option block.
 * Two of them landed on `locale|cost|currency` while reading their precision
 * from two SEPARATE constants that happen to both be 2 today: the day either
 * moved, one module would silently serve the other's decimals, and which one
 * depends on the order they first ran. Building the key from the same arguments
 * that build the options makes that unrepresentable.
 *
 * @param locale The reader's locale.
 * @param currencyCode ISO code. An invalid one throws from `Intl`, uncached, so
 *   a caller that catches keeps its fallback.
 * @param digits Both the minimum and maximum fraction digits.
 * @returns The cached or newly built formatter.
 */
export function cachedCurrencyFormat(
  locale: string,
  currencyCode: string,
  digits: number
): Intl.NumberFormat {
  return cachedNumberFormat(
    `${locale}|currency|${currencyCode}|${digits}`,
    () =>
      new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currencyCode,
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
  )
}
