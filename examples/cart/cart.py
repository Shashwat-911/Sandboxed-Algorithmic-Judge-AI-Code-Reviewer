"""Small cart service with intentional defects for the ATF demonstration."""
def total(prices, discount=0):
    return sum(prices) * (1 - discount)


def add_item(item, cart=[]):
    cart.append(item)
    return cart


def average_price(prices):
    return sum(prices) / len(prices)
