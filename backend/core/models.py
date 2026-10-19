from django.db import models


class User(models.Model):
    ROLE_CHOICES = [
        ('customer', 'Заказчик'),
        ('caregiver', 'Исполнитель'),
        ('admin', 'Администратор'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    last_name = models.CharField(max_length=100, default='')
    first_name = models.CharField(max_length=100, default='')
    middle_name = models.CharField(max_length=100, default='')
    full_name = models.CharField(max_length=300, default='')
    phone = models.CharField(max_length=30, unique=True)
    email = models.EmailField(blank=True)
    avatar = models.FileField(upload_to='avatars/', blank=True, null=True)
    about = models.TextField(blank=True)
    skills = models.JSONField(default=list, blank=True)
    work_preferences = models.JSONField(default=dict, blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    password_hash = models.CharField(max_length=256, blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class AuthToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_tokens')
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['token_hash']),
            models.Index(fields=['user', 'revoked_at']),
        ]


class Recipient(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recipients')
    full_name = models.CharField(max_length=200)
    birth_year = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    consent_confirmed = models.BooleanField(default=False)


class CarePlan(models.Model):
    recipient = models.ForeignKey(Recipient, on_delete=models.CASCADE, related_name='plans')
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=30, default='active')
    tasks = models.JSONField(default=list)
    prohibitions = models.JSONField(default=list)
    preferences = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class Order(models.Model):
    STATUS = [
        ('draft', 'Черновик'),
        ('risk_check', 'Проверка риска'),
        ('matching', 'Подбор'),
        ('caregiver_requested', 'Запрос исполнителю'),
        ('accepted', 'Исполнитель принял'),
        ('payment_authorized', 'Оплата авторизована'),
        ('confirmed', 'Подтверждена'),
        ('en_route', 'В пути'),
        ('arrived', 'Прибыл'),
        ('started', 'Идёт'),
        ('completed', 'Завершена'),
        ('customer_confirmed', 'Подтверждена заказчиком'),
        ('settlement', 'Расчёт'),
        ('replacement', 'Замена'),
        ('incident', 'Инцидент'),
        ('disputed', 'Спор'),
        ('cancelled', 'Отменена'),
        ('blocked', 'Заблокирована'),
    ]
    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='orders')
    recipient = models.ForeignKey(Recipient, on_delete=models.PROTECT, related_name='orders')
    caregiver = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='caregiver_orders')
    care_plan = models.ForeignKey(CarePlan, on_delete=models.PROTECT)
    status = models.CharField(max_length=30, choices=STATUS, default='draft')
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=350)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    platform_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    caregiver_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    address_area = models.CharField(max_length=200, blank=True)
    exact_address = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'start_at']),
            models.Index(fields=['caregiver', 'start_at', 'end_at']),
            models.Index(fields=['customer', 'start_at']),
        ]


class ShiftReport(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='report')
    condition = models.CharField(max_length=30, default='no_change')
    tasks_done = models.JSONField(default=list)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Incident(models.Model):
    SEVERITY = [
        ('info', 'Информация'),
        ('warning', 'Внимание'),
        ('critical', 'Критический'),
    ]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='incidents')
    severity = models.CharField(max_length=20, choices=SEVERITY)
    text = models.TextField()
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50)
    entity_id = models.PositiveIntegerField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['entity_type', 'entity_id', 'created_at'])]
