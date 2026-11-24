import '@xyflow/react/dist/style.css'
import { useTheme } from '../../context/ThemeContext'

import {
    Controls,
    MiniMap,
    ReactFlow,
    useEdgesState,
    useNodesState,
    type Edge,
} from '@xyflow/react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import type { LinkedRun, TaskStatus, WorkflowStep } from '../../lib/types'
import { buildWorkflowGraph, type CanvasNode } from './graphModel'
import { workflowNodeTypes } from './WorkflowNodes'
import { CanvasBackground } from './CanvasBackground'

const MINIMAP_COLOR: Record<TaskStatus, string> = {
    pending: 'var(--color-baseline)',
    running: 'var(--color-accent)',
    retrying: 'var(--color-status-warning)',
    waiting: 'var(--color-accent)',
    success: 'var(--color-status-good)',
    failed: 'var(--color-status-critical)',
    cancelled: 'var(--color-gridline)',
}

interface Props {
    steps: WorkflowStep[]
    selectedTaskId: string | null
    onSelect: (taskId: string | null) => void
    // workflow 觸發器串起來的上下游 run，畫在兩側
    upstreamRun?: LinkedRun | null
    downstreamRuns?: LinkedRun[]
    // 這是子 run 時：呼叫它的 run 與步驟名稱，畫在最左邊
    parentRun?: LinkedRun | null
    parentStepName?: string | null
}

export function WorkflowCanvas({
    steps,
    selectedTaskId,
    onSelect,
    upstreamRun,
    downstreamRuns,
    parentRun,
    parentStepName,
}: Props) {
    const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>([])
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
    const { theme } = useTheme()
    const navigate = useNavigate()

    // steps 每次 refetch 都是新物件，所以這裡會重算——但 dagre 對同一組 DAG 是
    // 決定性的，只有狀態變的時候節點不會位移。選取狀態也一起重建，免得 refetch
    // 把高亮洗掉。

    useEffect(() => {
        const graph = buildWorkflowGraph(steps, {
            upstream: upstreamRun,
            downstream: downstreamRuns,
            parent: parentRun,
            parentStepName,
        })
        setNodes(
            graph.nodes.map((n) =>
                n.type !== 'run' && n.id === selectedTaskId ? { ...n, data: { ...n.data, selected: true } } : n,
            ),
        )
        setEdges(graph.edges)
    }, [steps, upstreamRun, downstreamRuns, parentRun, parentStepName, selectedTaskId, setNodes, setEdges])

    return (
        <ReactFlow<CanvasNode>
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={workflowNodeTypes}
            onNodeClick={(_, node) => {
                // 上下游 run 的節點：跳到那個 run；其他是這個 run 自己的步驟，打開詳細面板
                if (node.type === 'run') navigate(`/workflows/${node.data.runId}`)
                else onSelect(node.id)
            }}
            onPaneClick={() => onSelect(null)}
            colorMode={theme}
            style={{ backgroundColor: 'var(--color-canvas)' }}
            fitView
            fitViewOptions={{ padding: 0.18, maxZoom: 1 }}
            minZoom={0.2}
            maxZoom={1.75}
            // Phase 1 是唯讀檢視：不能拖、不能連線，只能看跟點
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            edgesFocusable={false}
            proOptions={{ hideAttribution: false }}
        >
            <CanvasBackground variant='dots' />
            <Controls showInteractive={false} />
            <MiniMap
                pannable
                zoomable
                style={{ backgroundColor: 'var(--color-surface)' }}
                maskColor="color-mix(in srgb, var(--color-plane) 70%, transparent)"
                nodeColor={(n) => MINIMAP_COLOR[(n.data as { status: TaskStatus | null }).status ?? 'pending']}
            />
        </ReactFlow>
    )
}