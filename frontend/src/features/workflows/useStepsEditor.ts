import { useState } from 'react'
import { makeStep, type StepDraft } from './WorkflowStepsEditor'

export function useStepsEditor(initial: () => StepDraft[]) {
    const [steps, setSteps] = useState<StepDraft[]>(initial)

    function updateStep(uid: string, patch: Partial<StepDraft>) {
        setSteps((prev) => prev.map((s) => (s.uid === uid ? { ...s, ...patch } : s)))
    }

    function addStep() {
        setSteps((prev) => [...prev, makeStep(prev.length > 0 ? [prev[prev.length - 1].uid] : [])])
    }

    function removeStep(uid: string) {
        setSteps((prev) =>
            prev
                .filter((s) => s.uid !== uid)
                .map((s) => ({ ...s, dependsOnUids: s.dependsOnUids.filter((d) => d !== uid) })),
        )
    }

    function toggleDependsOn(uid: string, depUid: string) {
        setSteps((prev) =>
            prev.map((s) =>
                s.uid === uid
                    ? {
                        ...s,
                        dependsOnUids: s.dependsOnUids.includes(depUid)
                            ? s.dependsOnUids.filter((d) => d !== depUid)
                            : [...s.dependsOnUids, depUid],
                    }
                    : s,
            ),
        )
    }

    return { steps, updateStep, addStep, removeStep, toggleDependsOn }
}
