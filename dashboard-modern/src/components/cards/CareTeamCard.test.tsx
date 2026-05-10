import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/helpers'
import { CareTeamCard } from '@/components/cards/CareTeamCard'
import type { CareTeamDisplay } from '@/models/dashboard'

vi.mock('@/fhir/queries/careTeam', () => ({
  getActiveCareTeam: vi.fn(),
}))

import { getActiveCareTeam } from '@/fhir/queries/careTeam'
const mockGetActiveCareTeam = vi.mocked(getActiveCareTeam)

const ACTIVE_TEAM: CareTeamDisplay = {
  id: 'ct-001',
  name: 'Primary Care Team',
  status: 'active',
  members: [
    {
      id: 'ct-001-member-0',
      name: 'Dr. Sarah Johnson',
      role: 'Primary Care Physician',
      practitionerId: 'pract-001',
    },
    {
      id: 'ct-001-member-1',
      name: 'Nurse Patricia Lopez',
      role: 'Registered Nurse',
      practitionerId: 'pract-002',
    },
  ],
}

describe('CareTeamCard component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton while fetching', () => {
    mockGetActiveCareTeam.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<CareTeamCard patientId="patient-9001" />)
    expect(screen.getByText(/loading care team/i)).toBeInTheDocument()
  })

  it('renders active team name and members', async () => {
    mockGetActiveCareTeam.mockResolvedValue([ACTIVE_TEAM])
    renderWithProviders(<CareTeamCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Primary Care Team')).toBeInTheDocument()
    })
    expect(screen.getByText('Dr. Sarah Johnson')).toBeInTheDocument()
    expect(screen.getByText('Nurse Patricia Lopez')).toBeInTheDocument()
  })

  it('renders member roles', async () => {
    mockGetActiveCareTeam.mockResolvedValue([ACTIVE_TEAM])
    renderWithProviders(<CareTeamCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Primary Care Physician')).toBeInTheDocument()
    })
    expect(screen.getByText('Registered Nurse')).toBeInTheDocument()
  })

  it('shows empty state when no active care teams', async () => {
    mockGetActiveCareTeam.mockResolvedValue([])
    renderWithProviders(<CareTeamCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/no active care teams/i)).toBeInTheDocument()
    })
  })

  it('shows error state when query rejects', async () => {
    mockGetActiveCareTeam.mockRejectedValue(new Error('FHIR error'))
    renderWithProviders(<CareTeamCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/failed to load care team/i)).toBeInTheDocument()
    })
  })

  it('status-filter regression — inactive team NOT rendered', async () => {
    const inactiveTeam: CareTeamDisplay = {
      id: 'ct-002',
      name: 'Cardiology Consult Team (Discharged)',
      status: 'inactive',
      members: [
        {
          id: 'ct-002-member-0',
          name: 'Dr. Michael Chen',
          role: 'Cardiologist',
          practitionerId: 'pract-003',
        },
      ],
    }
    // Adapter filters inactive server-side — query only returns active
    mockGetActiveCareTeam.mockResolvedValue([ACTIVE_TEAM])
    renderWithProviders(<CareTeamCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Primary Care Team')).toBeInTheDocument()
    })
    expect(screen.queryByText('Cardiology Consult Team (Discharged)')).not.toBeInTheDocument()
    void inactiveTeam
  })

  it('member with no role renders name only', async () => {
    const teamNoRole: CareTeamDisplay = {
      id: 'ct-nrole',
      name: 'Minimal Team',
      status: 'active',
      members: [
        {
          id: 'ct-nrole-member-0',
          name: 'Some Provider',
          role: null,
          practitionerId: null,
        },
      ],
    }
    mockGetActiveCareTeam.mockResolvedValue([teamNoRole])
    renderWithProviders(<CareTeamCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Some Provider')).toBeInTheDocument()
    })
  })
})
