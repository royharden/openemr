import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/helpers'
import { LabResultsCard } from '@/components/cards/LabResultsCard'
import type { LabResultDisplay } from '@/models/dashboard'

vi.mock('@/fhir/queries/observations', () => ({
  getRecentLabResults: vi.fn(),
}))

import { getRecentLabResults } from '@/fhir/queries/observations'
const mockGetRecentLabResults = vi.mocked(getRecentLabResults)

const POTASSIUM_HIGH: LabResultDisplay = {
  id: 'obs-001',
  display: 'Potassium [Moles/volume] in Serum or Plasma',
  value: '5.9 mmol/L',
  unit: 'mmol/L',
  referenceRange: '3.5–5.1 mmol/L',
  effectiveDateTime: '2026-05-10T10:30:00Z',
  interpretation: 'high',
}

const HBA1C_NORMAL: LabResultDisplay = {
  id: 'obs-002',
  display: 'Hemoglobin A1c/Hemoglobin.total in Blood',
  value: '7.2 %',
  unit: '%',
  referenceRange: '< 7.0%',
  effectiveDateTime: '2026-05-09T08:15:00Z',
  interpretation: 'normal',
}

const HGB_LOW: LabResultDisplay = {
  id: 'obs-003',
  display: 'Hemoglobin [Mass/volume] in Blood',
  value: '10.8 g/dL',
  unit: 'g/dL',
  referenceRange: '12.0–16.0 g/dL',
  effectiveDateTime: '2026-05-08T14:00:00Z',
  interpretation: 'low',
}

describe('LabResultsCard component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton while fetching', () => {
    mockGetRecentLabResults.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)
    expect(screen.getByText(/loading lab results/i)).toBeInTheDocument()
  })

  it('renders lab result with display name and value', async () => {
    mockGetRecentLabResults.mockResolvedValue([POTASSIUM_HIGH])
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Potassium [Moles/volume] in Serum or Plasma')).toBeInTheDocument()
    })
    expect(screen.getByText('5.9 mmol/L')).toBeInTheDocument()
  })

  it('renders "H" badge for high interpretation', async () => {
    mockGetRecentLabResults.mockResolvedValue([POTASSIUM_HIGH])
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('H')).toBeInTheDocument()
    })
  })

  it('renders "L" badge for low interpretation', async () => {
    mockGetRecentLabResults.mockResolvedValue([HGB_LOW])
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('L')).toBeInTheDocument()
    })
  })

  it('does NOT render abnormal badge for normal results', async () => {
    mockGetRecentLabResults.mockResolvedValue([HBA1C_NORMAL])
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Hemoglobin A1c/Hemoglobin.total in Blood')).toBeInTheDocument()
    })
    expect(screen.queryByText('N')).not.toBeInTheDocument()
    expect(screen.queryByText('H')).not.toBeInTheDocument()
    expect(screen.queryByText('L')).not.toBeInTheDocument()
  })

  it('renders reference range', async () => {
    mockGetRecentLabResults.mockResolvedValue([POTASSIUM_HIGH])
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/3\.5–5\.1 mmol\/L/)).toBeInTheDocument()
    })
  })

  it('renders effective date (date part only)', async () => {
    mockGetRecentLabResults.mockResolvedValue([POTASSIUM_HIGH])
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('2026-05-10')).toBeInTheDocument()
    })
  })

  it('shows empty state when no lab results', async () => {
    mockGetRecentLabResults.mockResolvedValue([])
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/no recent lab results/i)).toBeInTheDocument()
    })
  })

  it('shows error state when query rejects', async () => {
    mockGetRecentLabResults.mockRejectedValue(new Error('FHIR error'))
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/failed to load lab results/i)).toBeInTheDocument()
    })
  })

  it('renders multiple results in order', async () => {
    mockGetRecentLabResults.mockResolvedValue([POTASSIUM_HIGH, HBA1C_NORMAL, HGB_LOW])
    renderWithProviders(<LabResultsCard patientId="patient-9001" />)

    await waitFor(() => {
      const items = screen.getAllByRole('listitem')
      expect(items).toHaveLength(3)
    })
  })
})
