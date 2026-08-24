from rest_framework import serializers

from .models import Account, Category, ExchangeRate, Person, Portfolio, Transaction, TransactionKind, Workspace
from .services import account_balance


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ["id", "name", "default_currency"]


class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ["id", "name", "relation", "color"]


class PortfolioSerializer(serializers.ModelSerializer):
    current_balance = serializers.SerializerMethodField()
    person_name = serializers.CharField(source="person.name", read_only=True)

    class Meta:
        model = Portfolio
        fields = ["id", "name", "type", "person", "person_name", "base_currency", "is_archived", "current_balance"]
        read_only_fields = ["current_balance", "person_name"]

    def get_current_balance(self, portfolio):
        return sum((account_balance(account) for account in portfolio.accounts.all()), start=0)


class AccountSerializer(serializers.ModelSerializer):
    current_balance = serializers.SerializerMethodField()
    portfolio_name = serializers.CharField(source="portfolio.name", read_only=True)

    class Meta:
        model = Account
        fields = ["id", "name", "type", "portfolio", "portfolio_name", "currency", "opening_balance", "is_archived", "current_balance"]
        read_only_fields = ["current_balance", "portfolio_name"]

    def get_current_balance(self, account):
        return account_balance(account)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "type", "color"]


class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    source_account_name = serializers.CharField(source="source_account.name", read_only=True)
    destination_account_name = serializers.CharField(source="destination_account.name", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "kind", "status", "occurred_on", "description", "category", "category_name", "counterparty",
            "amount", "currency", "source_account", "source_account_name", "destination_account", "destination_account_name",
            "posted_at", "created_at",
        ]
        read_only_fields = ["status", "posted_at", "created_at"]

    def validate(self, attrs):
        workspace = self.context["workspace"]
        for field in ("source_account", "destination_account", "category"):
            instance = attrs.get(field)
            if instance and instance.workspace_id != workspace.id:
                raise serializers.ValidationError({field: "المورد لا ينتمي إلى مساحة العمل الحالية."})
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        source = attrs.get("source_account", getattr(self.instance, "source_account", None))
        destination = attrs.get("destination_account", getattr(self.instance, "destination_account", None))
        currency = attrs.get("currency", getattr(self.instance, "currency", None))
        if kind == TransactionKind.TRANSFER and source and destination and source.id == destination.id:
            raise serializers.ValidationError("لا يمكن التحويل إلى الحساب نفسه.")
        for account in (source, destination):
            if account and account.currency != currency:
                raise serializers.ValidationError("يجب أن تطابق عملة الحركة عملة الحساب.")
        return attrs


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = ["id", "source_currency", "target_currency", "rate", "effective_on"]
