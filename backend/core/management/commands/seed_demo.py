from datetime import timedelta
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import User, Recipient, CarePlan, Order


class Command(BaseCommand):
    help = 'Создаёт демонстрационных пользователей и данные для тестирования.'

    def user(self, phone, name, role, email):
        parts = name.split(' ', 2)
        phone = self.format_phone(phone)
        obj, _ = User.objects.get_or_create(phone=phone, defaults={
            'role': role, 'last_name': parts[0], 'first_name': parts[1] if len(parts)>1 else '', 'middle_name': parts[2] if len(parts)>2 else '',
            'full_name': name, 'email': email, 'is_verified': role != 'customer', 'is_active': True,
        })
        obj.role = role
        obj.last_name = parts[0]
        obj.first_name = parts[1] if len(parts)>1 else ''
        obj.middle_name = parts[2] if len(parts)>2 else ''
        obj.full_name = name
        obj.email = email
        obj.phone = phone
        obj.password_hash = make_password('Dobrosmena123!')
        obj.is_active = True
        obj.is_verified = role != 'customer' or True
        obj.save()
        return obj

    def format_phone(self, value):
        digits = ''.join(ch for ch in str(value) if ch.isdigit())
        if digits.startswith('8') and len(digits)==11: digits='7'+digits[1:]
        return f'+7 {digits[1:4]}-{digits[4:7]}-{digits[7:9]}-{digits[9:11]}'

    def handle(self, *args, **kwargs):
        for existing in User.objects.all():
            parts = existing.full_name.split(' ', 2)
            existing.phone = self.format_phone(existing.phone)
            if not existing.last_name: existing.last_name = parts[0] if parts else ''
            if not existing.first_name: existing.first_name = parts[1] if len(parts)>1 else ''
            if not existing.middle_name: existing.middle_name = parts[2] if len(parts)>2 else ''
            existing.save(update_fields=['phone','last_name','first_name','middle_name'])
        admin = self.user('+7 900 000-00-01', 'Иванов Иван Иванович', 'admin', 'admin@dobrosmena.local')
        customer = self.user('+7 900 000-00-02', 'Петров Алексей Сергеевич', 'customer', 'customer@dobrosmena.local')
        c1 = self.user('+7 900 000-00-03', 'Петрова Анна Викторовна', 'caregiver', 'caregiver1@dobrosmena.local')
        c2 = self.user('+7 900 000-00-04', 'Сидорова Елена Андреевна', 'caregiver', 'caregiver2@dobrosmena.local')
        c1.about = 'Спокойно сопровождаю взрослых дома, помогаю с прогулками, питанием и бытовыми делами. Люблю понятные договорённости и всегда оставляю короткий отчёт семье.'
        c1.skills = ['meal_preparation','shopping','household_help','walks','companionship','personal_hygiene','mobility_support','dementia','family_communication','reporting']
        c1.work_preferences = {'night_work': False, 'weekend_work': True, 'live_in': False, 'hospital_accompaniment': False, 'transport': False}
        c1.experience_years = 6
        c1.save(update_fields=['about','skills','work_preferences','experience_years'])
        c2.about = 'Опыт сопровождения пожилых людей и людей с нарушениями памяти. Могу работать по выходным и подключаться как резервный исполнитель.'
        c2.skills = ['companionship','walks','dementia','memory_support','light_exercise','weekend_work','family_communication','reporting']
        c2.work_preferences = {'night_work': True, 'weekend_work': True, 'live_in': False, 'hospital_accompaniment': True, 'transport': False}
        c2.experience_years = 8
        c2.save(update_fields=['about','skills','work_preferences','experience_years'])
        r, _ = Recipient.objects.get_or_create(customer=customer, full_name='Мария Ивановна', defaults={
            'birth_year': 1948, 'notes': 'Спокойное общение, прогулка во дворе.', 'consent_confirmed': True,
        })
        plan, _ = CarePlan.objects.get_or_create(recipient=r, version=1, defaults={
            'tasks': ['Завтрак', 'Помощь при передвижении', 'Прогулка', 'Гигиена'],
            'prohibitions': ['Не давать лекарства самостоятельно', 'Не выполнять медицинские процедуры'],
            'preferences': ['Спокойное общение', 'Не оставлять одну на улице'],
        })
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        o, _ = Order.objects.get_or_create(customer=customer, recipient=r, start_at=now + timedelta(hours=2), defaults={
            'care_plan': plan, 'caregiver': c1, 'status': 'confirmed', 'end_at': now + timedelta(hours=8),
            'hours': 6, 'hourly_rate': 350, 'total_price': 2100, 'platform_commission': 378,
            'caregiver_amount': 1722, 'address_area': 'Центральный район', 'exact_address': 'ул. Примерная, 15',
        })
        o2, _ = Order.objects.get_or_create(customer=customer, recipient=r, start_at=now + timedelta(days=1, hours=2), defaults={
            'care_plan': plan, 'status': 'matching', 'end_at': now + timedelta(days=1, hours=8),
            'hours': 6, 'hourly_rate': 350, 'total_price': 2100, 'platform_commission': 378,
            'caregiver_amount': 1722, 'address_area': 'Центральный район', 'exact_address': 'ул. Примерная, 15',
        })
        self.stdout.write(self.style.SUCCESS('Demo data ready. Password for all demo accounts: Dobrosmena123!'))
