from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Account, AuditEvent, Category, ExchangeRate, Person, Portfolio, Transaction, TransactionEntry, TransactionKind, TransactionStatus, Workspace, WorkspaceMember, WorkspaceRole


def ensure_workspace(user) -> Workspace:
    """Return the user's first finance workspace and bootstrap non-financial defaults once."""
    workspace, _ = Workspace.objects.get_or_create(owner=user, defaults={"name": f"مساحة {user.name or user.email}"})
    WorkspaceMember.objects.get_or_create(workspace=workspace, user=user, defaults={"role": WorkspaceRole.OWNER})
    person, _ = Person.objects.get_or_create(workspace=workspace, name="أنا", defaults={"relation": "المالك"})
    portfolio, _ = Portfolio.objects.get_or_create(workspace=workspace, name="المحفظة اليومية", defaults={"person": person, "type": Portfolio.PortfolioType.CASH})
    Account.objects.get_or_create(workspace=workspace, name="الصندوق النقدي", defaults={"portfolio": portfolio, "type": Account.AccountType.CASH})
    Category.objects.get_or_create(workspace=workspace, name="دخل", type=Category.CategoryType.INCOME)
    Category.objects.get_or_create(workspace=workspace, name="مصروف", type=Category.CategoryType.EXPENSE)
    return workspace


def workspace_for_user(user) -> Workspace:
    membership = WorkspaceMember.objects.filter(user=user, is_active=True).select_related("workspace").order_by("workspace_id").first()
    return membership.workspace if membership else ensure_workspace(user)


def account_balance(account: Account) -> Decimal:
    effect = account.entries.filter(transaction__status=TransactionStatus.POSTED).aggregate(
        total=Coalesce(Sum("effect"), Value(Decimal("0")), output_field=DecimalField(max_digits=14, decimal_places=2))
    )["total"]
    return account.opening_balance + effect


def convert_amount(amount: Decimal, source_currency: str, target_currency: str, workspace: Workspace, effective_on=None) -> Decimal:
    """Convert only through an explicit workspace rate; historical data is never rewritten."""
    if source_currency == target_currency:
        return amount
    date = effective_on or timezone.localdate()
    direct = ExchangeRate.objects.filter(
        workspace=workspace,
        source_currency=source_currency,
        target_currency=target_currency,
        effective_on__lte=date,
    ).order_by("-effective_on").first()
    if direct:
        return amount * direct.rate
    reverse = ExchangeRate.objects.filter(
        workspace=workspace,
        source_currency=target_currency,
        target_currency=source_currency,
        effective_on__lte=date,
    ).order_by("-effective_on").first()
    if reverse:
        return amount / reverse.rate
    raise ValueError(f"لا يوجد سعر صرف {source_currency}/{target_currency} صالح بتاريخ {date}.")


def post_transaction(finance_transaction: Transaction, actor) -> Transaction:
    """Atomically materialize balanced account entries for a draft transaction."""
    with db_transaction.atomic():
        # Lock the transaction row itself; nullable account relations would otherwise
        # produce an outer join that PostgreSQL cannot lock with FOR UPDATE.
        locked = Transaction.objects.select_for_update().get(pk=finance_transaction.pk)
        if locked.status == TransactionStatus.VOIDED:
            raise ValueError("لا يمكن ترحيل حركة ملغاة.")
        if locked.status == TransactionStatus.POSTED:
            return locked

        entries: list[TransactionEntry] = []
        if locked.kind == TransactionKind.INCOME:
            if not locked.destination_account_id:
                raise ValueError("تتطلب حركة الدخل حساباً مستلماً.")
            entries.append(TransactionEntry(transaction=locked, account=locked.destination_account, effect=locked.amount, currency=locked.currency))
        elif locked.kind == TransactionKind.EXPENSE:
            if not locked.source_account_id:
                raise ValueError("تتطلب حركة المصروف حساباً مصدراً.")
            entries.append(TransactionEntry(transaction=locked, account=locked.source_account, effect=-locked.amount, currency=locked.currency))
        elif locked.kind == TransactionKind.TRANSFER:
            if not locked.source_account_id or not locked.destination_account_id:
                raise ValueError("يتطلب التحويل حساباً مصدراً وحساباً مستلماً.")
            if locked.source_account_id == locked.destination_account_id:
                raise ValueError("لا يمكن التحويل إلى الحساب نفسه.")
            entries.extend([
                TransactionEntry(transaction=locked, account=locked.source_account, effect=-locked.amount, currency=locked.currency),
                TransactionEntry(transaction=locked, account=locked.destination_account, effect=locked.amount, currency=locked.currency),
            ])
        else:
            raise ValueError("نوع الحركة غير مدعوم في الإصدار الأول.")

        TransactionEntry.objects.bulk_create(entries)
        locked.status = TransactionStatus.POSTED
        locked.posted_at = timezone.now()
        locked.save(update_fields=["status", "posted_at", "updated_at"])
        AuditEvent.objects.create(workspace=locked.workspace, actor=actor, action="posted", entity_type="transaction", entity_id=locked.id, summary=f"تم ترحيل حركة: {locked.description}")
    return locked
