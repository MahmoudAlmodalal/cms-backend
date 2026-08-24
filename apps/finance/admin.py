from django.contrib import admin

from .models import Account, AuditEvent, Category, ExchangeRate, Person, Portfolio, Transaction, TransactionEntry, Workspace, WorkspaceMember

admin.site.register([Workspace, WorkspaceMember, Person, Portfolio, Account, Category, Transaction, TransactionEntry, ExchangeRate, AuditEvent])
