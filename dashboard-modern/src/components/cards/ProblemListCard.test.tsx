import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/helpers'
import { ProblemListCard } from '@/components/cards/ProblemListCard'
import type { ProblemDisplay } from '@/models/dashboard'

vi.mock('@/fhir/queries/conditions', () => ({
  getActiveProblems: vi.fn(),
}))

import { getActiveProblems } from '@/fhir/queries/conditions'
const mockGetActiveProblems = vi.mocked(getActiveProblems)

const ACTIVE_PROBLEMS: ReadonlyArray<ProblemDisplay> = [
  {
    id: 'condition-9001-htn',
    display: 'Hypertension',
    code: 'I10',
    codeSystem: 'http://hl7.org/fhir/sid/icd-10-cm',
    clinicalStatus: 'active',
    onset: '2018-04-01',
    recordedDate: '2018-04-01',
  },
  {
    id: 'condition-9001-t2dm',
    display: 'Type 2 Diabetes Mellitus',
    code: 'E11.9',
    codeSystem: 'http://hl7.org/fhir/sid/icd-10-cm',
    clinicalStatus: 'active',
    onset: '2019-08-15',
    recordedDate: '2019-08-15',
  },
]

describe('ProblemListCard component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton while fetching', () => {
    mockGetActiveProblems.mockReturnValue(new Promise(() => {}))
    renderWithProviders(<ProblemListCard patientId="patient-9001" />)
    expect(screen.getByText(/loading problems/i)).toBeInTheDocument()
  })

  it('renders active problems', async () => {
    mockGetActiveProblems.mockResolvedValue(ACTIVE_PROBLEMS)
    renderWithProviders(<ProblemListCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Hypertension')).toBeInTheDocument()
    })
    expect(screen.getByText('Type 2 Diabetes Mellitus')).toBeInTheDocument()
  })

  it('shows empty state when no active problems', async () => {
    mockGetActiveProblems.mockResolvedValue([])
    renderWithProviders(<ProblemListCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/no active problems/i)).toBeInTheDocument()
    })
  })

  it('shows error state when query rejects', async () => {
    mockGetActiveProblems.mockRejectedValue(new Error('FHIR error'))
    renderWithProviders(<ProblemListCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText(/failed to load problem list/i)).toBeInTheDocument()
    })
  })

  it('does NOT render the resolved UTI condition (inactive-filter regression)', async () => {
    mockGetActiveProblems.mockResolvedValue(ACTIVE_PROBLEMS)
    renderWithProviders(<ProblemListCard patientId="patient-9001" />)

    await waitFor(() => {
      expect(screen.getByText('Hypertension')).toBeInTheDocument()
    })
    expect(screen.queryByText(/urinary tract infection/i)).not.toBeInTheDocument()
  })

  it('renders onset date for problems that have one', async () => {
    mockGetActiveProblems.mockResolvedValue(ACTIVE_PROBLEMS)
    renderWithProviders(<ProblemListCard patientId="patient-9001" />)

    await waitFor(() => {
      const onsetElements = screen.getAllByText(/onset/i)
      expect(onsetElements.length).toBeGreaterThanOrEqual(1)
    })
  })
})
