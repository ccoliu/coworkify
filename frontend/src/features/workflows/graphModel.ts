import dagre from "@dagrejs/dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import { shortId } from "../../lib/format";
import type { LinkedRun, TaskStatus, WorkflowStatus, WorkflowStep } from "../../lib/types";
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
    /** builder 的驗證訊息；run view 一律空陣列 */
    issues: string[]
}

export type StepNode = Node<StepNodeData, 'task' | 'condition'>

// workflow 觸發器串起來的另一個 run：畫在最左（上游）或最右（下游），點了跳過去
export type RunNodeData = {
    runId: string
    label: string
    status: WorkflowStatus
    direction: 'upstream' | 'downstream'
}

export type RunNode = Node<RunNodeData, 'run'>

export type CanvasNode = StepNode | RunNode

export interface LinkedRuns {
    upstream?: LinkedRun | null
    downstream?: LinkedRun[]
}

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
        isReduce: d.reduceOfUid != null,
        forEachId: d.forEachUid,
        reduceOfId: d.reduceOfUid,
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
            issues: []
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
export function autoLayout<N extends Node>(nodes: N[], edges: Edge[]): N[] {
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

const UPSTREAM_NODE_ID = 'run:upstream'

function runEdge(id: string, source: string, target: string, viaStatus: string | null, sourceHandle?: string): Edge {
    return {
        id,
        source,
        target,
        sourceHandle,
        type: 'smoothstep',
        label: viaStatus ? `on ${viaStatus}` : 'triggered',
        data: { kind: 'trigger' },
        deletable: false,
        // 跨 run 的邊用虛線，跟 run 內部的依賴分開
        style: { stroke: EDGE_COLOR_MUTED, strokeWidth: 1.5, strokeDasharray: '6 4' },
        labelStyle: { fill: 'var(--color-ink-muted)', fontSize: 11, fontWeight: 600 },
        labelBgStyle: { fill: 'var(--color-surface)' },
        labelBgPadding: [4, 2],
        labelBgBorderRadius: 4,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: EDGE_COLOR_MUTED },
    }
}

/**
 * 上游 run 接到這個 run 的起點步驟（沒有上游依賴的）；終點步驟（沒有人依賴的）接到每個下游 run。
 * 終點步驟優先挑沒被取消的——分支沒走到的那一邊不是真正收尾的地方。
 */
function addLinkedRuns(steps: GraphStep[], links: LinkedRuns, nodes: CanvasNode[], edges: Edge[]) {
    const runNode = (id: string, run: LinkedRun, direction: RunNodeData['direction']): RunNode => ({
        id,
        type: 'run',
        position: { x: 0, y: 0 },
        data: { runId: run.id, label: run.name, status: run.status, direction },
    })

    if (links.upstream) {
        nodes.push(runNode(UPSTREAM_NODE_ID, links.upstream, 'upstream'))
        for (const step of steps.filter((s) => s.dependsOn.length === 0)) {
            edges.push(runEdge(`${UPSTREAM_NODE_ID}->${step.id}`, UPSTREAM_NODE_ID, step.id, links.upstream.via_status))
        }
    }

    const downstream = links.downstream ?? []
    if (downstream.length === 0) return
    const dependedOn = new Set(steps.flatMap((s) => s.dependsOn))
    const terminal = steps.filter((s) => !dependedOn.has(s.id))
    const finishing = terminal.filter((s) => s.status !== 'cancelled')
    const ends = finishing.length > 0 ? finishing : terminal
    for (const run of downstream) {
        const id = `run:${run.id}`
        nodes.push(runNode(id, run, 'downstream'))
        for (const step of ends) {
            // condition 節點的一般輸出是具名的 out
            const handle = step.taskType === 'condition' ? 'out' : undefined
            edges.push(runEdge(`${step.id}->${id}`, step.id, id, run.via_status, handle))
        }
    }
}

export function buildWorkflowGraph(
    steps: WorkflowStep[],
    links: LinkedRuns = {},
): { nodes: CanvasNode[]; edges: Edge[] } {
    const graphSteps = stepsFromWorkflow(steps)
    const flow = toFlow(graphSteps)
    const nodes: CanvasNode[] = [...flow.nodes]
    const edges = [...flow.edges]
    addLinkedRuns(graphSteps, links, nodes, edges)
    return { nodes: autoLayout(nodes, edges), edges }
}
