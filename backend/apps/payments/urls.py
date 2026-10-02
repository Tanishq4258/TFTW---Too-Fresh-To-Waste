"""
Payments URL patterns for Too Fresh To Waste (TFTW).
"""

from django.urls import path
from . import views

urlpatterns = [
    # ─── Public Config ────────────────────────────────────────────────────────
    path('config/', views.PaymentConfigView.as_view(), name='payment-config'),

    # ─── Customer Checkout & Verification ─────────────────────────────────────
    path('create-order/', views.CreatePaymentOrderView.as_view(), name='payment-create-order'),
    path('verify/', views.VerifyPaymentView.as_view(), name='payment-verify'),
    path('failure/', views.PaymentFailureReportView.as_view(), name='payment-failure'),
    path('retry/', views.RetryPaymentView.as_view(), name='payment-retry'),

    # ─── Razorpay Webhook (Server-to-Server) ──────────────────────────────────
    path('webhook/', views.RazorpayWebhookView.as_view(), name='payment-webhook'),

    # ─── Admin Payment Management ─────────────────────────────────────────────
    path('refund/', views.AdminRefundView.as_view(), name='payment-admin-refund'),
    path('admin/all/', views.AdminPaymentsListView.as_view(), name='payment-admin-list'),
]
