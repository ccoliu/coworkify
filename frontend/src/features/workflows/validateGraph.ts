import { effectiveDependsOn, type StepDraft } from "./WorkflowStepsEditor";

export interface StepIssue {
    /** null 代表整體性問題，不屬於任何節點 */
    uid: string | null
    message: string
}

// 以下規則逐條鏡射 app/schemas/workflow.py 的 WorkflowCreate.validate_dag
// （2026-09-13 對照）。後端那份是最終把關，不可刪；這裡只是提前告知，
// 兩邊改動時請一起看。

const STEP_KEY_RE = /^[a-zA-Z0-9_]+$/
const STEP_REF_RE = /\{\{\s*steps\.([a-zA-Z0-9_]+)\.result(?:\.[a-zA-Z0-9_]+)*\s*\}\}/g
const STEP_REF_SYNTAX = '{{steps.<key>.result}}'

function referencedKeys(payload: Record<string, unknown>): string[] {
    return [...JSON.stringify(payload ?? {}).matchAll(STEP_REF_RE)].map((m) => m[1])
}

export function validateGraph(steps: StepDraft[]): StepIssue[] {
    const issues: StepIssue[] = []
    const add = (uid: string | null, message: string) => { issues.push({ uid, message }) }

    if (steps.length === 0) {
        add(null, '至少要有一個 step')
        return issues
    }

    const byUid = new Map(steps.map((s) => [s.uid, s]))
    const uidByKey = new Map(steps.map((s) => [s.key, s.uid]))
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