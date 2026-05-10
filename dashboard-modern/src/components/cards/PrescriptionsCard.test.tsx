import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/helpers'
import { PrescriptionsCard } from '@/components/cards/PrescriptionsCard'
import type { PrescriptionDisplay } from '@/models/dashboard'

vi.mock('@/fhir/queries/prescriptions', () => ({
  getActivePrescriptions: vi.fn(),
}))

import { getActivePrescriptions } from '@/fhir/queries/prescriptions'
const mockGetActivePrescriptions = vi.mocked(getActivePrescriptions)

const LISINOPRIL_RX: PrescriptionDisplay = {
  id: 'medreq-9001-rx-lisinopril',
  drug: 'Lisinopril 10 mg (Prescription)',
  sig: '10 mg once daily',
  status: 'active',
  authoredOn: '2024-01-10',
  prescriberName: 'Dr. Robert Williams',
}

describe('PrescriptionsCard component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton while fetching', () => {
    mockGetActivePrescriptions.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<PrescriptionsCard patientId="patient-9001" />)
    expect(screen.getByText(/loading prescriptions/i)).toBeInTheDocument()
  })

  it('renders active prescription with drug name, sig, and prescriber', async () => {
    mockGetActivePrescriptions.mockResolvedValue([LISINOPRIL_RX])
    renderWithProviders(<PrescriptionsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Lisinopril 10 mg (Prescription)')).toBeInTheDocument()
    })
    expect(screen.getByText('10 mg once daily')).toBeInTheDocument()
    expect(screen.getByText(/dr. robert williams/i)).toBeInTheDocument()
  })

  it('renders authored date', async () => {
    mockGetActivePrescriptions.mockResolvedValue([LISINOPRIL_RX])
    renderWithProviders(<PrescriptionsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/2024-01-10/)).toBeInTheDocument()
    })
  })

  it('shows empty state when no active prescriptions', async () => {
    mockGetActivePrescriptions.mockResolvedValue([])
    renderWithProviders(<PrescriptionsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/no active prescriptions/i)).toBeInTheDocument()
    })
  })

  it('shows error state when query rejects', async () => {
    mockGetActivePrescriptions.mockRejectedValue(new Error('FHIR error'))
    renderWithProviders(<PrescriptionsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/failed to load prescriptions/i)).toBeInTheDocument()
    })
  })

  it('does NOT render intent=plan medications (prescriptions-split regression)', async () => {
    mockGetActivePrescriptions.mockResolvedValue([LISINOPRIL_RX])
    renderWithProviders(<PrescriptionsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Lisinopril 10 mg (Prescription)')).toBeInTheDocument()
    })
    expect(screen.queryByText('Lisinopril 10 mg')).not.toBeInTheDocument()
  })

  it('renders multiple prescriptions', async () => {
    const rx2: PrescriptionDisplay = {
      id: 'rx-2',
      drug: 'Amoxicillin 500 mg',
      sig: '500 mg three times daily',
      status: 'active',
      authoredOn: '2024-03-05',
      prescriberName: null,
    }
    mockGetActivePrescriptions.mockResolvedValue([LISINOPRIL_RX, rx2])
    renderWithProviders(<PrescriptionsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Lisinopril 10 mg (Prescription)')).toBeInTheDocument()
      expect(screen.getByText('Amoxicillin 500 mg')).toBeInTheDocument()
    })
  })
})
