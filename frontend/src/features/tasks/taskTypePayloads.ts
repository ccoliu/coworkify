export interface PayloadFieldSpec {
  key: string
  label: string
  kind: 'string' | 'number' | 'boolean'
  default: string | number | boolean
}

export const PAYLOAD_SPECS: Record<string, PayloadFieldSpec[]> = {
  echo: [{ key: 'message', label: 'Message', kind: 'string', default: 'hello' }],
  heavy_computation: [
    { key: 'duration_seconds', label: 'Duration (seconds)', kind: 'number', default: 5 },
  ],
  flaky_task: [
    { key: 'should_fail', label: 'Should fail', kind: 'boolean', default: false },
  ],
}

export function defaultPayload(taskType: string): Record<string, unknown> {
  const spec = PAYLOAD_SPECS[taskType] ?? []
  return Object.fromEntries(spec.map((f) => [f.key, f.default]))
}
