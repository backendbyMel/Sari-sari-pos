from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from inventory.models import PriceTier, Product, ProductUnit

User = get_user_model()


def make_owner(username='boss'):
    return User.objects.create_user(username=username, password='Owner#Pass123', role='OWNER')


def make_cashier(username='cash'):
    return User.objects.create_user(username=username, password='Cashier#Pass123', role='CASHIER')


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


def make_marlboro(cost='8.0000', stock='400'):
    product = Product.objects.create(
        name='Marlboro Red', base_unit='stick', cost_price=Decimal(cost),
        stock_qty=Decimal(stock), low_stock_level=Decimal('40'),
    )
    stick = ProductUnit.objects.create(
        product=product, unit_name='stick', pieces_per_unit=Decimal('1'),
        selling_price=Decimal('10.00'),
    )
    pack = ProductUnit.objects.create(
        product=product, unit_name='pack', pieces_per_unit=Decimal('20'),
        barcode='4800000000011', selling_price=Decimal('190.00'),
    )
    return product, stick, pack


def make_candy(stock='100'):
    product = Product.objects.create(
        name='Candy Test', base_unit='piece', cost_price=Decimal('0.5000'),
        stock_qty=Decimal(stock),
    )
    piece = ProductUnit.objects.create(
        product=product, unit_name='piece', pieces_per_unit=Decimal('1'),
        barcode='4800000000200', selling_price=Decimal('1.00'),
    )
    PriceTier.objects.create(product_unit=piece, min_qty=Decimal('3'), price=Decimal('2.00'))
    return product, piece

def open_shift(cashier, opening_cash='1000.00'):
    from shifts.models import Shift
    return Shift.objects.create(cashier=cashier, opening_cash=Decimal(opening_cash))