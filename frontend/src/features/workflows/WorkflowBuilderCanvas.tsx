import '@xyflow/react/dist/style.css'
import {
    Background,
    BackgroundVariant,
    Controls,
    MiniMap,
    Panel,
    ReactFlow,
    ReactFlowProvider,
    useEdgesState,
    useNodesState,
    useReactFlow,
    type Connection,
    type Edge,
    type XYPosition,
} from '@xyflow/react'
import { useCallback, useEffect, useRef } from 'react'
import { Button } from '../../components/Button'
import { autoLayout, stepsFromDrafts, toFlow, wouldCreateCycle, type StepNode } from './graphModel'
import { TASK_TYPE_DRAG_MIME } from './TaskTypePalette'
import { workflowNodeTypes } from './WorkflowNodes'
import type { StepDraft } from './WorkflowStepsEditor'
import { useTheme } from '../../context/ThemeContext'
import { CanvasBackground } from './CanvasBackground'


interface Props {
    steps: StepDraft[]
    selectedUid: string | null
    onSelect: (uid: string | null) => void
    /** 回傳新 step 的 uid，畫布用它把節點放在游標位置 */
    onAddStep: (taskType: string) => string
    onRemoveStep: (uid: string) => void
    onConnectSteps: (source: string, target: string, branchWhen: 'true' | 'false' | null) => void
    onDisconnectSteps: (source: string, target: string) => void
    onInvalid: (message: string) => void
}


function BuilderCanvas({
    steps,
    selectedUid,
    onSelect,
    onAddStep,
    onRemoveStep,
    onConnectSteps,
    onDisconnectSteps,
    onInvalid,
}: Props) {
    const [nodes, setNodes, onNodesChange] = useNodesState<StepNode>([])
    const [edges, setEdges, onEdgesChange] = useEdgesState([])
    const { screenToFlowPosition, fitView } = useReactFlow()
    // 新加的 step 要放的位置。addStepOfType 是同步回傳 uid 的，所以可以先記起來，
    // 等下面的同步 effect 建節點時取用。
    const pendingPositions = useRef(new Map<string, XYPosition>())
    const { theme } = useTheme()

    // steps 是唯一真相，節點 / 邊每次都從它重建；只有座標沿用畫布上現有的，
    // 這樣使用者拖過的位置不會在每次編輯後被打回原形。
    useEffect(() => {
        const graph = toFlow(stepsFromDrafts(steps))
        setNodes((prev) => {
            const prevById = new Map(prev.map((n) => [n.id, n]))
            return graph.nodes.map((n, i) => {
                const pending = pendingPositions.current.get(n.id)
                if (pending) pendingPositions.current.delete(n.id)
                return {
                    ...n,
                    position: prevById.get(n.id)?.position ?? pending ?? { x: 40 + i * 40, y: 40 + i * 40 },
                    data: { ...n.data, selected: n.id === selectedUid },
                }
            })
        })
        setEdges(graph.edges)
    }, [steps, selectedUid, setNodes, setEdges])

    const addAt = useCallback(
        (taskType: string, position: XYPosition) => {
            const uid = onAddStep(taskType)
            pendingPositions.current.set(uid, position)
            onSelect(uid)
        },
        [onAddStep, onSelect],
    )

    const onDrop = useCallback(
        (event: React.DragEvent) => {
            event.preventDefault()
            const taskType = event.dataTransfer.getData(TASK_TYPE_DRAG_MIME)
            if (!taskType) return
            addAt(taskType, screenToFlowPosition({ x: event.clientX, y: event.clientY }))
        },
        [addAt, screenToFlowPosition],
    )

    const isValidConnection = useCallback(
        (c: Connection | Edge) => {
            if (!c.source || !c.target || c.source === c.target) return false
            const graph = stepsFromDrafts(steps)
            const target = steps.find((s) => s.uid === c.target)
            const source = steps.find((s) => s.uid === c.source)
            if (!target || !source) return false
            // 展開步驟只能依賴同一組的其他展開步驟（跟舊表單同一條規則）
            if ((target.forEachUid ?? null) != (source.forEachUid ?? null)) return false
            if (target.dependsOnUids.includes(c.source)) return false
            return !wouldCreateCycle(graph, c.source, c.target)
        },
        [steps],
    )

    const handleConnect = useCallback(
        (c: Connection) => {
            if (!c.source || !c.target) return
            // 從 condition 的 true / false handle 拉出來，就等於設定了 branch_of / branch_when
            const branchWhen = c.sourceHandle === 'true' || c.sourceHandle === 'false' ? c.sourceHandle : null
            onConnectSteps(c.source, c.target, branchWhen)
        },
        [onConnectSteps]
    )

    return (
        <div className="h-full w-full" onDrop={onDrop} onDragOver={(e) => e.preventDefault()}>
            <ReactFlow<StepNode>
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={workflowNodeTypes}
                colorMode={theme}
                style={{ backgroundColor: 'var(--color-canvas)' }}
                onConnect={handleConnect}
                isValidConnection={isValidConnection}
                onNodeClick={(_, node) => onSelect(node.id)}
                onPaneClick={() => onSelect(null)}
                onNodesDelete={(deleted) => deleted.forEach((n) => onRemoveStep(n.id))}
                onEdgesDelete={(deleted) =>
                    deleted.forEach((e) => {
                        if (e.data?.kind === 'depends') onDisconnectSteps(e.source, e.target)
                    })
                }
                onConnectEnd={(_, state) => {
                    if (!state.isValid) onInvalid('這條連線不合法：會造成循環、重複，或跨越 for_each 分組')
                }}
                fitView
                fitViewOptions={{ padding: 0.18, maxZoom: 1 }}
                minZoom={0.2}
                maxZoom={1.75}
                deleteKeyCode={['Backspace', 'Delete']}
                proOptions={{ hideAttribution: false }}
            >
                <CanvasBackground variant='dots' />
                <Controls showInteractive={false} />
                <MiniMap pannable zoomable style={{ backgroundColor: 'var(--color-surface)' }} />

                <Panel position="top-right">
                    <Button
                        variant="secondary"
                        onClick={() => {
                            setNodes((prev) => autoLayout(prev, edges))
                            // 重排後畫面要跟上，等 state 落地再 fitView
                            window.setTimeout(() => fitView({ padding: 0.18, maxZoom: 1 }), 0)
                        }}
                    >
                        Auto layout
                    </Button>
                </Panel>

                {steps.length === 0 && (
                    <Panel position="top-center">
                        <p className="mt-16 rounded-lg border border-dashed border-border px-4 py-3 text-sm text-ink-muted">
                            從左邊拖一個 task type 進來開始
                        </p>
                    </Panel>
                )}
            </ReactFlow>
        </div>
    )
}

export function WorkflowBuilderCanvas(props: Props) {
    // screenToFlowPosition 需要 provider，包在這裡讓頁面不用管
    return (
        <ReactFlowProvider>
            <BuilderCanvas {...props} />
        </ReactFlowProvider>
    )
}