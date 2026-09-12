import { json } from '@codemirror/lang-json'
import { python } from '@codemirror/lang-python'
import { indentUnit } from '@codemirror/language'
import type { Extension } from '@codemirror/state'
import CodeMirror from '@uiw/react-codemirror'
import { useMemo } from 'react'
import { useTheme } from '../context/ThemeContext'

const LANGUAGES: Record<string, () => Extension> = {
    python,
    json,
}

interface Props {
    value: string
    onChange: (value: string) => void
    /** 後端 catalog 給的語法標記。認不得的值就只吃基本編輯功能，不會壞掉 */
    language?: string | null
    height?: string
}

export function CodeEditor({ value, onChange, language, height = '240px' }: Props) {
    const { theme } = useTheme()

    const extensions = useMemo(() => {
        const lang = language ? LANGUAGES[language] : undefined
        // Python 認縮排，固定 4 空格。Tab 鍵插入縮排是 @uiw 的 indentWithTab 預設行為
        const base = [indentUnit.of('    ')]
        return lang ? [lang(), ...base] : base
    }, [language])

    return (
        <div className="overflow-hidden rounded-lg border border-border">
            <CodeMirror
                value={value}
                onChange={onChange}
                theme={theme}
                extensions={extensions}
                height={height}
                basicSetup={{
                    lineNumbers: true,
                    foldGutter: false,
                    autocompletion: true,
                    bracketMatching: true,
                    closeBrackets: true,
                }}
            />
        </div>
    )
}
