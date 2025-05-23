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
    list_display = ('user_id', 'full_name', 'phone', 'company', 'position', 'status', 'access_until', 'created_at')
    search_fields = ('user_id', 'full_name', 'phone', 'company', 'position')
    list_filter = ('status', 'access_until')
    fields = ('user_id', 'full_name', 'phone', 'company', 'position', 'status', 'access_bots', 'access_until')

    def save_model(self, request, obj, form, change):
        if change:
            previous = UserRequest.objects.get(pk=obj.pk)
            if previous.status != 'approved' and obj.status == 'approved':
                self.send_approval_message(obj)
        super().save_model(request, obj, form, change)

    def send_approval_message(self, obj):
        tokens = SettingsBot.objects.values_list('token', flat=True)

        chat_id = obj.user_id
        bots = obj.access_bots.all()
        bot_names = ', '.join([b.name for b in bots]) if bots else 'Нет'
        until = obj.access_until.strftime('%d.%m.%Y %H:%M') if obj.access_until else 'Не ограничено'

        text = (
            f"Ваш запрос одобрен!\n"
            f"Имя: {obj.full_name}\n"
            f"Доступ к ботам: {bot_names}\n"
            f"Доступ до: {until}"
        )

        print(f"Отправляем сообщение пользователю {obj.full_name} ({chat_id}): {text}")

        for token in tokens:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text
            }
            try:
                response = requests.post(url, data=payload)
                response.raise_for_status()
                print(f"Сообщение успешно отправлено для токена {token}")
            except requests.RequestException as e:
                print(f"Ошибка отправки сообщения ботом с токеном {token}: {e}")