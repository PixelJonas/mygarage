/**
 * A question asked in place, under the control that raised it: a heading, the
 * consequence, Cancel and a confirming action. Quick Settings uses it because
 * a drawer is no place for a full-screen overlay; the settings page's unit
 * editor shows the same body inside its overlay.
 */

import { useTranslation } from 'react-i18next'
import { Button } from '../ui'

export interface InlineConfirmProps {
  /** Id for the heading, which labels the group. */
  id: string
  title: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
  /** The consequence being confirmed. */
  children: React.ReactNode
  /** Replaces the in-place box (the page overlay's panel supplies its own). */
  className?: string
  /** `md` for a dialog panel: a larger heading and full-size buttons. */
  size?: 'sm' | 'md'
}

export default function InlineConfirm({
  id,
  title,
  confirmLabel,
  onConfirm,
  onCancel,
  children,
  className = 'mt-3 space-y-3 rounded-lg border border-garage-border bg-garage-bg p-3',
  size = 'sm',
}: InlineConfirmProps): React.ReactElement {
  const { t } = useTranslation()
  return (
    <div role="group" aria-labelledby={id} className={className}>
      <h3 id={id} className={`font-semibold text-garage-text ${size === 'sm' ? 'text-sm' : 'text-lg'}`}>
        {title}
      </h3>
      {children}
      <div className="flex gap-3 justify-end">
        <Button type="button" variant="secondary" size={size} onClick={onCancel}>
          {t('common:cancel')}
        </Button>
        <Button type="button" size={size} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </div>
  )
}
