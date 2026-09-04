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
  http_request: [
    { key: 'url', label: 'URL', kind: 'string', default: 'https://httpbin.org/get' },
    { key: 'method', label: 'Method', kind: 'string', default: 'GET' },
    { key: 'timeout_seconds', label: 'Timeout (seconds)', kind: 'number', default: 10 },
  ],
  job_search: [
    { key: 'keyword', label: 'Keyword', kind: 'string', default: 'backend engineer' },
    { key: 'count', label: 'Count', kind: 'number', default: 3 },
  ],
  tailor_cv: [
    { key: 'title', label: 'Title', kind: 'string', default: '{{item.title}}' },
    { key: 'jd', label: 'JD', kind: 'string', default: '{{item.jd}}' },
  ],
  job_apply: [
    { key: 'job_id', label: 'Job ID', kind: 'string', default: '{{item.job_id}}' },
  ],
}

export function defaultPayload(taskType: string): Record<string, unknown> {
  const spec = PAYLOAD_SPECS[taskType] ?? []
  return Object.fromEntries(spec.map((f) => [f.key, f.default]))
}
