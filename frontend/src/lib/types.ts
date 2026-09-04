export type TaskStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'retrying'
  | 'cancelled'

export interface Task {
  id: string
  name: string
  task_type: string
  payload: Record<string, unknown>
  status: TaskStatus
  priority: number
  max_retries: number
  retry_count: number
  scheduled_at: string | null
  runner_id: string | null
  created_at: string
  updated_at: string
}

export interface TaskCreate {
  name: string
  task_type: string
  payload: Record<string, unknown>
  priority: number
  max_retries: number
  scheduled_at?: string | null
  runner_id?: string | null
}

export interface TaskListFilters {
  status?: TaskStatus | ''
  task_type?: string
  limit: number
  offset: number
}

export const TASK_TYPES = [
  'echo',
  'heavy_computation',
  'flaky_task',
  'http_request',
  'job_search',
  'tailor_cv',
  'job_apply',
] as const
export type TaskType = (typeof TASK_TYPES)[number]

export const TASK_STATUSES: TaskStatus[] = [
  'pending',
  'running',
  'retrying',
  'success',
  'failed',
  'cancelled',
]

export interface WsTaskUpdate {
  task_id: string
  status: TaskStatus
  result: unknown
  error: string | null
  timestamp: number
}

export type WorkflowStatus = 'pending' | 'success' | 'failed'

export interface WorkflowStep {
  id: string
  task_id: string
  depends_on: string[]
  task_status: TaskStatus | null
  task_name: string | null
  task_type: string | null
  task_runner_id: string | null
}

export interface Workflow {
  id: string
  name: string
  status: WorkflowStatus
  created_at: string
  updated_at: string
  steps: WorkflowStep[]
}

export interface WorkflowStepCreate {
  key: string
  name: string
  task_type: string
  payload: Record<string, unknown>
  priority: number
  max_retries: number
  depends_on: string[]
  for_each?: string | null
  runner_id?: string | null
}

export interface WorkflowCreate {
  name: string
  steps: WorkflowStepCreate[]
}

export interface User {
  id: string
  username: string
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface WorkflowSchedule {
  id: string
  name: string
  cron_expression: string
  steps: WorkflowStepCreate[]
  enabled: boolean
  next_run_at: string | null
  last_run_at: string | null
  created_at: string
  updated_at: string
}

export interface WorkflowScheduleCreate {
  name: string
  cron_expression: string
  steps: WorkflowStepCreate[]
  enabled: boolean
}

export interface Runner {
  id: string
  name: string
  last_seen_at: string | null
  created_at: string
}

export interface RunnerCreated extends Runner {
  token: string
}

export interface WorkflowScheduleUpdate {
  name?: string
  cron_expression?: string
  steps?: WorkflowStepCreate[]
  enabled?: boolean
}
