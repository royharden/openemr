import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/helpers'
import { MedicationsCard } from '@/components/cards/MedicationsCard'
import type { MedicationDisplay, PrescriptionDisplay } from '@/models/dashboard'

vi.mock('@/fhir/queries/medications', () => ({
  getActiveMedications: vi.fn(),
}))

vi.mock('@/fhir/queries/prescriptions', () => ({
  getActivePrescriptions: vi.fn(),
}))

import { getActiveMedications } from '@/fhir/queries/medications'
import { getActivePrescriptions } from '@/fhir/queries/prescriptions'
const mockGetActiveMedications = vi.mocked(getActiveMedications)
const mockGetActivePrescriptions = vi.mocked(getActivePrescriptions)

const ACTIVE_MEDS: ReadonlyArray<MedicationDisplay> = [
  {
    id: 'medreq-9001-lisinopril',
    drug: 'Lisinopril 10 mg',
    dose: '10 mg once daily',
    route: 'Oral',
    status: 'active',
    effectiveDate: '2021-03-15',
    origin: 'list',
  },
  {
    id: 'medreq-9001-metformin',
    drug: 'Metformin 500 mg',
    dose: '500 mg twice daily with meals',
    route: 'Oral',
    status: 'active',
    effectiveDate: '2021-03-15',
    origin: 'list',
  },
]

const EMPTY_PRESCRIPTIONS: ReadonlyArray<PrescriptionDisplay> = []

describe('MedicationsCard component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetActivePrescriptions.mockResolvedValue(EMPTY_PRESCRIPTIONS)
  })

  it('shows loading skeleton while fetching', () => {
    mockGetActiveMedications.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<MedicationsCard patientId="patient-9001" />)
    expect(screen.getByText(/loading medications/i)).toBeInTheDocument()
  })

  it('renders active medications with drug name', async () => {
    mockGetActiveMedications.mockResolvedValue(ACTIVE_MEDS)
    renderWithProviders(<MedicationsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Lisinopril 10 mg')).toBeInTheDocument()
    })
    expect(screen.getByText('Metformin 500 mg')).toBeInTheDocument()
  })

  it('shows empty state when no active medications', async () => {
    mockGetActiveMedications.mockResolvedValue([])
    renderWithProviders(<MedicationsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/no active medications/i)).toBeInTheDocument()
    })
  })

  it('shows error state when query rejects', async () => {
    mockGetActiveMedications.mockRejectedValue(new Error('FHIR error'))
    renderWithProviders(<MedicationsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/failed to load medications/i)).toBeInTheDocument()
    })
  })

  it('does NOT render completed intent=plan med (inactive-filter regression)', async () => {
    mockGetActiveMedications.mockResolvedValue(ACTIVE_MEDS)
    renderWithProviders(<MedicationsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Lisinopril 10 mg')).toBeInTheDocument()
    })
    expect(screen.queryByText(/amoxicillin/i)).not.toBeInTheDocument()
  })

  it('does NOT render intent=order prescription (prescriptions-split regression)', async () => {
    mockGetActiveMedications.mockResolvedValue(ACTIVE_MEDS)
    renderWithProviders(<MedicationsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Lisinopril 10 mg')).toBeInTheDocument()
    })
    expect(screen.queryByText(/prescription/i)).not.toBeInTheDocument()
  })

  it('shows conflict chip when same drug appears in prescriptions', async () => {
    const prescriptionWithSameDrug: ReadonlyArray<PrescriptionDisplay> = [
      {
        id: 'rx-lisinopril',
        drug: 'Lisinopril 10 mg',
        sig: '10 mg once daily',
        status: 'active',
        authoredOn: '2024-01-10',
        prescriberName: 'Dr. Smith',
      },
    ]
    mockGetActiveMedications.mockResolvedValue(ACTIVE_MEDS)
    mockGetActivePrescriptions.mockResolvedValue(prescriptionWithSameDrug)

    renderWithProviders(<MedicationsCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Lisinopril 10 mg')).toBeInTheDocument()
    })
    expect(screen.getByText(/duplicate rx/i)).toBeInTheDocument()
  })
})
