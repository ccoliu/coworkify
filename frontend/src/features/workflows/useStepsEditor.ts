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

    /** 畫布用：不自動接到前一個 step，回傳新 uid 讓呼叫端可以定位 / 選取它。 */
    function addStepOfType(taskType: string, payload: Record<string, unknown>, name: string): string {
        const step: StepDraft = { ...makeStep(), taskType, payload, name }
        setSteps((prev) => [...prev, step])
        return step.uid
    }

    function removeStep(uid: string) {
        setSteps((prev) =>
            prev
                .filter((s) => s.uid !== uid)
                .map((s) => ({
                    ...s,
                    dependsOnUids: s.dependsOnUids.filter((d) => d !== uid),
                    // 指向被刪掉的 step 的參照一起清乾淨，否則送出時後端會以
                    // 「branch_of / for_each 指向不存在的 step」擋下來
                    branchOfUid: s.branchOfUid === uid ? null : s.branchOfUid,
                    branchWhen: s.branchOfUid === uid ? null : s.branchWhen,
                    forEachUid: s.forEachUid === uid ? null : s.forEachUid,
                })),
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

    /** 畫布拉出一條邊。從 condition 的 true / false handle 拉出來時一併設定分支。 */
    function connectSteps(sourceUid: string, targetUid: string, branchWhen: 'true' | 'false' | null) {
        setSteps((prev) =>
            prev.map((s) => {
                if (s.uid !== targetUid) return s
                const dependsOnUids = s.dependsOnUids.includes(sourceUid)
                    ? s.dependsOnUids
                    : [...s.dependsOnUids, sourceUid]
                return branchWhen
                    ? { ...s, dependsOnUids, branchOfUid: sourceUid, branchWhen }
                    : { ...s, dependsOnUids }
            }),
        )
    }

    function disconnectSteps(sourceUid: string, targetUid: string) {
        setSteps((prev) =>
            prev.map((s) => {
                if (s.uid !== targetUid) return s
                const isBranchEdge = s.branchOfUid === sourceUid
                return {
                    ...s,
                    dependsOnUids: s.dependsOnUids.filter((d) => d !== sourceUid),
                    branchOfUid: isBranchEdge ? null : s.branchOfUid,
                    branchWhen: isBranchEdge ? null : s.branchWhen,
                }
            }),
        )
    }

    return { steps, updateStep, addStep, addStepOfType, removeStep, toggleDependsOn, connectSteps, disconnectSteps }
}
