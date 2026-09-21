import type { TaskFieldSpec } from "../../lib/types";
import { effectiveDependsOn, type StepDraft } from "./WorkflowStepsEditor";

export interface StepIssue {
    /** null 代表整體性問題，不屬於任何節點 */
    uid: string | null
    message: string
    /** warning 不擋存檔，只是提醒；沒寫就是 error */
    severity?: 'error' | 'warning'
}

// 以下規則逐條鏡射 app/schemas/workflow.py 的 WorkflowCreate.validate_dag
// （2026-09-13 對照）。後端那份是最終把關，不可刪；這裡只是提前告知，
// 兩邊改動時請一起看。

const STEP_KEY_RE = /^[a-zA-Z0-9_]+$/
const STEP_REF_RE = /\{\{\s*steps\.([a-zA-Z0-9_]+)\.result(?:\.[a-zA-Z0-9_]+)*\s*\}\}/g
const STEP_REF_SYNTAX = '{{steps.<key>.result}}'

// 任何 {{...}}，用來找出「看起來像模板、但其實不會被代換」的寫法
const ANY_TEMPLATE_RE = /\{\{\s*([^{}]*?)\s*\}\}/g
const VALID_STEP_REF_RE = /^steps\.[a-zA-Z0-9_]+\.result(?:\.[a-zA-Z0-9_]+)*$/
const ITEM_REF_RE = /^item(?:\.[a-zA-Z0-9_.]+)?$/

function referencedKeys(payload: Record<string, unknown>): string[] {
    return [...JSON.stringify(payload ?? {}).matchAll(STEP_REF_RE)].map((m) => m[1])
}

/**
 * 模板寫錯時，executor 不會報錯，而是把 {{...}} 原樣送出去——通知收到一串大括號、
 * 網址變成 404，症狀離原因很遠。這裡把「長得像模板但不會被代換」的寫法抓出來。
 */
function templateWarnings(step: StepDraft, stepKeys: Set<string>): string[] {
    // python 程式碼裡的 {{ 可能是 f-string 的跳脫（f"{{literal}}"），不檢查
    const scanned =
        step.taskType === 'python'
            ? Object.fromEntries(Object.entries(step.payload ?? {}).filter(([k]) => k !== 'code'))
            : step.payload ?? {}

    const warnings = new Set<string>()
    for (const match of JSON.stringify(scanned).matchAll(ANY_TEMPLATE_RE)) {
        const inner = match[1]
        const raw = `{{${inner}}}`

        if (VALID_STEP_REF_RE.test(inner)) continue

        if (ITEM_REF_RE.test(inner)) {
            if (!step.forEachUid) warnings.add(`${raw} 只在 for_each 展開步驟裡有值，這裡會原樣送出`)
            continue
        }
        if (inner === 'items') {
            if (!step.reduceOfUid) warnings.add(`${raw} 只在 reduce 步驟裡有值，這裡會原樣送出`)
            continue
        }

        // 常見的是順序寫反（{{input_1.steps.result.x}}），有提到既有的 step key 就直接給出正確寫法
        const parts = inner.split('.')
        const mentioned = parts.find((p) => stepKeys.has(p))
        if (mentioned) {
            const resultAt = parts.indexOf('result')
            const tail = resultAt >= 0 ? parts.slice(resultAt + 1).map((p) => `.${p}`).join('') : ''
            warnings.add(`看不懂的模板 ${raw}，執行時會原樣送出；是不是要寫 {{steps.${mentioned}.result${tail}}}？`)
        } else {
            warnings.add(`看不懂的模板 ${raw}，執行時會原樣送出；格式是 {{steps.<step key>.result.<欄位>}}`)
        }
    }
    return [...warnings]
}


