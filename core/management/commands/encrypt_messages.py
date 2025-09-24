from django.core.management.base import BaseCommand
from core.models import Message
from core.security import encrypt_value, is_encrypted


class Command(BaseCommand):
    help = "Encrypt any stored Message.text values that are still plaintext. Requires ENCRYPTION_KEY."

    def handle(self, *args, **options):
        total = 0
        updated = 0
        for msg in Message.objects.all().only('id', 'text'):
            total += 1
            if msg.text and not is_encrypted(msg.text):
                original = msg.text
                msg.text = encrypt_value(original)
                msg.save(update_fields=["text"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Scanned {total} messages. Encrypted {updated}."))