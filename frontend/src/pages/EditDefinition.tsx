import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { getDefinition } from '../lib/apiClient'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { hasUnsupportedSteps } from '../features/workflows/WorkflowStepsEditor'
import { WorkflowBuilder } from './WorkflowBuilder'

export function EditDefinition() {
    const { id } = useParams<{ id: string }>()
    const { data: definition, isLoading, isError } = useQuery({
        queryKey: ['definition', id],
        queryFn: () => getDefinition(id as string),
        enabled: !!id
    })

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-16">
                <Spinner />
            </div>
        )
    }

    if (isError || !definition) {
        return (
            <EmptyState
                title="Workflow not found"
                action={<Link to="/workflows" className="text-sm font-medium text-accent">Back to workflows</Link>}
            />
        )
    }

    if (hasUnsupportedSteps(definition.steps)) {
        return (
            <EmptyState
                title="這個 workflow 還不能用畫布編輯"
                description="它用到了 reduce_of，builder 目前不支援——在這裡存檔會把 reduce 設定洗掉。請先透過 API（PUT /definitions/{id}）修改。"
                action={
                    <Link to={`/definitions/${definition.id}`} className="text-sm font-medium text-accent">
                        Back to {definition.name}
                    </Link>
                }
            />
        )
    }

    // key：從一個定義的編輯頁直接跳到另一個時，builder 的內部狀態要整個重建
    return <WorkflowBuilder key={definition.id} definition={definition} />
}