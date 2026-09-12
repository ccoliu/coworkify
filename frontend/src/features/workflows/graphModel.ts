import dagre, { Graph } from "@dagrejs/dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import { shortId } from "../../lib/format";
import type { TaskStatus, WorkflowStep } from "../../lib/types";
import type { StepDraft } from "./WorkflowStepsEditor";

export const NODE_WIDTH = 216;
export const NODE_HEIGHT = 76;

// 用 type 而不是 interface：React Flow 的 Node<T> 要求 T 可指派給
// Record<string, unknown>，只有 type alias 會有隱含的 index signature。
export type StepNodeData = {
    label: string
    taskType: string
    status: TaskStatus | null
    branchWhen: 'true' | 'false' | null
    isReduce: boolean
    selected: boolean
}

export type StepNode = Node<StepNodeData, 'task' | 'condition'>

/**
 * 畫布用的中性 step 表示法。run view（WorkflowStep，id 是 task_id）與 Phase 2 的
 * builder（StepDraft，id 是 draft uid）都先轉成這個形狀，toFlow / autoLayout 就能
 * 兩邊共用，不用各寫一份。
 */

export interface GraphStep {
    id: string
    name: string
    taskType: string
    status: TaskStatus | null
    dependsOn: string[]
    branchOfId: string | null
    branchWhen: 'true' | 'false' | null
    isReduce: boolean
    // builder 專用：這個 step 依哪個 step 的結果展開 / 收斂。run view 拿不到
    // for_each 資訊（展開後的 task 只剩 depends_on），所以那邊一律 null。
    forEachId: string | null
    reduceOfId: string | null
}

const EDGE_COLOR = 'var(--color-baseline)'
const EDGE_COLOR_MUTED = 'var(--color-ink-muted)'

/** 已執行的 workflow（GET /workflows/{id}）→ GraphStep。 */
export function stepsFromWorkflow(steps: WorkflowStep[]): GraphStep[] {
    // branch_of_key 存的是「建立當下的 step key」而不是 task id，先建對照表才連得起來。
    const taskIdByStepKey = new Map<string, string>()
    for (const s of steps) {
        if (s.step_key) taskIdByStepKey.set(s.step_key, s.task_id)
    }

    // depends_on 可能指到這個 workflow 以外（或已被硬刪）的 task，濾掉避免畫出斷頭的邊。
    const known = new Set(steps.map((s) => s.task_id))

    return steps.map((s) => ({
        id: s.task_id,
        name: s.task_name ?? shortId(s.task_id),
        taskType: s.task_type ?? 'unknown',
        status: s.task_status,
        dependsOn: s.depends_on.filter((d) => known.has(d)),
        branchOfId: s.branch_of_key ? (taskIdByStepKey.get(s.branch_of_key) ?? null) : null,
        branchWhen: s.branch_when,
        isReduce: s.reduce_of_key != null,
        forEachId: null,
        reduceOfId: null,
    }))
}

export function stepsFromDrafts(drafts: StepDraft[]): GraphStep[] {
    const known = new Set(drafts.map((d) => d.uid))
    return drafts.map((d) => ({
        id: d.uid,
        name: d.name.trim() || d.taskType || 'step',
        taskType: d.taskType,
        status: null,
        dependsOn: d.dependsOnUids.filter((u) => known.has(u)),
        branchOfId: d.branchOfUid,
        branchWhen: d.branchWhen,
        isReduce: false,
        forEachId: d.forEachUid,
        reduceOfId: null,
    }))
}

/**
 * 加上 source → target 這條邊會不會成環。從 target 往下游走，走得回 source 就會。
 * Phase 3 會把 validate_dag 整組鏡射過來，這裡先擋掉最致命的一種。
 */
export function wouldCreateCycle(steps: GraphStep[], sourceId: string, targetId: string): boolean {
    if (sourceId === targetId) return true
    const downstream = new Map<string, string[]>()
    for (const s of steps) {
        for (const dep of s.dependsOn) {
            downstream.set(dep, [...(downstream.get(dep) ?? []), s.id])
        }
    }
    const seen = new Set<string>()
    const stack = [targetId]
    while (stack.length > 0) {
        const cur = stack.pop() as string
        if (cur == sourceId) return true
        if (seen.has(cur)) continue
        seen.add(cur)
        stack.push(...(downstream.get(cur) ?? []))
    }
    return false
}

