from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.finance.models import ExchangeRate, TransactionStatus
from apps.finance.services import workspace_for_user
from apps.users.models import User


@pytest.mark.django_db
def test_posted_transfer_updates_balances_and_is_scoped_to_current_user():
    user = User.objects.create_user(email="owner@example.com", password="safe-password")
    other_user = User.objects.create_user(email="other@example.com", password="safe-password")
    client = APIClient()
    client.force_authenticate(user=user)

    workspace_response = client.get("/api/v1/workspaces/current/")
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.data["workspace"]["id"]
    accounts = client.get("/api/v1/accounts/").data["results"]
    source_account = accounts[0]["id"]
    people = client.get("/api/v1/people/").data["results"]
    person_id = people[0]["id"]

    portfolio_response = client.post("/api/v1/portfolios/", {"name": "الادخار", "type": "savings", "person": person_id, "base_currency": "ILS"}, format="json")
    assert portfolio_response.status_code == 201
    destination_response = client.post("/api/v1/accounts/", {"name": "حساب الادخار", "type": "savings", "portfolio": portfolio_response.data["id"], "currency": "ILS", "opening_balance": "0"}, format="json")
    assert destination_response.status_code == 201

    income_response = client.post("/api/v1/transactions/", {"kind": "income", "description": "دخل", "amount": "100.00", "currency": "ILS", "destination_account": source_account}, format="json")
    assert income_response.status_code == 201
    assert client.post(f"/api/v1/transactions/{income_response.data['id']}/post/").status_code == 200

    transfer_response = client.post("/api/v1/transactions/", {"kind": "transfer", "description": "تحويل", "amount": "40.00", "currency": "ILS", "source_account": source_account, "destination_account": destination_response.data["id"]}, format="json")
    assert transfer_response.status_code == 201
    assert client.post(f"/api/v1/transactions/{transfer_response.data['id']}/post/").status_code == 200

    balances = {row["name"]: Decimal(row["current_balance"]) for row in client.get("/api/v1/accounts/").data["results"]}
    assert balances["الصندوق النقدي"] == Decimal("60.00")
    assert balances["حساب الادخار"] == Decimal("40.00")
    assert TransactionStatus.POSTED == "posted"

    client.force_authenticate(user=other_user)
    other_workspace = client.get("/api/v1/workspaces/current/").data["workspace"]
    foreign_accounts = client.get("/api/v1/accounts/").data["results"]
    assert other_workspace["id"] != workspace_id
    assert all(row["id"] not in {source_account, destination_response.data["id"]} for row in foreign_accounts)


@pytest.mark.django_db
def test_reports_use_historical_workspace_exchange_rates_and_require_authentication():
    anonymous_client = APIClient()
    assert anonymous_client.get("/api/v1/workspaces/current/").status_code == 403

    user = User.objects.create_user(email="currency@example.com", password="safe-password")
    workspace = workspace_for_user(user)
    client = APIClient()
    client.force_authenticate(user=user)
    account = client.get("/api/v1/accounts/").data["results"][0]
    ExchangeRate.objects.create(
        workspace=workspace,
        source_currency="ILS",
        target_currency="USD",
        rate=Decimal("0.25"),
        effective_on="2025-01-01",
    )
    income = client.post(
        "/api/v1/transactions/",
        {"kind": "income", "description": "دخل شيكل", "amount": "100.00", "currency": "ILS", "destination_account": account["id"], "occurred_on": "2025-01-02"},
        format="json",
    )
    assert client.post(f"/api/v1/transactions/{income.data['id']}/post/").status_code == 200
    report = client.get("/api/v1/reports/cash-flow/?currency=USD")
    assert report.status_code == 200
    assert Decimal(report.data["income"]) == Decimal("25.00")
