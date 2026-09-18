# 開始使用 Coworkify

完整的上手教學在**應用程式裡**：啟動服務後開 http://localhost:5173/getting-started
（側邊欄的 **Getting started**）。放在站內是為了讓說明可以直接連到對應的頁面，
也避免同一份內容維護兩次。

內容包含：

- workflow（定義）與 run（執行）的差別
- 一個從頭建到跑完的例子：輸入、python 判斷、條件分支、兩條分支的 shell
- 資料怎麼在步驟之間流動：python 的 `inputs`、shell 的 `./get_input`、其他類型的 `{{steps...}}` 模板
- Retry 與 Re-run 的差別
- 設成 cron 週期排程
- 常見問題排查
- 用 API 做同一件事（`POST /definitions/`、`POST /definitions/{id}/runs`）

如果服務還沒起來：

```bash
docker compose up -d --build
```

- 前端：http://localhost:5173（第一次進去先註冊一組帳號）
- API 文件：http://localhost:8000/docs

專案架構、任務類型清單與壓測數據見 [README](../README.md)。
