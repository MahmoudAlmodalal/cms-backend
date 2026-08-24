from decimal import Decimal

from django.utils.dateparse import parse_date
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account, AuditEvent, Category, ExchangeRate, Person, Portfolio, Transaction, TransactionKind, TransactionStatus, WorkspaceRole
from .serializers import AccountSerializer, CategorySerializer, ExchangeRateSerializer, PersonSerializer, PortfolioSerializer, TransactionSerializer, WorkspaceSerializer
from .services import account_balance, convert_amount, post_transaction, workspace_for_user


class FinanceWorkspacePermission(permissions.BasePermission):
    """Readers may view their workspace; only owners and editors may mutate it."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        workspace = workspace_for_user(request.user)
        if request.method in permissions.SAFE_METHODS:
            return True
        return workspace.members.filter(
            user=request.user,
            is_active=True,
            role__in=[WorkspaceRole.OWNER, WorkspaceRole.EDITOR],
        ).exists()


class WorkspaceScopedViewSet(viewsets.ModelViewSet):
    permission_classes = [FinanceWorkspacePermission]

    def get_workspace(self):
        return workspace_for_user(self.request.user)

    def perform_create(self, serializer):
        serializer.save(workspace=self.get_workspace())


class CurrentWorkspaceView(APIView):
    permission_classes = [FinanceWorkspacePermission]

    def get(self, request):
        workspace = workspace_for_user(request.user)
        accounts = Account.objects.filter(workspace=workspace, is_archived=False).select_related("portfolio")
        net_worth = sum((convert_amount(account_balance(account), account.currency, workspace.default_currency, workspace) for account in accounts), start=Decimal("0"))
        return Response({"workspace": WorkspaceSerializer(workspace).data, "net_worth": net_worth, "account_count": accounts.count()})


class PersonViewSet(WorkspaceScopedViewSet):
    serializer_class = PersonSerializer

    def get_queryset(self):
        return Person.objects.filter(workspace=self.get_workspace())


class PortfolioViewSet(WorkspaceScopedViewSet):
    serializer_class = PortfolioSerializer

    def get_queryset(self):
        return Portfolio.objects.filter(workspace=self.get_workspace()).select_related("person").prefetch_related("accounts")

    def perform_create(self, serializer):
        person = serializer.validated_data["person"]
        if person.workspace_id != self.get_workspace().id:
            raise ValidationError({"person": "الشخص لا ينتمي إلى مساحة العمل الحالية."})
        super().perform_create(serializer)


class AccountViewSet(WorkspaceScopedViewSet):
    serializer_class = AccountSerializer

    def get_queryset(self):
        return Account.objects.filter(workspace=self.get_workspace()).select_related("portfolio")

    def perform_create(self, serializer):
        portfolio = serializer.validated_data["portfolio"]
        if portfolio.workspace_id != self.get_workspace().id:
            raise ValidationError({"portfolio": "المحفظة لا تنتمي إلى مساحة العمل الحالية."})
        super().perform_create(serializer)


class CategoryViewSet(WorkspaceScopedViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        return Category.objects.filter(workspace=self.get_workspace())


class TransactionViewSet(WorkspaceScopedViewSet):
    serializer_class = TransactionSerializer

    def get_queryset(self):
        queryset = Transaction.objects.filter(workspace=self.get_workspace()).select_related("category", "source_account", "destination_account")
        for field in ("kind", "status", "category", "source_account", "destination_account"):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        start = parse_date(self.request.query_params.get("start", ""))
        end = parse_date(self.request.query_params.get("end", ""))
        if start:
            queryset = queryset.filter(occurred_on__gte=start)
        if end:
            queryset = queryset.filter(occurred_on__lte=end)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["workspace"] = self.get_workspace()
        return context

    def perform_create(self, serializer):
        serializer.save(workspace=self.get_workspace(), created_by=self.request.user)

    def perform_update(self, serializer):
        if self.get_object().status != TransactionStatus.DRAFT:
            raise ValidationError("لا يمكن تعديل حركة منشورة أو ملغاة؛ أنشئ حركة تصحيحية بدلاً منها.")
        serializer.save()

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        finance_transaction = self.get_object()
        try:
            posted = post_transaction(finance_transaction, request.user)
        except ValueError as error:
            raise ValidationError(str(error)) from error
        return Response(self.get_serializer(posted).data)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        finance_transaction = self.get_object()
        if finance_transaction.status == TransactionStatus.VOIDED:
            return Response(self.get_serializer(finance_transaction).data)
        finance_transaction.status = TransactionStatus.VOIDED
        finance_transaction.save(update_fields=["status", "updated_at"])
        AuditEvent.objects.create(
            workspace=finance_transaction.workspace,
            actor=request.user,
            action="voided",
            entity_type="transaction",
            entity_id=finance_transaction.id,
            summary=f"تم إلغاء حركة: {finance_transaction.description}",
        )
        return Response(self.get_serializer(finance_transaction).data)


class ExchangeRateViewSet(WorkspaceScopedViewSet):
    serializer_class = ExchangeRateSerializer

    def get_queryset(self):
        return ExchangeRate.objects.filter(workspace=self.get_workspace())


class NetWorthReportView(APIView):
    permission_classes = [FinanceWorkspacePermission]

    def get(self, request):
        workspace = workspace_for_user(request.user)
        target_currency = request.query_params.get("currency", workspace.default_currency)
        accounts = Account.objects.filter(workspace=workspace, is_archived=False).select_related("portfolio")
        try:
            rows = [
                {
                    "account_id": account.id,
                    "account": account.name,
                    "portfolio": account.portfolio.name,
                    "currency": account.currency,
                    "balance": account_balance(account),
                    "converted_balance": convert_amount(account_balance(account), account.currency, target_currency, workspace),
                }
                for account in accounts
            ]
        except ValueError as error:
            raise ValidationError(str(error)) from error
        total = sum((row["converted_balance"] for row in rows), start=Decimal("0"))
        return Response({"currency": target_currency, "net_worth": total, "accounts": rows})


class CashFlowReportView(APIView):
    permission_classes = [FinanceWorkspacePermission]

    def get(self, request):
        workspace = workspace_for_user(request.user)
        target_currency = request.query_params.get("currency", workspace.default_currency)
        queryset = Transaction.objects.filter(workspace=workspace, status=TransactionStatus.POSTED)
        start = parse_date(request.query_params.get("start", ""))
        end = parse_date(request.query_params.get("end", ""))
        if start:
            queryset = queryset.filter(occurred_on__gte=start)
        if end:
            queryset = queryset.filter(occurred_on__lte=end)
        try:
            income = sum(
                (convert_amount(item.amount, item.currency, target_currency, workspace, item.occurred_on) for item in queryset.filter(kind=TransactionKind.INCOME)),
                start=Decimal("0"),
            )
            expense = sum(
                (convert_amount(item.amount, item.currency, target_currency, workspace, item.occurred_on) for item in queryset.filter(kind=TransactionKind.EXPENSE)),
                start=Decimal("0"),
            )
        except ValueError as error:
            raise ValidationError(str(error)) from error
        return Response({"income": income, "expense": expense, "net_cash_flow": income - expense, "currency": target_currency})
