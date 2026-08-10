from django.db import models


class Order(models.Model):
    external_id = models.CharField(max_length=255, unique=True)
    patient_name = models.CharField(max_length=255)
    clinic_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} ({self.external_id})"
