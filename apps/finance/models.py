from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Currency(models.TextChoices):
    ILS = "ILS", "Israeli shekel"
    USD = "USD", "US dollar"


class WorkspaceRole(models.TextChoices):
    OWNER = "owner", "Owner"
    EDITOR = "editor", "Editor"
    VIEWER = "viewer", "Viewer"


class TransactionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    POSTED = "posted", "Posted"
    VOIDED = "voided", "Voided"


class TransactionKind(models.TextChoices):
    INCOME = "income", "Income"
    EXPENSE = "expense", "Expense"
    TRANSFER = "transfer", "Transfer"
    ASSET_PURCHASE = "asset_purchase", "Asset purchase"
    ASSET_SALE = "asset_sale", "Asset sale"
    DEBT = "debt", "Debt"
    DEBT_REPAYMENT = "debt_repayment", "Debt repayment"
    RECEIVABLE = "receivable", "Receivable"
    PAYABLE = "payable", "Payable"


class Workspace(BaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="finance_workspaces")
    name = models.CharField(max_length=120)
    default_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.ILS)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class WorkspaceMember(BaseModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="finance_memberships")
    role = models.CharField(max_length=12, choices=WorkspaceRole.choices, default=WorkspaceRole.VIEWER)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "user"], name="finance_unique_workspace_member")]


class Person(BaseModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="people")
    name = models.CharField(max_length=120)
    relation = models.CharField(max_length=80, blank=True)
    color = models.CharField(max_length=7, default="#0F5C5B")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="finance_unique_person_name")]
        ordering = ["name"]


class Portfolio(BaseModel):
    class PortfolioType(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"
        SAVINGS = "savings", "Savings"
        INVESTMENT = "investment", "Investment"
        DEBT = "debt", "Debt"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="portfolios")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="portfolios")
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=16, choices=PortfolioType.choices, default=PortfolioType.CASH)
    base_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.ILS)
    is_archived = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="finance_unique_portfolio_name")]
        ordering = ["name"]


class Account(BaseModel):
    class AccountType(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"
        SAVINGS = "savings", "Savings"
        CARD = "card", "Card"
        E_WALLET = "e_wallet", "E-wallet"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="accounts")
    portfolio = models.ForeignKey(Portfolio, on_delete=models.PROTECT, related_name="accounts")
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=16, choices=AccountType.choices, default=AccountType.BANK)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.ILS)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    is_archived = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="finance_unique_account_name")]
        ordering = ["name"]


class Category(BaseModel):
    class CategoryType(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=12, choices=CategoryType.choices)
    color = models.CharField(max_length=7, default="#0F5C5B")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "name", "type"], name="finance_unique_category")]
        ordering = ["type", "name"]


class Transaction(BaseModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=20, choices=TransactionKind.choices)
    status = models.CharField(max_length=12, choices=TransactionStatus.choices, default=TransactionStatus.DRAFT)
    occurred_on = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=255)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    counterparty = models.CharField(max_length=120, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.ILS)
    source_account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="outgoing_transactions")
    destination_account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="incoming_transactions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_finance_transactions")
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-occurred_on", "-id"]
        indexes = [models.Index(fields=["workspace", "status", "occurred_on"])]


class TransactionEntry(BaseModel):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="entries")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="entries")
    effect = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)

    class Meta:
        indexes = [models.Index(fields=["account", "transaction"])]


class ExchangeRate(BaseModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="exchange_rates")
    source_currency = models.CharField(max_length=3, choices=Currency.choices)
    target_currency = models.CharField(max_length=3, choices=Currency.choices)
    rate = models.DecimalField(max_digits=12, decimal_places=6, validators=[MinValueValidator(Decimal("0.000001"))])
    effective_on = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "source_currency", "target_currency", "effective_on"], name="finance_unique_exchange_rate")]
        ordering = ["-effective_on"]


class AuditEvent(BaseModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="finance_audit_events")
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80)
    entity_id = models.PositiveIntegerField()
    summary = models.CharField(max_length=255)

    class Meta:
        ordering = ["-created_at"]
