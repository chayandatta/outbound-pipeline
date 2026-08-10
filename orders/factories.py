import factory
from factory.django import DjangoModelFactory
from orders.models import Order


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = Order

    external_id = factory.Sequence(lambda n: f"ORD-{n:05d}")
    patient_name = factory.Faker("name")
    clinic_name = factory.Sequence(lambda n: f"Clinic_{n}")
