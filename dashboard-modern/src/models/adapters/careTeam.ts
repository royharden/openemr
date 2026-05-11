import type { CareTeam } from '@/fhir/schemas/careTeam'
import type { CareTeamDisplay, CareTeamMember } from '@/models/dashboard'

function toCareTeamStatus(status: string | undefined): CareTeamDisplay['status'] {
  const allowed = [
    'active',
    'inactive',
    'proposed',
    'suspended',
    'entered-in-error',
  ] as const
  type S = (typeof allowed)[number]
  return allowed.includes(status as S) ? (status as S) : 'unknown'
}

function resolveRole(
  roles: Array<{ coding?: Array<{ display?: string }>, text?: string }> | undefined,
): string | null {
  if (roles == null || roles.length === 0) return null
  const first = roles[0]
  if (first == null) return null
  return first.text ?? first.coding?.[0]?.display ?? null
}

function buildMembers(
  resource: CareTeam,
  practitionerNamesById: ReadonlyMap<string, string>,
): ReadonlyArray<CareTeamMember> {
  const participants = resource.participant ?? []
  return participants.map((p, idx) => {
    const ref = p.member?.reference ?? null
    let practitionerId: string | null = null
    let name: string | null = p.member?.display ?? null

    if (ref != null) {
      practitionerId = ref.startsWith('Practitioner/')
        ? ref.slice('Practitioner/'.length)
        : ref
      const resolved = practitionerNamesById.get(practitionerId)
      if (resolved != null) name = resolved
    }

    return {
      id: `${resource.id}-member-${idx}`,
      name,
      role: resolveRole(p.role),
      practitionerId,
    }
  })
}

export function adaptCareTeam(
  resources: ReadonlyArray<CareTeam>,
  practitionerNamesById: ReadonlyMap<string, string>,
): ReadonlyArray<CareTeamDisplay> {
  return resources
    .filter((r) => r.status === 'active')
    .map((r) => ({
      id: r.id,
      name: r.name ?? null,
      status: toCareTeamStatus(r.status),
      members: buildMembers(r, practitionerNamesById),
    }))
}
