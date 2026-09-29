#!/usr/bin/env python3
"""
Generates 200 synthetic customer records using Faker and saves to data/customers.csv
and data/customers_masked.csv.
"""

import csv
import os
import re
import uuid
from faker import Faker

fake = Faker()
Faker.seed(42)  # Deterministic seed for reproducible demo data

def mask_ssn(ssn: str) -> str:
    # Returns XXX-XX-XXXX with first 5 digits masked
    digits = re.sub(r"\D", "", ssn)
    if len(digits) >= 4:
        return f"XXX-XX-{digits[-4:]}"
    return "XXX-XX-0000"

def mask_phone(phone: str) -> str:
    # Returns XXX-XXX-XXXX with first 6 digits masked
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 4:
        return f"XXX-XXX-{digits[-4:]}"
    return "XXX-XXX-0000"

def generate_customers(count: int = 200):
    records = []
    for _ in range(count):
        raw_ssn = fake.ssn()
        raw_phone = fake.numerify("###-###-####")
        records.append({
            "id": str(uuid.uuid4()),
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "ssn": raw_ssn,
            "email": fake.email(),
            "phone_number": raw_phone,
            "ssn_masked": mask_ssn(raw_ssn),
            "phone_number_masked": mask_phone(raw_phone),
        })
    return records

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    records = generate_customers(200)

    # 1. Base table CSV (contains raw data to be loaded into Spanner)
    raw_csv_path = os.path.join(data_dir, "customers.csv")
    with open(raw_csv_path, mode="w", newline="", encoding="utf-8") as f:
        fieldnames = ["id", "first_name", "last_name", "ssn", "email", "phone_number"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r[k] for k in fieldnames})
    print(f"Generated 200 records into: {raw_csv_path}")

    # 2. Masked view CSV (representing the expected view output per GEMINI.md)
    masked_csv_path = os.path.join(data_dir, "customers_masked.csv")
    with open(masked_csv_path, mode="w", newline="", encoding="utf-8") as f:
        fieldnames = ["id", "first_name", "last_name", "ssn", "email", "phone_number"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "id": r["id"],
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "ssn": r["ssn_masked"],
                "email": r["email"],
                "phone_number": r["phone_number_masked"],
            })
    print(f"Generated 200 masked preview records into: {masked_csv_path}")

if __name__ == "__main__":
    main()
