import '@xyflow/react/dist/style.css'
import { useTheme } from '../../context/ThemeContext'

import {
    Background,
    BackgroundVariant,
    Controls,
    MiniMap,
    ReactFlow,
    useEdgesState,
    useNodesState,
    type Edge,
} from '@xyflow/react'
import { useEffect } from 'react'
import type { TaskStatus, WorkflowStep } from '../../lib/types'
import { buildWorkflowGraph, type StepNode, type StepNodeData } from './graphModel'
import { workflowNodeTypes } from './WorkflowNodes'
import { CanvasBackground } from './CanvasBackground'

const MINIMAP_COLOR: Record<TaskStatus, string> = {
    pending: 'var(--color-baseline)',
    running: 'var(--color-accent)',
    retrying: 'var(--color-status-warning)',
    success: 'var(--color-status-good)',
    failed: 'var(--color-status-critical)',
    cancelled: 'var(--color-gridline)',
}

interface Props {
    steps: WorkflowStep[]
    selectedTaskId: string | null
    onSelect: (taskId: string | null) => void
}

export function WorkflowCanvas({ steps, selectedTaskId, onSelect }: Props) {
    const [nodes, setNodes, onNodesChange] = useNodesState<StepNode>([])
    const [edges, setEdges, onEdgesChange] = useEdgesState([])
    const { theme } = useTheme()

    // steps 每次 refetch 都是新物件，所以這裡會重算——但 dagre 對同一組 DAG 是
    // 決定性的，只有狀態變的時候節點不會位移。選取狀態也一起重建，免得 refetch
    // 把高亮洗掉。

    useEffect(() => {
        const graph = buildWorkflowGraph(steps)
        setNodes(
            graph.nodes.map((n) =>
                n.id === selectedTaskId ? { ...n, data: { ...n.data, selected: true } } : n,
            ),
        )
        setEdges(graph.edges)
    }, [steps, selectedTaskId, setNodes, setEdges])

    return (
        <ReactFlow<StepNode>
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={workflowNodeTypes}
            onNodeClick={(_, node) => onSelect(node.id)}
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
                nodeColor={(n) => MINIMAP_COLOR[(n.data as StepNodeData).status ?? 'pending']}
            />
        </ReactFlow>
    )
}