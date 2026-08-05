"""Delivery timing agent."""

from services.delivery_analysis import analyze_delivery


class DeliveryAgent:
    def analyze(self, order):
        return analyze_delivery(order)

    def run(self, order):
        return self.analyze(order)
