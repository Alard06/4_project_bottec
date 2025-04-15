from django.contrib import admin
from admin_app.models import AdministrationBot, SettingsBot, UserRequest
import requests

@admin.register(SettingsBot)
class SettingsBotAdmin(admin.ModelAdmin):
    list_display = ('id', 'token')
    search_fields = ('token',)
    fields = ('token',)
    
    def has_add_permission(self, request):
        if self.model.objects.count() >= 1:
            return False
        return super().has_add_permission(request)

@admin.register(AdministrationBot)
class AdministrationBotAdmin(admin.ModelAdmin):
    list_display = ('name', 'assistant_token', 'api_token', 'prompt_preview')
    search_fields = ('name', 'assistant_token', 'api_token')
    list_filter = ('name',)
    fields = ('name', 'assistant_token', 'api_token', 'prompt')
    
    def prompt_preview(self, obj):
        return obj.prompt[:50] + '...' if obj.prompt else '-'
    prompt_preview.short_description = 'Prompt (preview)'



@admin.register(UserRequest)
class UserRequestAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'full_name', 'phone', 'company', 'position', 'status', 'created_at')
    search_fields = ('user_id', 'full_name', 'phone', 'company', 'position')
    list_filter = ('status',)
    fields = ('user_id', 'full_name', 'phone', 'company', 'position', 'status')

    def save_model(self, request, obj, form, change):
        if change:
            previous = UserRequest.objects.get(pk=obj.pk)
            if previous.status != 'approved' and obj.status == 'approved':
                self.send_approval_message(obj)
        super().save_model(request, obj, form, change)

    def send_approval_message(self, obj):
        tokens = SettingsBot.objects.values_list('token', flat=True)

        chat_id = obj.user_id
        text = f"Ваш запрос одобрен! Добро пожаловать, {obj.full_name}!"

        for token in tokens:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text
            }
            try:
                response = requests.post(url, data=payload)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"Ошибка отправки сообщения ботом с токеном {token}: {e}")