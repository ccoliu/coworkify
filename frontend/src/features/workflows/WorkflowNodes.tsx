import { Handle, Position, type NodeProps, type NodeTypes } from '@xyflow/react'
import clsx from 'clsx'
import { StatusBadge } from '../../components/StatusBadge'
import type { TaskStatus } from '../../lib/types'
import { NODE_WIDTH, type StepNode, type StepNodeData } from './graphModel'
import { PythonIcon, BashIcon, WebIcon, SplitIcon, RobotIcon, BiImportIcon } from '../../components/Icon'

const STATUS_BORDER: Record<TaskStatus, string> = {
    pending: 'border-border',
    running: 'border-accent ring-2 ring-accent/20',
    retrying: 'border-status-warning',
    success: 'border-status-good',
    failed: 'border-status-critical ring-2 ring-status-critical/15',
    cancelled: 'border-border opacity-55'
}

// 用 inline style 而不是 class：React Flow 自己的 .react-flow__handle 權重較高，
// 走 style 可以完全不用跟它拚 specificity。
const HANDLE_STYLE = {
    width: 8,
    height: 8,
    border: 'none',
    background: 'var(--color-baseline)',
} as const

function shellClass(data: StepNodeData) {
    return clsx(
        'rounded-lg border bg-surface px-3 py-2.5 shadow-sm transition-shadow',
        // 驗證問題優先於執行狀態：還沒送出的圖，狀態一律是 pending，沒什麼好顯示的
        data.issues.length > 0 ? 'border-status-critical' : STATUS_BORDER[data.status ?? 'pending'],
        data.selected && 'ring-2 ring-accent',
    )
}

function NodeHeader({ data }: { data: StepNodeData }) {
    return (
        <>
            <div className="flex items-center gap-1.5">
                {data.taskType === 'condition' && <span className="text-xs text-status-warning">◆</span>}
                <span className="truncate text-sm font-medium text-ink" title={data.label}>
                    {data.label}
                </span>
                {data.isReduce && (
                    <span className="shrink-0 rounded bg-plane px-1 font-mono text-[10px] text-ink-muted">
                        reduce
                    </span>
                )}
                {data.issues.length > 0 && (
                    <span
                        title={data.issues.join('\n')}
                        className="ml-auto shrink-0 rounded-full bg-status-critical px-1.5 text-[10px] font-bold text-white"
                    >
                        {data.issues.length}
                    </span>
                )}
            </div>
            <div className="mt-1 flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs text-ink-muted">{data.taskType}</span>
                <StatusBadge status={data.status ?? 'pending'} />
            </div>
        </>
    )
}

export function TaskNode({ data }: NodeProps<StepNode>) {
    return (
        <div style={{ width: NODE_WIDTH }} className={shellClass(data)}>
            <div className="flex items-center gap-1.5">
                {data.taskType === 'input' && <BiImportIcon />}
                {data.taskType === 'python' && <PythonIcon />}
                {data.taskType === 'http_request' && <WebIcon />}
                {data.taskType === 'shell' && <BashIcon />}
                {data.taskType === 'agent_step' && <RobotIcon />}
            </div>
            {/* input 是 workflow 的資料入口，沒有上游，不畫接點 */}
            {data.taskType !== 'input' && (
                <Handle type="target" position={Position.Left} style={HANDLE_STYLE} />
            )}
            <NodeHeader data={data} />
            <Handle type="source" position={Position.Right} style={HANDLE_STYLE} />
        </div>
    )
}

function BranchOutput({ when }: { when: 'true' | 'false' }) {
    const color = when === 'true' ? 'var(--color-status-good)' : 'var(--color-ink-muted)'
    return (
        <div className="relative flex items-center justify-end py-0.5">
            <span className="font-mono text-[10px] uppercase tracking-wide" style={{ color }}>
                {when}
            </span>
            <Handle
                id={when}
                type="source"
                position={Position.Right}
                style={{
                    ...HANDLE_STYLE,
                    background: color,
                    position: 'absolute',
                    // 卡片有 12px 的左右 padding，-16 剛好讓 handle 騎在節點邊框上
                    right: -16,
                    top: '50%',
                    transform: 'translateY(-50%)',
                }}
            />
        </div>
    )
}

export function ConditionNode({ data, isConnectable }: NodeProps<StepNode>) {
    return (
        <div style={{ width: NODE_WIDTH }} className={shellClass(data)}>
            <div className="flex items-center gap-1.5">
                {data.taskType === 'condition' && <SplitIcon />}
            </div>
            <Handle type="target" position={Position.Left} style={HANDLE_STYLE} />
            <NodeHeader data={data} />
            <div className="mt-2 border-t border-border pt-1">
                <BranchOutput when="true" />
                <BranchOutput when="false" />
            </div>
            {/* 給「只是依賴這個 condition、沒有做分支」的下游用的錨點，不顯示 */}
            <Handle
                id="out"
                type="source"
                position={Position.Right}
                style={{
                    ...HANDLE_STYLE,
                    opacity: isConnectable ? 0.45 : 0,
                    pointerEvents: isConnectable ? 'auto' : 'none',
                }}
            />
        </div>
    )
}

// nodeTypes 一定要是模組層級常數，每次 render 產生新物件 React Flow 會整組重掛。
export const workflowNodeTypes = {
    task: TaskNode,
    condition: ConditionNode,
} satisfies NodeTypes