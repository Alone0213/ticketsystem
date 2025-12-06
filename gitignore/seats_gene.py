import json
seats = []
for i in range(1, 501):
    seats.append({"seat_id": i, "pos": "", "occupied": False, "student_id": None})
with open("seats.json", "w", encoding="utf-8") as f:
    json.dump(seats, f, indent=2)
import json
seats = []
for i in range(1, 501):
    seats.append({"seat_id": i, "pos": "", "occupied": False, "student_id": None})
with open("seats.json", "w", encoding="utf-8") as f:
    json.dump(seats, f, indent=2)
