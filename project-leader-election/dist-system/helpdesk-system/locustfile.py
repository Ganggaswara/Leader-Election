from locust import HttpUser, task, between
import json
import random

class TicketServiceUser(HttpUser):
    wait_time = between(1, 3)
    ticket_ids = []  # Simpan ID tiket yang berhasil dibuat

    def on_start(self):
        # Bikin 1 tiket dulu saat user start, simpan ID-nya
        payload = {
            "customer_name": f"User_{random.randint(1000, 9999)}",
            "issue_title": f"Issue #{random.randint(1, 100)}",
            "description": "Test dari Locust"
        }
        with self.client.post("/tickets", json=payload, name="POST /tickets", catch_response=True) as res:
            if res.status_code == 201:
                data = res.json()
                self.ticket_ids.append(data["ticket_id"])
            else:
                res.failure(f"Gagal bikin tiket: {res.text}")

    @task(3)
    def get_all_tickets(self):
        self.client.get("/tickets", name="GET /tickets")

    @task(2)
    def get_ticket_by_id(self):
        if not self.ticket_ids:
            return
        ticket_id = random.choice(self.ticket_ids)
        with self.client.get(f"/tickets/{ticket_id}", name="GET /tickets/{id}", catch_response=True) as res:
            if res.status_code == 404:
                res.failure("Ticket not found")

    @task(1)
    def create_ticket(self):
        payload = {
            "customer_name": f"User_{random.randint(1000, 9999)}",
            "issue_title": f"Issue #{random.randint(1, 100)}",
            "description": "Test dari Locust"
        }
        with self.client.post("/tickets", json=payload, name="POST /tickets", catch_response=True) as res:
            if res.status_code == 201:
                data = res.json()
                self.ticket_ids.append(data["ticket_id"])  # Simpan ID baru
            else:
                res.failure(f"Bad request: {res.text}")

    @task(1)
    def update_ticket(self):
        if not self.ticket_ids:
            return
        ticket_id = random.choice(self.ticket_ids)
        payload = {"issue_title": f"Updated Issue #{random.randint(1, 100)}"}
        with self.client.put(f"/tickets/{ticket_id}", json=payload, name="PUT /tickets/{id}", catch_response=True) as res:
            if res.status_code == 404:
                res.failure("Ticket not found")