export function toFlow(steps: GraphStep[]): { nodes: StepNode[]; edges: Edge[] } {
    const nodes: StepNode[] = steps.map((step) => ({
        id: step.id,
        type: step.taskType === 'condition' ? 'condition' : 'task',
        position: { x: 0, y: 0 }, // 真正的座標交給 autoLayout
        data: {
            label: step.name,
            taskType: step.taskType,
            status: step.status,
            branchWhen: step.branchWhen,
            isReduce: step.isReduce,
            selected: false,
        },
    }))

    const isCondition = new Map(steps.map((s) => [s.id, s.taskType === 'condition']))
    const edges: Edge[] = []

    for (const step of steps) {
        for (const depId of step.dependsOn) {
            const isBranch = depId === step.branchOfId && step.branchWhen != null
            // condition 節點有 true / false 兩個具名輸出，外加一個給「只是依賴它、
            // 沒做分支」用的 out，所以從 condition 出發的邊一定要指定 sourceHandle。
            const sourceHandle = isCondition.get(depId) ? (isBranch ? step.branchWhen : 'out') : undefined
            const dimmed = step.status === 'cancelled'
            const live = step.status === 'running' || step.status === 'retrying'

            edges.push({
                id: `${depId}->${step.id}`,
                source: depId,
                target: step.id,
                sourceHandle,
                type: 'smoothstep',
                animated: live,
                label: isBranch ? step.branchWhen : undefined,
                // 只有 depends_on 的邊可以被刪；for_each / reduce 是在屬性面板設定的
                data: { kind: 'depends' },
                deletable: true,
                style: {
                    stroke: dimmed ? EDGE_COLOR_MUTED : EDGE_COLOR,
                    strokeWidth: dimmed ? 1 : 1.5,
                    opacity: dimmed ? 0.4 : 1,
                    strokeDasharray: dimmed ? '4 3' : undefined,
                },
                labelStyle: { fill: 'var(--color-ink-secondary)', fontSize: 11, fontWeight: 600 },
                labelBgStyle: { fill: 'var(--color-surface)' },
                labelBgPadding: [4, 2],
                labelBgBorderRadius: 4,
                markerEnd: {
                    type: MarkerType.ArrowClosed,
                    width: 16,
                    height: 16,
                    color: dimmed ? EDGE_COLOR_MUTED : EDGE_COLOR,
                },
            })
        }

        // for_each / reduce 不是依賴關係，是「資料從哪裡來」，畫成虛線區隔開來
        for (const [kind, srcId] of [
            ['foreach', step.forEachId],
            ['reduce', step.reduceOfId],
        ] as const) {
            if (!srcId) continue
            edges.push({
                id: `${srcId}-${kind}-${step.id}`,
                source: srcId,
                target: step.id,
                sourceHandle: isCondition.get(srcId) ? 'out' : undefined,
                type: 'smoothstep',
                label: kind === 'foreach' ? 'for each' : 'reduce',
                data: { kind },
                deletable: false,
                style: { stroke: EDGE_COLOR_MUTED, strokeWidth: 1.5, strokeDasharray: '5 4' },
                labelStyle: { fill: 'var(--color-ink-muted)', fontSize: 11, fontWeight: 600 },
                labelBgStyle: { fill: 'var(--color-surface)' },
                labelBgPadding: [4, 2],
                labelBgBorderRadius: 4,
            })
        }
    }

    return { nodes, edges }
}

/** dagre 由左至右排版。同一組 DAG 結果是穩定的，所以狀態更新重算不會讓節點亂跳。 */
export function autoLayout(nodes: StepNode[], edges: Edge[]): StepNode[] {
    const g = new dagre.graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({ rankdir: 'LR', nodesep: 32, ranksep: 88, marginx: 16, marginy: 16 })

    for (const n of nodes) g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
    for (const e of edges) g.setEdge(e.source, e.target)
    dagre.layout(g)

    return nodes.map((n) => {
        const { x, y } = g.node(n.id)
        // dagre 給的是節點中心點，React Flow 要的是左上角
        return { ...n, position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 } }
    })
}

export function buildWorkflowGraph(steps: WorkflowStep[]): { nodes: StepNode[]; edges: Edge[] } {
    const { nodes, edges } = toFlow(stepsFromWorkflow(steps))
    return { nodes: autoLayout(nodes, edges), edges }
}
