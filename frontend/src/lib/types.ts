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
}

export interface TaskListFilters {
  status?: TaskStatus | ''
  task_type?: string
  limit: number
  offset: number
}

export type TaskFieldKind = 'string' | 'number' | 'boolean' | 'text' | 'select' | 'multiselect' | 'code'

export interface TaskFieldOption {
  value: string
  label: string
}

export interface TaskFieldSpec {
  key: string
  label: string
  kind: TaskFieldKind
  default: string | number | boolean | string[] | null
  required: boolean
  help?: string | null
  options?: TaskFieldOption[] | null
  upload_accept?: string | null
  // kind === 'code' 時的語法標記，目前支援 'python' / 'json'
  language?: string | null
}

export interface TaskTypeSpec {
  task_type: string
  label: string
  description: string
  fields: TaskFieldSpec[]
}

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
  // 分支：branch_of_key 指向某個 condition step 的 key（不是 task id）
  branch_of_key: string | null
  branch_when: 'true' | 'false' | null
  // 建立當下的本地 key，畫布用它把 branch_of_key 解析回 task_id
  step_key: string | null
  reduce_of_key: string | null
  task_status: TaskStatus | null
  task_name: string | null
  task_type: string | null
}

export interface Workflow {
  id: string
  name: string
  status: WorkflowStatus
  created_at: string
  updated_at: string
  steps: WorkflowStep[]
  // null for a workflow created before this field existed — such a
  // workflow can't be promoted to a schedule (there's no template to reuse).
  steps_template: WorkflowStepCreate[] | null
  // 整條 workflow 成功時的終端結果，{step_key: result}；失敗或執行中是 null
  result: Record<string, unknown> | null
  // 屬於哪個定義；舊資料與 POST /workflows/ 建立的一次性 workflow 是 null
  definition_id: string | null
  definition_version: number | null
  // 這次 run 經 input_schema 檢查、補完預設值後的輸入
  input: Record<string, unknown> | null
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
  reduce_of?: string | null
  branch_of?: string | null
  branch_when?: 'true' | 'false' | null
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
  // 新排程指向一個定義；舊排程是 null，改帶自己的 steps 快照
  definition_id: string | null
  input: Record<string, unknown> | null
  steps: WorkflowStepCreate[]
  enabled: boolean
  next_run_at: string | null
  last_run_at: string | null
  created_at: string
  updated_at: string
  definition_name: string | null
  definition_version: string | null
}

export interface WorkflowScheduleCreate {
  name: string
  cron_expression: string
  definition_id: string
  input: Record<string, unknown>
  enabled: boolean
}

export interface PromoteWorkflowToSchedule {
  name: string
  cron_expression: string
  enabled: boolean
}

export interface WorkflowScheduleUpdate {
  name?: string
  cron_expression?: string
  input?: Record<string, unknown>
  enabled?: boolean
}

export interface WorkflowRunSummary {
  id: string
  status: WorkflowStatus
  created_at: string
}

export interface WorkflowDefinition {
  id: string
  name: string
  description: string | null
  steps: WorkflowStepCreate[]
  // 跟 task-type catalog 的 field spec 同形，run 表單直接用 TaskPayloadFields 畫
  input_schema: TaskFieldSpec[]
  version: number
  created_at: string
  updated_at: string
  run_count: number
  last_run: WorkflowRunSummary | null
}

export interface WorkflowDefinitionCreate {
  name: string
  description?: string | null
  steps: WorkflowStepCreate[]
  // 透過 schema 描述哪些 field 給前端當參數輸入用（順序就是輸入頁面從上到下的欄位順序）
  input_schema: TaskFieldSpec[]
}