export function validateGraph(steps: StepDraft[]): StepIssue[] {
    const issues: StepIssue[] = []
    const add = (uid: string | null, message: string) => { issues.push({ uid, message }) }
    const warn = (uid: string | null, message: string) => { issues.push({ uid, message, severity: 'warning' }) }

    if (steps.length === 0) {
        add(null, '至少要有一個 step')
        return issues
    }

    const byUid = new Map(steps.map((s) => [s.uid, s]))
    const uidByKey = new Map(steps.map((s) => [s.key, s.uid]))
    const stepKeys = new Set(steps.map((s) => s.key))
    const nameOf = (uid: string) => byUid.get(uid)?.name.trim() || byUid.get(uid)?.key || 'step'

    const keyCount = new Map<string, number>()
    for (const s of steps) keyCount.set(s.key, (keyCount.get(s.key) ?? 0) + 1)

    const inputSteps = steps.filter((s) => s.taskType === 'input')
    if (inputSteps.length > 1) {
        for (const s of inputSteps) add(s.uid, '一個 workflow 只能有一個 input step')
    }

    for (const step of steps) {
        const deps = effectiveDependsOn(step)

        if (!step.name.trim()) add(step.uid, '名稱不可空白')
        if (!step.taskType) add(step.uid, '沒有選 task type')
        if (!STEP_KEY_RE.test(step.key)) add(step.uid, `Step key「${step.key}」只能用英數字與底線`)
        else if ((keyCount.get(step.key) ?? 0) > 1) add(step.uid, `Step key「${step.key}」與其他 step 重複`)

        for (const dep of deps) {
            if (!byUid.has(dep)) add(step.uid, '依賴了不存在的 step')
            if (dep === step.uid) add(step.uid, '不能依賴自己')
        }

        // payload 裡的 {{steps.<key>.result}} 參照
        const refs = referencedKeys(step.payload)
        if (refs.length > 0 && step.forEachUid) {
            add(step.uid, `動態展開步驟的 payload 不支援 ${STEP_REF_SYNTAX}，請改用 {{item}}`)
        }

        for (const ref of refs) {
            if (ref === step.key) {
                add(step.uid, 'payload 不能參照自己的結果')
                continue
            }
            const refUid = uidByKey.get(ref)
            if (!refUid) add(step.uid, `payload 參照了不存在的 step「${ref}」`)
            else if (!deps.includes(refUid)) {
                add(step.uid, `payload 參照了「${ref}」的結果，必須在畫布上把它連成上游`)
            }
        }

        // reduce（對應 validate_dag 的 reduce_of 段落）
        if (step.reduceOfUid) {
            const src = byUid.get(step.reduceOfUid)
            if (step.reduceOfUid === step.uid) add(step.uid, '不能 reduce 自己')
            else if (!src) add(step.uid, 'reduce 來源已不存在')
            else if (!src.forEachUid) {
                add(step.uid, `reduce 來源「${nameOf(step.reduceOfUid)}」不是 for_each 展開步驟`)
            }
            if (step.forEachUid) add(step.uid, '不能同時是 for_each 與 reduce 步驟')
            if (step.branchOfUid) add(step.uid, '不能同時是 branch 與 reduce 步驟')
            if (deps.length > 0) add(step.uid, 'reduce 步驟的依賴會在展開後自動決定，不能自己拉線進來')
            if (refs.length > 0) {
                add(step.uid, 'reduce 步驟的 payload 不支援 {{steps...}}，請用 {{items}}（python 用 inputs）')
            }
        }

        // 分支
        if (step.branchOfUid || step.branchWhen) {
            if (!step.branchOfUid || !step.branchWhen) {
                add(step.uid, 'branch 來源與 true/false 要一起設定')
            } else {
                if (step.forEachUid) add(step.uid, '分支步驟不能同時是動態展開步驟')
                if (step.branchOfUid === step.uid) add(step.uid, '不能 branch 自己')
                const src = byUid.get(step.branchOfUid)
                if (!src) add(step.uid, 'branch 來源已不存在')
                else if (src.taskType !== 'condition') {
                    add(step.uid, `branch 來源「${nameOf(step.branchOfUid)}」不是 condition 步驟`)
                }
            }
        }

        // for_each 分組
        if (step.forEachUid) {
            const src = byUid.get(step.forEachUid)
            if (step.forEachUid === step.uid) add(step.uid, '不能 for_each 自己')
            else if (!src) add(step.uid, 'for_each 來源已不存在')
            else if (src.forEachUid) {
                add(step.uid, `for_each 目標「${nameOf(step.forEachUid)}」本身也是展開步驟，不支援巢狀展開`)
            }
            for (const dep of deps) {
                if ((byUid.get(dep)?.forEachUid ?? null) !== step.forEachUid) {
                    add(step.uid, `展開步驟只能依賴同一組的展開步驟，不可依賴「${nameOf(dep)}」`)
                }
            }
        } else {
            for (const dep of deps) {
                if (byUid.get(dep)?.forEachUid) {
                    add(step.uid, `依賴了動態展開步驟「${nameOf(dep)}」，fan-in 需要 reduce 步驟`)
                }
            }
        }

        if (step.taskType === 'input' && deps.length > 0) {
            add(step.uid, 'input step 是資料入口，不能有上游')
        }

        // condition 的 left：這就是 cond_test 當初踩的那條（後端同步補上）
        if (step.taskType === 'condition') {
            const left = step.payload.left
            if (left === undefined || left === null || left === '') {
                if (deps.length !== 1) {
                    add(
                        step.uid,
                        `condition 沒填 Left，需要剛好一個上游 step 讓系統自動帶入結果（目前 ${deps.length} 個）`,
                    )
                }
            }
        }

        // python 已經改用全域 inputs 取上游結果（見 app/tasks/handler.py 的 _PY_RUNNER）。
        // 模板還是會被解析，所以不擋，但字串插值會毀掉型別，值來自表單時還是注入風險。
        if (
            step.taskType === 'python' &&
            typeof step.payload.code === 'string' &&
            step.payload.code.includes('{{steps.')
        ) {
            warn(step.uid, 'python 程式碼不需要 {{steps...}}：上游結果放在全域變數 inputs 裡，或寫成 main(inputs)')
        }

        for (const message of templateWarnings(step, stepKeys)) warn(step.uid, message)

    }

    // 循環依賴：跟後端同樣是三色 DFS，但把所有涉及的節點都收集起來而不是拋第一個。
    // 注意這整段在 for 迴圈「之外」——要等所有 step 的依賴都看過才能判斷。
    const WHITE = 0
    const GRAY = 1
    const BLACK = 2
    const color = new Map(steps.map((s) => [s.uid, WHITE]))
    const inCycle = new Set<string>()

    function dfs(uid: string) {
        color.set(uid, GRAY)
        for (const dep of effectiveDependsOn(byUid.get(uid) as StepDraft)) {
            if (!byUid.has(dep)) continue
            if (color.get(dep) === GRAY) {
                inCycle.add(uid)
                inCycle.add(dep)
            } else if (color.get(dep) === WHITE) {
                dfs(dep)
            }
        }
        color.set(uid, BLACK)
    }

    for (const s of steps) if (color.get(s.uid) === WHITE) dfs(s.uid)
    for (const uid of inCycle) add(uid, '循環依賴')

    return issues
}


