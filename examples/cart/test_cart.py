import unittest
from cart import total, add_item, average_price

class CartTests(unittest.TestCase):
    def test_total(self):
        self.assertEqual(total([10, 20], .1), 27)

    def test_empty_average(self):
        self.assertEqual(average_price([]), 0)

    def test_cart_isolation(self):
        add_item('apple')
        self.assertEqual(add_item('pear'), ['pear'])
