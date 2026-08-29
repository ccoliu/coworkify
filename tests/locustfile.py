from locust import wait_time
import random
from locust import HttpUser, task, between

class CoworkifyUser(HttpUser):
    wait_time = between(.1, .5)

    def on_start(self):
         """每個虛擬用戶啟動時設定 API Key Header"""
         self.headers = {
            "X-API-Key": "changeme_local_dev_key",
            "Content-Type": "application/json"
         }
    

    # 權重 3: 高頻查詢任務列表
    @task(3)
    def get_task_list(self):
        self.client.get("/tasks/?limit=20", headers=self.headers, name="GET /tasks")

    # 權重 2: 發送任務建立請求
    @task(2)
    def create_task(self):
        task_type = ["echo", "heavy_computation", "flaky_task"]
        selected_type = random.choice(task_type)

        payload = {
            "name": f"load_test_task_{random.randint(1000, 9999)}",
            "task_type": selected_type,
            "payload": {"message": "testing with locust", "duration_seconds": 1},
            "priority": random.randint(0, 9),
            "max_retries": 2
        }

        self.client.post("/tasks/", json=payload, headers=self.headers, name="POST /tasks")
    
    # 權重 1: 健康檢查
    @task(1)
    def health_check(self):
        self.client.get("/health", headers=self.headers, name="GET /health")