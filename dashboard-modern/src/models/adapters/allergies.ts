import type { AllergyIntolerance } from '@/fhir/schemas/allergyIntolerance'
import type { AllergiesView } from '@/models/dashboard'

/**
 * LOCKED SIGNATURE — Workstream B implements the body.
 *
 * Adapts an array of Zod-parsed AllergyIntolerance resources to the
 * AllergiesView. CANONICAL implementation of clinical-status filtering:
 * filters in JS (not server-side) on
 *   resource.clinicalStatus.coding[*].code === 'active'.
 *
 * NKDA: if the only entry has code matching SNOMED 716186003 ("No
 * known drug allergies"), set view.nkda=true and items=[].
 */
export function adaptAllergies(
  _resources: ReadonlyArray<AllergyIntolerance>,
): AllergiesView {
  throw new Error('adaptAllergies(): not implemented — Workstream B')
}
