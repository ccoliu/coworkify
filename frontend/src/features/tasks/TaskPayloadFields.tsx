import { useId, useState, type ChangeEvent } from 'react'
import type { TaskFieldSpec } from '../../lib/types'
import { Input, Label, Select, Textarea } from '../../components/Field'
import { useToast } from '../../context/ToastContext'
import { CodeEditor } from '../../components/CodeEditor'
import { Modal } from '../../components/Modal'

interface Props {
  idPrefix: string
  fields: TaskFieldSpec[]
  payload: Record<string, unknown>
  onChange: (payload: Record<string, unknown>) => void
}

// 檔案讀進來的內容會整包放進 payload、整包送去後端，太大的檔案沒什麼意義，
// 先擋在前端省一趟無謂的請求。
const MAX_UPLOAD_BYTES = 512 * 1024

function FileUploadButton({
  accept,
  onLoaded,
}: {
  accept: string
  onLoaded: (content: string, filename: string) => void
}) {
  const inputId = useId()
  const { push } = useToast()

  async function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // 允許連續選同一個檔案也能再次觸發 onChange
    if (!file) return

    if (file.size > MAX_UPLOAD_BYTES) {
      push(`File too large (${Math.round(file.size / 1024)}KB) — limit is ${MAX_UPLOAD_BYTES / 1024}KB`, 'error')
      return
    }

    try {
      onLoaded(await file.text(), file.name)
    } catch {
      push(`Failed to read ${file.name}`, 'error')
    }
  }

  return (
    <label
      htmlFor={inputId}
      className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-ink-secondary hover:bg-plane"
    >
      Upload file…
      <input id={inputId} type="file" accept={accept} onChange={onFileChange} className="hidden" />
    </label>
  )
}

function CodeField({
  label,
  value,
  language,
  onChange,
}: {
  label: string
  value: string
  language?: string | null
  onChange: (next: string) => void
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      <CodeEditor value={value} language={language} onChange={onChange} />
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="mt-1 text-xs font-medium text-accent"
      >
        ⤢ 放大編輯
      </button>
      {expanded && (
        <Modal title={label} wide onClose={() => setExpanded(false)}>
          <CodeEditor value={value} language={language} onChange={onChange} height="60vh" />
        </Modal>
      )}
    </>
  )
}

export function TaskPayloadFields({ idPrefix, fields, payload, onChange }: Props) {
  const [uploadedNames, setUploadedNames] = useState<Record<string, string>>({})

  if (fields.length === 0) return null

  return (
    <div className="flex flex-col gap-3">
      {fields.map((field) => {
        const id = `${idPrefix}-${field.key}`
        const value = payload[field.key]

        return (
          <div key={field.key}>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <Label htmlFor={id}>
                {field.label}
                {field.required && ' *'}
              </Label>
              {(field.kind === 'text' || field.kind === 'code') && field.upload_accept && (
                <FileUploadButton
                  accept={field.upload_accept}
                  onLoaded={(content, filename) => {
                    onChange({ ...payload, [field.key]: content })
                    setUploadedNames((names) => ({ ...names, [field.key]: filename }))
                  }}
                />
              )}
            </div>

            {field.kind === 'boolean' ? (
              <Select
                id={id}
                value={String(value)}
                onChange={(e) => onChange({ ...payload, [field.key]: e.target.value === 'true' })}
              >
                <option value="false">false</option>
                <option value="true">true</option>
              </Select>
            ) : field.kind === 'select' ? (
              <Select
                id={id}
                value={String(value ?? '')}
                onChange={(e) => onChange({ ...payload, [field.key]: e.target.value })}
              >
                {(field.options ?? []).map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
            ) : field.kind === 'multiselect' ? (
              <div className="flex flex-wrap gap-3 rounded-lg border border-border px-3 py-2">
                {(field.options ?? []).map((opt) => {
                  const selected = Array.isArray(value) && (value as string[]).includes(opt.value)
                  return (
                    <label key={opt.value} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => {
                          const current = Array.isArray(value) ? (value as string[]) : []
                          const next = selected
                            ? current.filter((v) => v !== opt.value)
                            : [...current, opt.value]
                          onChange({ ...payload, [field.key]: next })
                        }}
                      />
                      {opt.label}
                    </label>
                  )
                })}
              </div>
            ) : field.kind === 'code' ? (
              <CodeField
                label={field.label}
                value={String(value ?? '')}
                language={field.language}
                onChange={(next) => onChange({ ...payload, [field.key]: next })}
              />
            ) : field.kind === 'text' ? (
              <Textarea
                id={id}
                value={String(value ?? '')}
                onChange={(e) => onChange({ ...payload, [field.key]: e.target.value })}
                rows={6}
              />
            ) : (
              <Input
                id={id}
                type={field.kind === 'number' ? 'number' : 'text'}
                value={String(value ?? '')}
                onChange={(e) =>
                  onChange({
                    ...payload,
                    [field.key]: field.kind === 'number' ? Number(e.target.value) : e.target.value,
                  })
                }
              />
            )}

            {uploadedNames[field.key] && (
              <p className="mt-1 text-xs text-ink-muted">Loaded from {uploadedNames[field.key]}</p>
            )}
            {field.help && <p className="mt-1 text-xs text-ink-muted">{field.help}</p>}
          </div>
        )
      })}
    </div>
  )
}