export function issuesByUid(issues: StepIssue[]): Map<string, string[]> {
    const map = new Map<string, string[]>()
    for (const issue of issues) {
        if (!issue.uid) continue
        map.set(issue.uid, [...(map.get(issue.uid) ?? []), issue.message])
    }
    return map
}

/** 鏡射 app/schemas/definition.py 的 InputFieldSpec + validate_input_schema。 */
export function validateInputSchema(schema: TaskFieldSpec[], steps: StepDraft[]): StepIssue[] {
    const issues: StepIssue[] = []
    const add = (message: string) => { issues.push({ uid: null, message }) }

    const counts = new Map<string, number>()
    for (const f of schema) counts.set(f.key, (counts.get(f.key) ?? 0) + 1)

    for (const f of schema) {
        // key 會出現在 '{{steps.<input step>.result.<key>}}' 的路徑裡，規則跟 step key 一樣
        if (!STEP_KEY_RE.test(f.key)) add(`輸入欄位 key「${f.key}」只能用英數字與底線`)
        else if ((counts.get(f.key) ?? 0) > 1) add(`輸入欄位 key「${f.key}」已重複`)
        if (!f.label.trim()) add(`輸入欄位「${f.key}」缺少顯示名稱`)
        if ((f.kind === 'select' || f.kind === 'multiselect') && !f.options?.length) {
            add(`輸入欄位「${f.key}」是選項型，至少要有一個選項`)
        }
    }

    if (schema.length > 0 && !steps.some((s) => s.taskType === 'input')) {
        add('有輸入欄位就需要一個 input step——run 填的值會從那一步進入 workflow')
    }

    return issues
}