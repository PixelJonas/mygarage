/**
 * How an integrations tab's status reads, shared by the card's tab strip and
 * the per-source settings drawers.
 *
 * Moved out of LiveLinkIntegrationsCard so a drawer states a tab's status in
 * the same words the card does, from the same table.
 */

/** Green, yellow, red, and nothing else: the operator ruled out a grey
 *  "unconfigured" state, so not-set-up reads as red. An unknown status also
 *  reads as red, never green, matching `derive_broker_status`. */
export const DOT_TONE: Record<string, 'success' | 'warning' | 'danger'> = {
  ok: 'success',
  attention: 'warning',
  off: 'danger',
}

/** Written as literal keys so `validate-i18n-usage` can see them. A computed
 *  key would be invisible to the scanner and could ship as a raw string. */
export const STATUS_KEY: Record<string, string> = {
  receiving: 'integrations.statusReceiving',
  firmware_update: 'integrations.statusFirmwareUpdate',
  not_linked: 'integrations.statusNotLinked',
  no_data: 'integrations.statusNoData',
  broker_down: 'integrations.statusBrokerDown',
  disabled: 'integrations.statusDisabled',
  not_configured: 'integrations.statusNotConfigured',
}
