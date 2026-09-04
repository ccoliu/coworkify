import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listSchedules } from '../lib/apiClient'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Spinner } from '../components/Spinner'
import { CreateScheduleModal } from '../features/schedules/CreateScheduleModal'
import { ScheduleTable } from '../features/schedules/ScheduleTable'

export function Schedules() {
    const [showCreate, setShowCreate] = useState(false)

    const { data: schedules, isLoading, isError } = useQuery({
        queryKey: ['schedules'],
        queryFn: listSchedules,
    })

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-semibold text-ink">Schedules</h1>
                    <p className="text-sm text-ink-muted">
                        Run a workflow automatically on a recurring cron schedule.
                    </p>
                </div>
                <Button variant="primary" onClick={() => setShowCreate(true)}>
                    New schedule
                </Button>
            </div>

            <Card>
                {isLoading ? (
                    <div className="flex items-center justify-center py-16">
                        <Spinner />
                    </div>
                ) : isError ? (
                    <div className="px-6 py-16 text-center text-sm text-status-critical">
                        Failed to load schedules.
                    </div>
                ) : (
                    <ScheduleTable schedules={schedules ?? []} />
                )}
            </Card>

            {showCreate && <CreateScheduleModal onClose={() => setShowCreate(false)} />}
        </div>
    )
}
