import { getAuthToken } from './authStorage'
import type {
  AuthResponse,
  PromoteWorkflowToSchedule,
  Task,
  TaskCreate,
  TaskListFilters,
  TaskTypeSpec,
  User,
  Workflow,
  WorkflowCreate,
  WorkflowSchedule,
  WorkflowScheduleCreate,
  WorkflowScheduleUpdate,
} from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
  status: number
  retryAfter?: number

  constructor(message: string, status: number, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getAuthToken()
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // response had no JSON body
    }
    const retryAfter = res.headers.get('Retry-After')
    throw new ApiError(
      detail,
      res.status,
      retryAfter ? Number(retryAfter) : undefined,
    )
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export function fetchHealth(): Promise<{ status: string; message: string }> {
  return request('/health')
}

export function register(username: string, password: string): Promise<AuthResponse> {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function login(username: string, password: string): Promise<AuthResponse> {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function fetchMe(): Promise<User> {
  return request('/auth/me')
}

export function listTasks(filters: TaskListFilters): Promise<Task[]> {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.task_type) params.set('task_type', filters.task_type)
  params.set('limit', String(filters.limit))
  params.set('offset', String(filters.offset))
  return request(`/tasks/?${params.toString()}`)
}

export function getTask(id: string): Promise<Task> {
  return request(`/tasks/${id}`)
}

export function listTaskTypes(): Promise<TaskTypeSpec[]> {
  return request('/tasks/types')
}

export function createTask(task: TaskCreate): Promise<Task> {
  return request('/tasks/', { method: 'POST', body: JSON.stringify(task) })
}

export function deleteTask(id: string): Promise<void> {
  return request(`/tasks/${id}`, { method: 'DELETE' })
}

export function listWorkflows(limit = 20, offset = 0): Promise<Workflow[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return request(`/workflows/?${params.toString()}`)
}

export function getWorkflow(id: string): Promise<Workflow> {
  return request(`/workflows/${id}`)
}

export function createWorkflow(workflow: WorkflowCreate): Promise<Workflow> {
  return request('/workflows/', { method: 'POST', body: JSON.stringify(workflow) })
}

export function promoteWorkflowToSchedule(
  id: string,
  body: PromoteWorkflowToSchedule,
): Promise<WorkflowSchedule> {
  return request(`/workflows/${id}/promote-to-schedule`, { method: 'POST', body: JSON.stringify(body) })
}

export function listSchedules(): Promise<WorkflowSchedule[]> {
  return request('/schedules/')
}

export function getSchedule(id: string): Promise<WorkflowSchedule> {
  return request(`/schedules/${id}`)
}

export function createSchedule(schedule: WorkflowScheduleCreate): Promise<WorkflowSchedule> {
  return request('/schedules/', { method: 'POST', body: JSON.stringify(schedule) })
}

export function updateSchedule(id: string, patch: WorkflowScheduleUpdate): Promise<WorkflowSchedule> {
  return request(`/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })
}

export function deleteSchedule(id: string): Promise<void> {
  return request(`/schedules/${id}`, { method: 'DELETE' })
}

export function deleteWorkflow(id: string): Promise<void> {
  return request(`/workflows/${id}`, { method: 'DELETE' })
}