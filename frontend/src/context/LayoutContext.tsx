import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface LayoutWidthValue {
    wide: boolean
    setWide: (wide: boolean) => void
}

const LayoutWidthContext = createContext<LayoutWidthValue>({ wide: false, setWide: () => { } })

export function LayoutWidthProvider({ children }: { children: ReactNode }) {
    const [wide, setWide] = useState(false)
    return <LayoutWidthContext.Provider value={{ wide, setWide }}>{children}</LayoutWidthContext.Provider>
}

/**
 * 讓單一頁面把主內容區撐滿視窗（左側 nav 不受影響）。離開該頁時自動還原，
 * 所以呼叫端不用自己收尾。
 */
export function useWideLayout(enabled = true) {
    const { setWide } = useContext(LayoutWidthContext)
    useEffect(() => {
        setWide(enabled)
        return () => setWide(false)
    }, [enabled, setWide])
}

export function useLayoutWidth() {
    return useContext(LayoutWidthContext)
}
