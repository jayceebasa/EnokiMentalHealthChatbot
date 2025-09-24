from django.contrib import admin
from .models import ChatSession, Message, UserPreference


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "anon_id", "created_at", "updated_at")
	search_fields = ("anon_id", "user__username")
	list_filter = ("created_at",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
	list_display = ("id", "session", "sender", "short_text", "created_at")
	search_fields = ("text", "session__id")
	readonly_fields = ("decrypted_preview",)

	def decrypted_preview(self, obj):
		return obj.plaintext
	decrypted_preview.short_description = "Decrypted Text"
	list_filter = ("sender", "created_at")


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "anon_id", "tone", "language", "updated_at")
	search_fields = ("anon_id", "user__username")
	list_filter = ("tone", "language")
