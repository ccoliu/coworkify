import '@xyflow/react/dist/style.css'
import {
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
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '../../components/Button'
import { useTheme } from '../../context/ThemeContext'
import { CanvasBackground } from './CanvasBackground'
import { autoLayout, stepsFromDrafts, toFlow, wouldCreateCycle, type StepNode } from './graphModel'
import { TASK_TYPE_DRAG_MIME } from './TaskTypePalette'
import { workflowNodeTypes } from './WorkflowNodes'
import type { StepDraft } from './WorkflowStepsEditor'

interface Props {
    steps: StepDraft[]
    selectedUid: string | null
    issues: Map<string, string[]>
    onSelect: (uid: string | null) => void
    /** 回傳新 step 的 uid，畫布用它把節點放在游標位置 */
    onAddStep: (taskType: string) => string
    /** 回傳複製出來的新 step uid，畫布負責把它放在原節點旁邊 */
    onDuplicateStep: (uid: string) => string | null
    onRemoveStep: (uid: string) => void
    onConnectSteps: (source: string, target: string, branchWhen: 'true' | 'false' | null) => void
    onDisconnectSteps: (source: string, target: string) => void
    onInvalid: (message: string) => void
    /** 載入既有定義時為 true：第一次拿到 steps 就自動排版一次（新建的空白畫布不需要） */
    autoLayoutOnLoad?: boolean
}

/** 使用者正在打字時不該觸發畫布快捷鍵。CodeMirror 的編輯區不是 textarea，要另外判斷。 */
function isTypingTarget(target: EventTarget | null): boolean {
    const el = target as HTMLElement | null
    if (!el || typeof el.closest !== 'function') return false
    if (el.isContentEditable) return true
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) return true
    return el.closest('.cm-editor') != null
}

