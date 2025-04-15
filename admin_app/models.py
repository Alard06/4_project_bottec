from django.db import models

# Create your models here.

class SettingsBot(models.Model):
    token = models.CharField(max_length=255)

    class Meta:
        db_table = 'settings_bot'
        verbose_name = 'Токен'
        verbose_name_plural = 'Токены'

    def __str__(self):
        return self.token


class AdministrationBot(models.Model):
    name = models.CharField(max_length=255)
    api_token = models.CharField(max_length=255, blank=True, null=True)
    assistant_token = models.CharField(max_length=255)
    prompt = models.TextField(null=True, blank=True)


    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'administration_bot'
        verbose_name = 'Настройки бота'
        verbose_name_plural = 'Настройки ботов'


class UserRequest(models.Model):
    user_id = models.BigIntegerField(unique=True)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    company = models.CharField(max_length=255, blank=True, null=True)
    position = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'На модерации'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено')
    ], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    access_bots = models.ManyToManyField(AdministrationBot, blank=True)
    access_until = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.full_name} ({self.user_id})"

    class Meta:
        db_table = 'user_request'
        verbose_name = 'Запрос пользователя'
        verbose_name_plural = 'Запросы пользователей'


