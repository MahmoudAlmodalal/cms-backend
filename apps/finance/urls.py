from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.routers import DefaultRouter

from .views import AccountViewSet, CashFlowReportView, CategoryViewSet, CurrentWorkspaceView, ExchangeRateViewSet, NetWorthReportView, PersonViewSet, PortfolioViewSet, TransactionViewSet

router = DefaultRouter()
router.register("people", PersonViewSet, basename="finance-person")
router.register("portfolios", PortfolioViewSet, basename="finance-portfolio")
router.register("accounts", AccountViewSet, basename="finance-account")
router.register("categories", CategoryViewSet, basename="finance-category")
router.register("transactions", TransactionViewSet, basename="finance-transaction")
router.register("exchange-rates", ExchangeRateViewSet, basename="finance-exchange-rate")


@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"detail": "CSRF cookie set"})


urlpatterns = [
    path("csrf/", csrf, name="finance-csrf"),
    path("workspaces/current/", CurrentWorkspaceView.as_view(), name="finance-current-workspace"),
    path("reports/net-worth/", NetWorthReportView.as_view(), name="finance-net-worth"),
    path("reports/cash-flow/", CashFlowReportView.as_view(), name="finance-cash-flow"),
    path("", include(router.urls)),
]
