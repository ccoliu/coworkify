from locust import wait_time
import random
from locust import HttpUser, task, between

class CoworkifyUser(HttpUser):
    wait_time = between(.1, .5)

    def on_start(self):
        """每個虛擬用戶啟動時註冊一個帳號並取得 JWT"""
        username = f"locust_{random.randint(100000, 999999)}"
        resp = self.client.post(
            "/auth/register",
            json={"username": username, "password": "locust_password_123"},
            name="POST /auth/register",
        )
        token = resp.json()["access_token"]
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @task(3)
    def get_task_list(self):
        self.client.get("/tasks/?limit=20", headers=self.headers, name="GET /tasks")

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

    @task(1)
    def health_check(self):
        self.client.get("/health", headers=self.headers, name="GET /health")

    @task(1)
    def create_workflow(self):
        payload = {
            "name": f"load_test_wf_{random.randint(1000, 9999)}",
            "steps": [
                {"key": "t1", "name": "step1", "task_type": "echo", "payload": {"message": "step1"}, "depends_on": []},
                {"key": "t2", "name": "step2", "task_type": "echo", "payload": {"message": "step2"}, "depends_on": ["t1"]},
                {"key": "t3", "name": "step3", "task_type": "echo", "payload": {"message": "step3"}, "depends_on": ["t2"]},
            ],
        }
        self.client.post("/workflows/", json=payload, headers=self.headers, name="POST /workflows")
