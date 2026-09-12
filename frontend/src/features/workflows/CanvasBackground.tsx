import { Background, BackgroundVariant } from '@xyflow/react'

/**
 * 畫布底紋。兩種選擇：
 * - paper：兩層格線疊成方格紙（細格 16px，每 5 格一條粗線）
 * - dots：n8n 那種點陣
 * 兩張畫布共用，換風格只要改一個 prop。
 */
export function CanvasBackground({ variant = 'paper' }: { variant?: 'paper' | 'dots' }) {
    if (variant === 'dots') {
        return (
            <Background
                id="canvas-dots"
                variant={BackgroundVariant.Dots}
                gap={18}
                size={1.4}
                color="var(--color-canvas-grid-major)"
            />
        )
    }

    // 疊兩層 Background 要給不同的 id，否則 React Flow 的 pattern 會互相覆蓋
    return (
        <>
            <Background
                id="canvas-grid-minor"
                variant={BackgroundVariant.Lines}
                gap={16}
                lineWidth={1}
                color="var(--color-canvas-grid-minor)"
            />
            <Background
                id="canvas-grid-major"
                variant={BackgroundVariant.Lines}
                gap={80}
                lineWidth={1}
                color="var(--color-canvas-grid-major)"
            />
        </>
    )
}
