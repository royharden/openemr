import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/helpers'
import { PatientHeader } from '@/components/PatientHeader'
import type { PatientHeaderData } from '@/models/dashboard'

vi.mock('@/fhir/queries/patient', () => ({
  getPatient: vi.fn(),
}))

import { getPatient } from '@/fhir/queries/patient'
const mockGetPatient = vi.mocked(getPatient)

const MARIA: PatientHeaderData = {
  id: 'patient-9001',
  fullName: 'Maria Elena Garcia',
  dateOfBirth: '1985-03-22',
  ageYears: 40,
  sex: 'female',
  mrn: 'MRN-9001',
  active: true,
}

describe('PatientHeader component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton while fetching', () => {
    mockGetPatient.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<PatientHeader patientId="patient-9001" />)
    expect(screen.getByText(/loading patient header/i)).toBeInTheDocument()
  })

  it('renders patient data when query resolves', async () => {
    mockGetPatient.mockResolvedValue(MARIA)
    renderWithProviders(<PatientHeader patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Maria Elena Garcia')).toBeInTheDocument()
    })
    expect(screen.getByText(/MRN-9001/)).toBeInTheDocument()
    expect(screen.getByText(/female/i)).toBeInTheDocument()
    expect(screen.getByText(/active/i)).toBeInTheDocument()
  })

  it('shows error state when query rejects', async () => {
    mockGetPatient.mockRejectedValue(new Error('Network error'))
    renderWithProviders(<PatientHeader patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/failed to load patient/i)).toBeInTheDocument()
    })
  })

  it('shows inactive badge for inactive patient', async () => {
    mockGetPatient.mockResolvedValue({ ...MARIA, active: false })
    renderWithProviders(<PatientHeader patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/inactive/i)).toBeInTheDocument()
    })
  })
})
