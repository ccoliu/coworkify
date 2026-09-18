import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '../components/Card'

function Mono({ children }: { children: ReactNode }) {
    return <code className="rounded bg-plane px-1 py-0.5 font-mono text-xs text-ink">{children}</code>
}

function Code({ children }: { children: string }) {
    return (
        <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-plane p-3 font-mono text-xs text-ink-secondary">
            {children}
        </pre>
    )
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
    return (
        <Card className="scroll-mt-6 p-5" id={id}>
            <h2 className="mb-3 text-base font-semibold text-ink">{title}</h2>
            <div className="flex flex-col gap-3 text-sm leading-relaxed text-ink-secondary">{children}</div>
        </Card>
    )
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
                <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
                        {head.map((h) => (
                            <th key={h} className="px-3 py-2 font-medium">
                                {h}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, i) => (
                        <tr key={i} className="border-b border-border align-top last:border-0">
                            {row.map((cell, j) => (
                                <td key={j} className="px-3 py-2 text-ink-secondary">
                                    {cell}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

const SECTIONS = [
    ['concepts', 'Workflow 與 run'],
    ['example', '例子：價格警示'],
    ['task-types', '任務類型與屬性'],
    ['data', '資料怎麼在步驟之間流動'],
    ['retry', 'Retry 與 Re-run'],
    ['schedule', '設成定期執行'],
    ['troubleshooting', '卡住的時候'],
    ['api', '用 API 做同一件事'],
]

/** 每個步驟共通的屬性，不分任務類型；對應屬性面板由上而下的欄位順序。 */
const COMMON_FIELDS: [string, string][] = [
    ['Step key', '這一步的識別碼，其他步驟用它取值（inputs["<key>"]、{{steps.<key>.result}}）。只能用英數字與底線'],
    ['Name', '顯示用的名稱，可以隨意取；不影響取值'],
    ['Task type', '換類型會重設這一步的專屬欄位'],
    ['Priority', '0 最低，數字越大越優先被 worker 取走。預設 3'],
    ['Max retries', '這一步自己失敗時的重試次數，採指數退避。預設 3；用完才算整條 workflow 失敗'],
    ['Depends on', '在畫布上拉線就是依賴；上游全部成功後這一步才會被派送'],
    ['分支', '從 condition 節點的 true / false 出口拉線，等同設定 branch_of 與 branch_when'],
    ['For each', '指向一個結果是 list 的步驟，這一步會依項目逐一展開；payload 內用 {{item}} 取值'],
]

const TASK_TYPES: { type: string; label: string; summary: ReactNode; fields: [string, string, ReactNode][] }[] = [
    {
        type: 'input',
        label: 'Input',
        summary: (
            <>
                整條 workflow 的資料入口，每條最多一個，而且不能有上游。定義有宣告 Input fields
                時，執行前填的表單值會取代它的內容。
            </>
        ),
        fields: [['data', '選填', '一段 JSON 物件或陣列。沒有輸入欄位的定義才需要在這裡寫死值；可直接上傳 .json']],
    },
    {
        type: 'python',
        label: 'Python',
        summary: (
            <>
                在受限的 subprocess 裡執行 Python。定義 <Mono>main()</Mono>，它的回傳值會成為結果的{' '}
                <Mono>result.value</Mono>，不用自己 print。
            </>
        ),
        fields: [
            ['code', '必填', 'CodeMirror 編輯器，可放大成 modal 或上傳 .py。回傳值必須可 JSON 序列化'],
            ['timeout_seconds', '選填', '預設 10，上限 60'],
        ],
    },
    {
        type: 'shell',
        label: 'Shell',
        summary: <>在受限的 subprocess 裡執行 shell 指令，工作目錄是一個用完即丟的暫存目錄。</>,
        fields: [
            ['command', '必填', '多行指令可以直接換行寫'],
            ['timeout_seconds', '選填', '預設 10，上限 60'],
        ],
    },
    {
        type: 'http_request',
        label: 'HTTP Request',
        summary: <>發送一個 HTTP 請求，會擋掉指向內網或 cloud metadata endpoint 的目標。結果含狀態碼與回應內容。</>,
        fields: [
            ['url', '必填', <>要打的網址；可用 <Mono>{'{{steps...}}'}</Mono> 模板組出來</>],
            ['method', '選填', 'GET / POST / PUT / PATCH / DELETE，預設 GET'],
            ['timeout_seconds', '選填', '預設 10'],
        ],
    },
    {
        type: 'condition',
        label: 'Condition',
        summary: (
            <>
                評估一個條件，<strong className="text-ink">本身永遠成功</strong>，回傳{' '}
                <Mono>passed=true/false</Mono>。分支靠下游步驟指向它來達成，不是靠這一步失敗。
            </>
        ),
        fields: [
            [
                'left',
                '選填',
                <>
                    留空時自動帶入唯一那個上游的結果（上游是 python 就取 <Mono>main()</Mono>{' '}
                    的回傳值）。上游有多個時必填
                </>,
            ],
            ['operator', '必填', '= / ≠ / &gt; / ≥ / &lt; / ≤ / contains / is true / is empty 等'],
            ['right', '選填', 'is true、is false、is empty、is not empty 這幾個不需要填'],
        ],
    },
    {
        type: 'agent_step',
        label: 'Agent (Codoctopus)',
        summary: (
            <>
                執行一個 Codoctopus agent step。需要 worker 裝好 codoctopus，並以{' '}
                <Mono>docker compose --profile agent up</Mono> 啟動專屬的 worker-agent；否則這一步會一直停在 pending。
            </>
        ),
        fields: [
            ['role', '必填', 'system prompt，描述這個 agent 的身分與規則'],
            ['instruction', '必填', '這一步要它做的事'],
            ['model', '選填', <>格式 <Mono>provider:model</Mono>，例如 <Mono>anthropic:claude-opus-5</Mono>；留空用預設</>],
            ['tools', '選填', 'read_file / write_file / list_files / http_request / run_tests'],
            ['workspace', '選填', '留空用共用暫存目錄；同一條 workflow 的多個 agent step 要共用檔案時才指定'],
        ],
    },
]

export function GettingStarted() {
    return (
        <div className="flex flex-col gap-5">
            <div>
                <h1 className="text-lg font-semibold text-ink">Getting started</h1>
                <p className="mt-1 text-sm text-ink-muted">
                    用一個實際的例子走完「建一條 workflow → 執行 → 看結果 → 設成排程」。
                </p>
            </div>

            <Card className="p-4">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">目錄</p>
                <ol className="flex flex-col gap-0.5">
                    {SECTIONS.map(([id, label], i) => (
                        <li key={id}>
                            <a
                                href={`#${id}`}
                                className="flex items-baseline gap-2.5 py-1.5 text-sm text-ink-secondary hover:text-accent"
                            >
                                <span className="w-4 shrink-0 text-right font-mono text-xs text-ink-muted">
                                    {i + 1}
                                </span>
                                {label}
                            </a>
                        </li>
                    ))}
                </ol>
            </Card>

            <Section id="concepts" title="Workflow 與 run">
                <p>這是最容易混淆的一組概念：</p>
                <ul className="flex flex-col gap-2 pl-4">
                    <li className="list-disc">
                        <strong className="text-ink">Workflow（定義）</strong>
                        ：一條產線。畫布上的節點、連線、輸入欄位都屬於它，它本身不會執行。
                    </li>
                    <li className="list-disc">
                        <strong className="text-ink">Run（執行）</strong>
                        ：拿一批輸入把產線跑一次。每次 run 都會複製一份當下的定義，所以之後改了定義，舊的執行紀錄不會被改寫。
                    </li>
                </ul>
                <p>
                    <Link to="/workflows" className="text-accent hover:underline">
                        Workflows
                    </Link>{' '}
                    頁面上半部是定義，下半部的 Recent runs 是每一次執行。
                </p>
            </Section>

            <Section id="example" title="例子：價格警示">
                <p>填入價格與門檻，超過門檻走一條路，沒超過走另一條。這個例子涵蓋了輸入、程式判斷、條件分支，以及步驟之間怎麼傳資料。</p>
                <Code>{`input_1 ──> python_1 ──> condition_1 ──true──> shell_1（發出警示）
                                      └─false─> shell_2（記錄正常）`}</Code>

                <p className="mt-2 font-medium text-ink">1. 開一張新畫布</p>
                <p>
                    <Link to="/workflows/new" className="text-accent hover:underline">
                        New workflow
                    </Link>
                    ，名稱填 <Mono>price-alert</Mono>。
                </p>

                <p className="mt-2 font-medium text-ink">2. 定義輸入欄位</p>
                <p>
                    展開上方的 <strong className="text-ink">Input fields</strong>，加兩個欄位：
                </p>
                <Table
                    head={['Key', 'Label', 'Type', '必填', 'Default']}
                    rows={[
                        [<Mono>price</Mono>, '價格', '數字', '✔', ''],
                        [<Mono>threshold</Mono>, '門檻', '數字', '', <Mono>100</Mono>],
                    ]}
                />
                <p>
                    Key 只能用英數字與底線，而且<strong className="text-ink">大小寫敏感</strong>
                    ——下游是靠它取值的，Label 只是畫面上的顯示文字。
                </p>

                <p className="mt-2 font-medium text-ink">3. 拉出節點</p>
                <p>從左側面板把任務類型拖進畫布，再拉線接起來。線的方向就是依賴關係（資料往下游流）。</p>

                <p>
                    <Mono>input_1</Mono>（Input）— 整條 workflow 的資料入口。Input data 留著{' '}
                    <Mono>{'{}'}</Mono> 就好，執行時這一步的結果會被換成 Run 表單填的值。每條 workflow 只能有一個 input
                    step，而且它不能有上游。
                </p>

                <p>
                    <Mono>python_1</Mono>（Python）：
                </p>
                <Code>{`def main():
    data = inputs["input_1"]
    return data["price"] > data["threshold"]`}</Code>
                <p>
                    <Mono>inputs</Mono> 是自動提供的全域變數，內容是所有上游步驟的結果，型別完整保留（數字就是數字）。
                    <Mono>main()</Mono> 的回傳值就是這一步的結果。
                </p>

                <p>
                    <Mono>condition_1</Mono>（Condition）— Operator 選 <Mono>is true</Mono>，
                    <strong className="text-ink">Left 留空</strong>。留空時系統會自動帶入唯一那個上游的結果，所以它必須剛好只有一個上游；有兩個以上就得自己指定
                    Left，否則存檔會被擋下來。
                </p>

                <p>
                    <Mono>shell_1</Mono> / <Mono>shell_2</Mono>（Shell）— 從 condition_1 右側的{' '}
                    <Mono>true</Mono> 出口拉線到 shell_1、<Mono>false</Mono>{' '}
                    出口拉線到 shell_2。這個動作就等於設定了分支，不用另外填欄位。
                </p>
                <Code>{`# shell_1
echo "警示：價格 $(./get_input input_1.price) 高於門檻 $(./get_input input_1.threshold)"

# shell_2
echo "價格正常：$(./get_input input_1.price)"`}</Code>

                <p className="mt-2 font-medium text-ink">4. 執行</p>
                <p>
                    存檔後會跳到定義頁，右邊就是你剛才定義的 Run 表單。價格填 <Mono>150</Mono>、門檻留預設，按 Run
                    workflow。節點會隨執行狀態即時上色（WebSocket 推播，不用重新整理）：綠色是成功、紅色是失敗、灰色淡化是{' '}
                    <Mono>cancelled</Mono>。
                </p>
                <p>
                    這個例子跑完後 shell_2 會是 cancelled——
                    <strong className="text-ink">分支沒走到是預期結果，不是失敗</strong>，整條 workflow 仍然是 Success。
                    下方的 Result 收集的是所有終端節點（沒有其他步驟依賴它）的結果：
                </p>
                <Code>{`{
  "shell_1": {
    "stdout": "警示：價格 150 高於門檻 100\\n",
    "stderr": "",
    "exit_code": 0
  }
}`}</Code>
                <p>點任一節點可以看到它實際收到的 payload，包含系統塞給它的 inputs——排查「值到底有沒有傳進去」時先看這裡。</p>
            </Section>

            <Section id="data" title="資料怎麼在步驟之間流動">
                <Table
                    head={['步驟類型', '寫法', '說明']}
                    rows={[
                        [
                            <Mono>python</Mono>,
                            <Mono>{'inputs["input_1"]["price"]'}</Mono>,
                            <>
                                全域變數，型別完整保留。也可以寫成 <Mono>def main(inputs):</Mono>
                            </>,
                        ],
                        [
                            <Mono>shell</Mono>,
                            <Mono>{'$(./get_input input_1.price)'}</Mono>,
                            <>
                                點號路徑對應 python 的中括號；整包資料也在工作目錄的 <Mono>inputs.json</Mono>
                            </>,
                        ],
                        [
                            '其他',
                            <Mono>{'{{steps.input_1.result.price}}'}</Mono>,
                            'http_request、condition 等用字串模板，派送前代換',
                        ],
                    ]}
                />
                <ul className="flex flex-col gap-2 pl-4">
                    <li className="list-disc">
                        <Mono>inputs</Mono>{' '}
                        包含所有祖先，不只直接上游。分支底下的步驟也拿得到最前面 input step 的值，不必為此多拉一條線。
                    </li>
                    <li className="list-disc">
                        模板是<strong className="text-ink">字串插值</strong>，值裡有引號或{' '}
                        <Mono>$(...)</Mono> 會出事，型別也會變成文字。值來自 Run 表單時，優先用 inputs / get_input。
                    </li>
                    <li className="list-disc">
                        模板參照誰，就必須連線到誰——否則沒辦法保證它先執行，存檔會被擋下來。
                    </li>
                </ul>
                <p>
                    <Mono>input_1</Mono> 這種名字是 <strong className="text-ink">step key</strong>，在節點的屬性面板可以看到與修改。
                </p>
            </Section>

            <Section id="task-types" title="任務類型與屬性">
                <p>
                    這份清單由後端的 <Mono>app/tasks/catalog.py</Mono> 定義，透過{' '}
                    <Mono>GET /tasks/types</Mono> 提供欄位規格——畫布右側的屬性面板是照它動態產生的，
                    所以後端新增一種任務類型不需要改前端。
                </p>

                <p className="mt-2 font-medium text-ink">每個步驟共通的屬性</p>
                <Table head={['屬性', '說明']} rows={COMMON_FIELDS.map(([name, desc]) => [<Mono>{name}</Mono>, desc])} />

                {TASK_TYPES.map((t) => (
                    <div key={t.type} className="mt-3 flex flex-col gap-2">
                        <p className="font-medium text-ink">
                            {t.label} <span className="font-mono text-xs text-ink-muted">{t.type}</span>
                        </p>
                        <p>{t.summary}</p>
                        <Table
                            head={['欄位', '必填', '說明']}
                            rows={t.fields.map(([key, required, desc]) => [<Mono>{key}</Mono>, required, desc])}
                        />
                    </div>
                ))}

                <p className="mt-2">
                    早期的示範 handler（<Mono>echo</Mono>、<Mono>heavy_computation</Mono>、<Mono>flaky_task</Mono>{' '}
                    等）仍註冊在後端，既有資料與測試還在引用，但刻意不列進這份目錄，選單裡不會出現。
                </p>
            </Section>



            <Section id="retry" title="Retry 與 Re-run">
                <Table
                    head={['', '做什麼', '什麼時候用']}
                    rows={[
                        [
                            <strong className="text-ink">Retry failed steps</strong>,
                            '在同一次 run 上，把失敗的步驟與被它連帶取消的下游重設後續跑。已經成功的上游不會重跑',
                            '上游很花時間或很貴，只想修掉失敗那段',
                        ],
                        [
                            <strong className="text-ink">Re-run</strong>,
                            '用同一份定義快照與同一份輸入，建立一次新的 run',
                            '想留下兩次執行的對照，或只是想再跑一次',
                        ],
                    ]}
                />
                <p>
                    Retry 只在 workflow 狀態是 failed 時出現。沒走到的分支在 Retry 後仍然維持 cancelled，不會被誤喚醒。
                    單一步驟本身的重試（<Mono>max_retries</Mono>{' '}
                    加上指數退避）是自動的，上面兩個是重試都用完、整條 workflow 失敗之後的手段。
                </p>
            </Section>

            <Section id="schedule" title="設成定期執行">
                <p>
                    <Link to="/schedules" className="text-accent hover:underline">
                        Schedules
                    </Link>{' '}
                    → New schedule：選一條 workflow、填 cron 表達式（有「每天 9:00」等常用預設）、填這個排程每次要用的輸入。
                </p>
                <p>
                    排程<strong className="text-ink">指向定義本身</strong>
                    ，不是它現在的快照。之後改了那條 workflow，下次觸發就會自動用新版，不用回來改排程。也可以從任何一次 run
                    的詳情頁按 Schedule this workflow，直接沿用那次的輸入建立排程。
                </p>
            </Section>

            <Section id="troubleshooting" title="卡住的時候">
                <Table
                    head={['症狀', '多半是']}
                    rows={[
                        ['KeyError 或取到空值', 'key 打錯或大小寫不符。看節點 payload 裡的 inputs 實際長什麼樣'],
                        [
                            <>
                                shell 印出 <Mono>{'{{steps...}}'}</Mono> 原文
                            </>,
                            'shell 不吃 python 的 inputs 變數，但吃模板；反過來 python 不需要模板',
                        ],
                        [
                            <Mono>./get_input: not found</Mono>,
                            '這一步沒有上游，所以沒有 inputs.json，工具也不會被放進去',
                        ],
                        ['存檔鈕是灰的', '看畫布上方的錯誤清單，點任一條會跳到對應節點'],
                        [
                            '改了程式碼但行為沒變',
                            <>
                                改的若是 <Mono>app/tasks/</Mono> 底下的檔案，要{' '}
                                <Mono>docker compose restart worker worker-agent beat</Mono>，Celery worker 不會自動重載
                            </>,
                        ],
                        [
                            <>
                                用到 <Mono>reduce_of</Mono> 的定義不能在畫布編輯
                            </>,
                            <>
                                畫布還不支援 reduce，請用 <Mono>PUT /definitions/{'{id}'}</Mono> 修改
                            </>,
                        ],
                    ]}
                />
                <p>
                    <span className="text-status-warning">黃色的提示是警告</span>
                    ，不擋存檔，只是告訴你有更好的寫法（例如 python 裡還在用模板）。
                </p>
            </Section>

            <Section id="api" title="用 API 做同一件事">
                <p>
                    介面上的每個動作都有對應的 API，在{' '}
                    <a
                        href="http://localhost:8000/docs"
                        target="_blank"
                        rel="noreferrer"
                        className="text-accent hover:underline"
                    >
                        Swagger UI
                    </a>{' '}
                    可以直接試。先用 <Mono>POST /auth/login</Mono> 拿 token，按右上角 Authorize 貼上（不要加{' '}
                    <Mono>Bearer </Mono> 前綴）。
                </p>
                <p className="font-medium text-ink">建立定義</p>
                <Code>{`POST /definitions/
{
  "name": "price-alert",
  "input_schema": [
    {"key": "price", "label": "價格", "kind": "number", "required": true},
    {"key": "threshold", "label": "門檻", "kind": "number", "default": 100}
  ],
  "steps": [
    {"key": "input_1", "name": "input", "task_type": "input",
     "payload": {"data": "{}"}, "depends_on": []},
    {"key": "python_1", "name": "compare", "task_type": "python",
     "payload": {"code": "def main():\\n    data = inputs['input_1']\\n    return data['price'] > data['threshold']"},
     "depends_on": ["input_1"]},
    {"key": "condition_1", "name": "over threshold?", "task_type": "condition",
     "payload": {"operator": "is_true"}, "depends_on": ["python_1"]},
    {"key": "shell_1", "name": "alert", "task_type": "shell",
     "payload": {"command": "echo \\"警示\\""},
     "depends_on": ["condition_1"], "branch_of": "condition_1", "branch_when": "true"},
    {"key": "shell_2", "name": "ok", "task_type": "shell",
     "payload": {"command": "echo \\"價格正常\\""},
     "depends_on": ["condition_1"], "branch_of": "condition_1", "branch_when": "false"}
  ]
}`}</Code>
                <p className="font-medium text-ink">執行一次</p>
                <Code>{`POST /definitions/{definition_id}/runs
{"input": {"price": 150}}`}</Code>
                <p>
                    沒填的 threshold 會自動補上預設值 100。回應就是這次 run，用{' '}
                    <Mono>GET /workflows/{'{run_id}'}</Mono> 查它的狀態與 result。其他常用的：
                    <Mono>GET /definitions/{'{id}'}/runs</Mono> 列出執行紀錄、
                    <Mono>PUT /definitions/{'{id}'}</Mono> 整份取代定義（版本號自動 +1）、
                    <Mono>POST /workflows/{'{id}'}/rerun</Mono> 與 <Mono>/retry</Mono>。
                </p>
            </Section>
        </div>
    )
}
