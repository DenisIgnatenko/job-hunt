const STATUS_COLORS: Record<string, string> = {
  new:                'badge-blue',
  in_progress:        'badge-yellow',
  letter_sent:        'badge-purple',
  applied:            'badge-orange',
  interview:          'badge-teal',
  offer:              'badge-green',
  rejected:           'badge-red',
  rejected_by_company:'badge-red',
  // events
  interested:         'badge-teal',
  attending:          'badge-purple',
  attended:           'badge-green',
  skipped:            'badge-red',
}

const PLATFORM_COLORS: Record<string, string> = {
  jobindex:  'badge-blue',
  linkedin:  'badge-purple',
  remotive:  'badge-teal',
  thehub:    'badge-orange',
  unknown:   'badge-gray',
}

const FORMAT_COLORS: Record<string, string> = {
  remote:  'badge-green',
  hybrid:  'badge-yellow',
  onsite:  'badge-orange',
  unknown: 'badge-gray',
}

interface Props {
  value: string
  type?: 'status' | 'platform' | 'format'
}

export default function StatusBadge({ value, type = 'status' }: Props) {
  const map = type === 'platform' ? PLATFORM_COLORS
            : type === 'format'   ? FORMAT_COLORS
            : STATUS_COLORS
  const cls = map[value] ?? 'badge-gray'
  return <span className={`badge ${cls}`}>{value.replace(/_/g, ' ')}</span>
}
