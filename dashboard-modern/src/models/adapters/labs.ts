import type { Observation } from '@/fhir/schemas/observation'
import type { LabInterpretation, LabResultDisplay } from '@/models/dashboard'

function toInterpretation(obs: Observation): LabInterpretation {
  const code = obs.interpretation?.[0]?.coding?.[0]?.code
  switch (code) {
    case 'H':
    case 'HH':
      return code === 'HH' ? 'critical-high' : 'high'
    case 'L':
    case 'LL':
      return code === 'LL' ? 'critical-low' : 'low'
    case 'N':
      return 'normal'
    case 'A':
      return 'abnormal'
    default:
      return code != null ? 'abnormal' : 'unknown'
  }
}

function formatValue(obs: Observation): string | null {
  const vq = obs.valueQuantity
  if (vq != null) {
    const num = vq.value != null ? String(vq.value) : null
    const unit = vq.unit ?? null
    if (num == null) return null
    return unit != null ? `${num} ${unit}` : num
  }
  if (obs.valueString != null) return obs.valueString
  const cc = obs.valueCodeableConcept
  if (cc != null) return cc.text ?? cc.coding?.[0]?.display ?? null
  return null
}

function formatReferenceRange(obs: Observation): string | null {
  const rr = obs.referenceRange?.[0]
  if (rr == null) return null
  if (rr.text != null) return rr.text
  const low = rr.low?.value
  const high = rr.high?.value
  const unit = rr.low?.unit ?? rr.high?.unit ?? ''
  if (low != null && high != null) return `${low}–${high} ${unit}`.trim()
  if (low != null) return `≥ ${low} ${unit}`.trim()
  if (high != null) return `≤ ${high} ${unit}`.trim()
  return null
}

function getEffective(obs: Observation): string | null {
  return obs.effectiveDateTime ?? obs.effectivePeriod?.start ?? null
}

function getDisplay(obs: Observation): string {
  const code = obs.code
  if (code == null) return obs.id
  return code.text ?? code.coding?.[0]?.display ?? code.coding?.[0]?.code ?? obs.id
}

export function adaptLabs(
  resources: ReadonlyArray<Observation>,
  n: number,
): ReadonlyArray<LabResultDisplay> {
  const sorted = [...resources].sort((a, b) => {
    const ta = getEffective(a) ?? ''
    const tb = getEffective(b) ?? ''
    return tb.localeCompare(ta)
  })

  return sorted.slice(0, n).map((obs) => ({
    id: obs.id,
    display: getDisplay(obs),
    value: formatValue(obs),
    unit: obs.valueQuantity?.unit ?? null,
    referenceRange: formatReferenceRange(obs),
    effectiveDateTime: getEffective(obs),
    interpretation: toInterpretation(obs),
  }))
}
