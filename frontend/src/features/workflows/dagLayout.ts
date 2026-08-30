import type { WorkflowStep } from '../../lib/types'

export function computeLevels(steps: WorkflowStep[]): WorkflowStep[][] {
    const byTaskId = new Map(steps.map((s) => [s.task_id, s]))
    const levelCache = new Map<string, number>()

    function levelOf(step: WorkflowStep): number {
        const cached = levelCache.get(step.task_id)
        if (cached !== undefined) return cached
        if (step.depends_on.length === 0) {
            levelCache.set(step.task_id, 0)
            return 0
        }
        const level =
            1 +
            Math.max(
                ...step.depends_on.map((depId) => {
                    const depStep = byTaskId.get(depId)
                    return depStep ? levelOf(depStep) : 0
                }),
            )
        levelCache.set(step.task_id, level)
        return level
    }

    const maxLevel = Math.max(0, ...steps.map(levelOf))
    const levels: WorkflowStep[][] = Array.from({ length: maxLevel + 1 }, () => [])
    for (const step of steps) {
        levels[levelOf(step)].push(step)
    }
    return levels
}
