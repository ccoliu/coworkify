/**
 * 顯示 task / workflow 的結果。JSON.stringify 會把字串裡的換行轉義成 \n，
 * 而 stdout、stderr、python 回傳的長文字正是最常看的東西，所以字串一律原樣輸出，
 * 只有結構化的值才走 JSON。
 */

function toText(value: unknown): string {
    if (typeof value === 'string') return value
    if (value === null || value === undefined) return String(value)
    if (typeof value !== 'object' || Array.isArray(value)) return JSON.stringify(value)

    return Object.entries(value as Record<string, unknown>)
        .map(([key, v]) => {
            const text = typeof v === 'string' ? v : JSON.stringify(v, null, 2)
            // 多行的值換行後縮排，才看得出哪一段屬於哪個欄位
            return text.includes('\n') ? `"${key}":\n${text.replace(/^/gm, '   ')}` : `"${key}": ${text}`
        })
        .join('\n')
}

export function JsonBlock({ value, className = '' }: { value: unknown; className?: string }) {
    return (
        <pre
            className={`max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-plane p-3 font-mono text-xs text-ink-secondary ${className}`}
        >
            {toText(value)}
        </pre>
    )
}