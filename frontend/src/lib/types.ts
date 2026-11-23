export type TaskStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'retrying'
  | 'waiting'
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
  'waiting',
  'cancelled',
]

export interface TaskLog {
  id: string
  status: TaskStatus
  result: unknown
  error_message: string | null
  execution_time_ms: number | null
  worker_id: string | null,
  created_at: string
}

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
  // 怎麼開始的；手動建立與舊資料是 null
  trigger_kind?: 'schedule' | 'webhook' | 'workflow' | null
  trigger_id?: string | null
  upstream_run?: LinkedRun | null
  downstream_runs?: LinkedRun[]
}

export interface LinkedRun {
  id: string
  name: string
  status: WorkflowStatus
  created_at: string
  // 上游以什麼結果結束才觸發這條串接
  via_status: 'success' | 'failed' | null
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
  last_error: string | null
  last_error_at: string | null
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

// 值寫進去之後 API 就不會再回傳，這裡刻意沒有 value
export interface Connection {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface ConnectionCreate {
  name: string
  value: string
  description?: string | null
}

export interface ConnectionUpdate {
  value?: string
  description?: string | null
}

export type TriggerKind = 'webhook' | 'workflow'
export type TriggerOnStatus = 'success' | 'failed' | 'any'

// 觸發器：webhook（外部打 /hooks/<id>）或 workflow（另一條產線的 run 結束時）。
// webhook 的 secret 只在建立與換新時出現在 WorkflowTriggerWithSecret
export interface WorkflowTrigger {
  id: string
  name: string
  kind: TriggerKind
  // 要啟動的產線
  definition_id: string
  // workflow 觸發器才有：看哪條產線的 run、什麼結果
  source_definition_id: string | null
  on_status: TriggerOnStatus | null
  // run 輸入欄位 → 路徑。webhook 對 request body 取值，例如 { repo: 'repository.full_name' }；
  // workflow 對 { workflow_id, status, result, input } 取值，例如 { summary: 'result.summarize' }
  input_mapping: Record<string, string>
  // 路徑 → 期望值；陣列代表「其中之一」
  filter: Record<string, unknown>
  enabled: boolean
  last_triggered_at: string | null
  last_error: string | null
  last_error_at: string | null
  created_at: string
  updated_at: string
  // webhook 才有，例如 /hooks/<id>，前面接 API 的網址
  hook_path: string | null
}

export interface WorkflowTriggerWithSecret extends WorkflowTrigger {
  // workflow 觸發器沒有 secret
  secret: string | null
}

export interface WorkflowTriggerCreate {
  name: string
  kind: TriggerKind
  definition_id: string
  source_definition_id?: string | null
  on_status?: TriggerOnStatus
  input_mapping: Record<string, string>
  filter: Record<string, unknown>
  enabled?: boolean
}

export interface WorkflowTriggerUpdate {
  name?: string
  input_mapping?: Record<string, string>
  filter?: Record<string, unknown>
  on_status?: TriggerOnStatus
  enabled?: boolean
}