function BuilderCanvas({
    steps,
    selectedUid,
    issues,
    onSelect,
    onAddStep,
    onDuplicateStep,
    onRemoveStep,
    onConnectSteps,
    onDisconnectSteps,
    onInvalid,
    autoLayoutOnLoad
}: Props) {
    const [nodes, setNodes, onNodesChange] = useNodesState<StepNode>([])
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
    // 選取狀態完全由我們自己管：同步 effect 每次都會重建 nodes / edges，
    // React Flow 內建的 selected 旗標會被洗掉，靠它做刪除並不可靠。
    const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
    const { screenToFlowPosition, fitView } = useReactFlow()
    const pendingPositions = useRef(new Map<string, XYPosition>())
    const { theme } = useTheme()
    const didInitialLayout = useRef(false);

    useEffect(() => {
        const graph = toFlow(stepsFromDrafts(steps))
        // 判斷放在 updater 外面：StrictMode 會把 updater 呼叫兩次，
        // 在裡面改 ref 的話第二次會看到 true、回傳沒排版的結果
        const layoutNow = autoLayoutOnLoad && !didInitialLayout.current && steps.length > 0
        if (layoutNow) didInitialLayout.current = true

        setNodes((prev) => {
            const prevById = new Map(prev.map((n) => [n.id, n]))
            const next = graph.nodes.map((n, i) => {
                const pending = pendingPositions.current.get(n.id)
                if (pending) pendingPositions.current.delete(n.id)
                return {
                    ...n,
                    position: prevById.get(n.id)?.position ?? pending ?? { x: 40 + i * 40, y: 40 + i * 40 },
                    data: { ...n.data, selected: n.id === selectedUid, issues: issues.get(n.id) ?? [] },
                }
            })
            return layoutNow ? autoLayout(next, graph.edges) : next
        })
        if (layoutNow) window.setTimeout(() => fitView({ padding: 0.18, maxZoom: 1 }), 0)


        setEdges(
            graph.edges.map((e) =>
                e.id === selectedEdgeId
                    ? {
                        ...e,
                        style: { ...e.style, stroke: 'var(--color-accent)', strokeWidth: 2.5 },
                        markerEnd:
                            typeof e.markerEnd === 'object' && e.markerEnd !== null
                                ? { ...e.markerEnd, color: 'var(--color-accent)' }
                                : e.markerEnd,
                    }
                    : e,
            ),
        )
    }, [steps, selectedUid, selectedEdgeId, issues, setNodes, setEdges, autoLayout, fitView])

    const selectNode = useCallback(
        (uid: string | null) => {
            setSelectedEdgeId(null)
            onSelect(uid)
        },
        [onSelect],
    )

    const addAt = useCallback(
        (taskType: string, position: XYPosition) => {
            const uid = onAddStep(taskType)
            pendingPositions.current.set(uid, position)
            selectNode(uid)
        },
        [onAddStep, selectNode],
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

    const removeEdge = useCallback(
        (edgeId: string) => {
            const edge = edges.find((e) => e.id === edgeId)
            if (!edge) return
            if (edge.data?.kind !== 'depends') {
                onInvalid('for_each / reduce 的關聯要在右側屬性面板調整，不能直接刪線')
                return
            }
            onDisconnectSteps(edge.source, edge.target)
            setSelectedEdgeId(null)
        },
        [edges, onDisconnectSteps, onInvalid],
    )

    const runAutoLayout = useCallback(() => {
        setNodes((prev) => autoLayout(prev, edges))
        // 重排後畫面要跟上，等 state 落地再 fitView
        window.setTimeout(() => fitView({ padding: 0.18, maxZoom: 1 }), 0)
    }, [edges, fitView, setNodes])

    const duplicate = useCallback(
        (uid: string) => {
            const source = nodes.find((n) => n.id === uid)
            const newUid = onDuplicateStep(uid)
            if (!newUid) return
            if (source) {
                pendingPositions.current.set(newUid, {
                    x: source.position.x + 48,
                    y: source.position.y + 72,
                })
            }
            selectNode(newUid)
        },
        [nodes, onDuplicateStep, selectNode],
    )

    // 快捷鍵。掛在 document 上而不是畫布 div，使用者才不用先點畫布一下才生效；
    // 正在打字時一律略過。
    useEffect(() => {
        function onKeyDown(event: KeyboardEvent) {
            if (isTypingTarget(event.target)) return

            if (event.key === 'Delete' || event.key === 'Backspace') {
                if (selectedEdgeId) {
                    event.preventDefault()
                    removeEdge(selectedEdgeId)
                } else if (selectedUid) {
                    event.preventDefault()
                    onRemoveStep(selectedUid)
                }
                return
            }

            if (event.key === 'Escape') {
                setSelectedEdgeId(null)
                onSelect(null)
                return
            }

            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd') {
                if (!selectedUid) return
                event.preventDefault() // 蓋掉瀏覽器的「加入書籤」
                duplicate(selectedUid)
                return
            }

            if (event.ctrlKey || event.metaKey || event.altKey) return

            if (event.key.toLowerCase() === 'l') runAutoLayout()
            else if (event.key.toLowerCase() === 'f') fitView({ padding: 0.18, maxZoom: 1 })
        }

        document.addEventListener('keydown', onKeyDown)
        return () => document.removeEventListener('keydown', onKeyDown)
    }, [selectedEdgeId, selectedUid, removeEdge, onRemoveStep, onSelect, duplicate, runAutoLayout, fitView])

    const isValidConnection = useCallback(
        (c: Connection | Edge) => {
            if (!c.source || !c.target || c.source === c.target) return false
            const target = steps.find((s) => s.uid === c.target)
            const source = steps.find((s) => s.uid === c.source)
            if (!target || !source) return false
            // 展開步驟只能依賴同一組的其他展開步驟（跟舊表單同一條規則）
            if ((target.forEachUid ?? null) !== (source.forEachUid ?? null)) return false
            if (target.dependsOnUids.includes(c.source)) return false
            return !wouldCreateCycle(stepsFromDrafts(steps), c.source, c.target)
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
        [onConnectSteps],
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
                onNodeClick={(_, node) => selectNode(node.id)}
                onEdgeClick={(_, edge) => {
                    onSelect(null)
                    setSelectedEdgeId(edge.id)
                }}
                onEdgeDoubleClick={(_, edge) => removeEdge(edge.id)}
                onPaneClick={() => selectNode(null)}
                onConnectEnd={(_, state) => {
                    if (!state.isValid) onInvalid('這條連線不合法：會造成循環、重複，或跨越 for_each 分組')
                }}
                fitView
                fitViewOptions={{ padding: 0.18, maxZoom: 1 }}
                minZoom={0.2}
                maxZoom={1.75}
                // 刪除一律走我們自己的快捷鍵處理，避免跟 RF 內部選取狀態打架
                deleteKeyCode={null}
                proOptions={{ hideAttribution: false }}
            >
                <CanvasBackground variant="dots" />
                <Controls showInteractive={false} />
                <MiniMap pannable zoomable style={{ backgroundColor: 'var(--color-surface)' }} />

                <Panel position="top-right">
                    <Button variant="secondary" onClick={runAutoLayout}>
                        Auto layout
                    </Button>
                </Panel>

                {selectedEdgeId && (
                    <Panel position="top-center">
                        <button
                            type="button"
                            onClick={() => removeEdge(selectedEdgeId)}
                            className="mt-2 rounded-lg border border-status-critical/40 bg-surface px-3 py-1.5 text-xs font-medium text-status-critical shadow-sm hover:bg-status-critical hover:text-white"
                        >
                            ✕ 移除這條連線（Delete）
                        </button>
                    </Panel>
                )}

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
