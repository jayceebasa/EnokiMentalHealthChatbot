from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from .security import encrypt_value, decrypt_value, is_encrypted

User = get_user_model()


class ChatSession(models.Model):
	"""Represents a logical conversation thread.

	A session can belong to an authenticated user OR an anonymous visitor (tracked via anon_id / session key).
	"""
	user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="chat_sessions")
	anon_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	summary = models.TextField(null=True, blank=True, help_text="Running condensed emotional/context summary for continuity.")
	memory = models.JSONField(null=True, blank=True, help_text="Structured memory (stressor, motivation, coping, trajectory, bot_openings)")

	class Meta:
		indexes = [
			models.Index(fields=["anon_id"]),
			models.Index(fields=["created_at"]),
		]

	def __str__(self):
		owner = self.user.username if self.user else f"anon:{self.anon_id}" if self.anon_id else "unassigned"
		return f"ChatSession({owner}, id={self.id})"


class UserPreference(models.Model):
	"""Stores tone / language preferences for either an authenticated user or an anonymous visitor."""
	user = models.OneToOneField(User, null=True, blank=True, on_delete=models.CASCADE, related_name="preferences")
	anon_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
	tone = models.CharField(max_length=32, default="empathetic")
	language = models.CharField(max_length=8, default="en")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["anon_id"], name="unique_pref_anon_id", condition=models.Q(anon_id__isnull=False)),
		]

	def __str__(self):
		if self.user:
			return f"UserPreference(user={self.user.username})"
		return f"UserPreference(anon={self.anon_id})"


class Message(models.Model):
	"""A single message in a chat session."""
	SENDER_CHOICES = (
		("user", "User"),
		("bot", "Bot"),
	)

	session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
	sender = models.CharField(max_length=8, choices=SENDER_CHOICES)
	text = models.TextField(help_text="Encrypted or plaintext depending on ENCRYPTION_KEY")
	emotions = models.JSONField(null=True, blank=True)  # list of {label, score}
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]
		indexes = [
			models.Index(fields=["created_at"]),
			models.Index(fields=["sender"]),
		]

	def short_text(self):
		plain = self.plaintext
		return (plain[:47] + "...") if len(plain) > 50 else plain

	@property
	def plaintext(self) -> str:
		return decrypt_value(self.text)

	def set_plaintext(self, value: str):
		self.text = encrypt_value(value)

	def save(self, *args, **kwargs):
		# Encrypt only if not already encrypted
		if self.text and not is_encrypted(self.text):
			self.text = encrypt_value(self.text)
		super().save(*args, **kwargs)

	def __str__(self):
		return f"Message({self.sender}, session={self.session_id}, id={self.id})"

