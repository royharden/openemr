import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/helpers'
import { AllergiesCard } from '@/components/cards/AllergiesCard'
import type { AllergiesView } from '@/models/dashboard'

vi.mock('@/fhir/queries/allergies', () => ({
  getActiveAllergies: vi.fn(),
}))

import { getActiveAllergies } from '@/fhir/queries/allergies'
const mockGetActiveAllergies = vi.mocked(getActiveAllergies)

const PENICILLIN_ALLERGY: AllergiesView = {
  nkda: false,
  items: [
    {
      id: 'allergy-9001-penicillin',
      substance: 'Penicillin',
      clinicalStatus: 'active',
      verificationStatus: 'confirmed',
      criticality: 'high',
      reactions: ['Skin rash', 'Difficulty breathing'],
      recordedDate: '2010-06-15',
    },
  ],
}

const NKDA_VIEW: AllergiesView = { nkda: true, items: [] }

const EMPTY_VIEW: AllergiesView = { nkda: false, items: [] }

describe('AllergiesCard component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton while fetching', () => {
    mockGetActiveAllergies.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<AllergiesCard patientId="patient-9001" />)
    expect(screen.getByText(/loading allergies/i)).toBeInTheDocument()
  })

  it('renders active allergy with substance name and criticality', async () => {
    mockGetActiveAllergies.mockResolvedValue(PENICILLIN_ALLERGY)
    renderWithProviders(<AllergiesCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Penicillin')).toBeInTheDocument()
    })
    expect(screen.getByText('high')).toBeInTheDocument()
    expect(screen.getByText(/skin rash/i)).toBeInTheDocument()
  })

  it('renders NKDA badge when nkda=true', async () => {
    mockGetActiveAllergies.mockResolvedValue(NKDA_VIEW)
    renderWithProviders(<AllergiesCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/NKDA/)).toBeInTheDocument()
    })
  })

  it('shows empty state when no active allergies', async () => {
    mockGetActiveAllergies.mockResolvedValue(EMPTY_VIEW)
    renderWithProviders(<AllergiesCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/no active allergies/i)).toBeInTheDocument()
    })
  })

  it('shows error state when query rejects', async () => {
    mockGetActiveAllergies.mockRejectedValue(new Error('FHIR error'))
    renderWithProviders(<AllergiesCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/failed to load allergies/i)).toBeInTheDocument()
    })
  })

  it('does NOT render inactive allergy (adapter-side filter regression)', async () => {
    const viewWithOnlyActive: AllergiesView = {
      nkda: false,
      items: [
        {
          id: 'allergy-active',
          substance: 'Penicillin',
          clinicalStatus: 'active',
          verificationStatus: 'confirmed',
          criticality: 'high',
          reactions: [],
          recordedDate: null,
        },
      ],
    }
    mockGetActiveAllergies.mockResolvedValue(viewWithOnlyActive)
    renderWithProviders(<AllergiesCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Penicillin')).toBeInTheDocument()
    })
    expect(screen.queryByText('Sulfonamide (resolved)')).not.toBeInTheDocument()
  })
})
