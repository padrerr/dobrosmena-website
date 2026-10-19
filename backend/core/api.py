import hashlib
import secrets
import os
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.contrib.auth.hashers import check_password, make_password
from rest_framework import serializers, status
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

from .authentication import BearerAuthentication
from .models import AuthToken, User, Recipient, CarePlan, Order, ShiftReport, Incident, AuditLog
from .permissions import IsAuthenticated, IsAdmin, IsCustomer, IsCaregiver


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'last_name', 'first_name', 'middle_name', 'full_name', 'phone', 'email', 'role', 'avatar_url', 'about', 'skills', 'work_preferences', 'experience_years', 'is_verified', 'is_active', 'last_login', 'created_at')

    avatar_url = serializers.SerializerMethodField()

    def get_avatar_url(self, obj):
        try:
            return obj.avatar.url if obj.avatar else ''
        except Exception:
            return ''


def split_full_name(value):
    parts = ' '.join(str(value).strip().split()).split(' ')
    if len(parts) < 3:
        raise serializers.ValidationError('Укажите фамилию, имя и отчество полностью.')
    return parts[0], parts[1], ' '.join(parts[2:])

def format_phone(value):
    digits = ''.join(ch for ch in str(value) if ch.isdigit())
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]
    elif len(digits) == 10:
        digits = '7' + digits
    if len(digits) != 11 or not digits.startswith('7'):
        return str(value).strip()
    return f'+7 {digits[1:4]}-{digits[4:7]}-{digits[7:9]}-{digits[9:11]}'

def normalize_phone(value):
    digits = ''.join(ch for ch in str(value) if ch.isdigit())
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]
    elif len(digits) == 10:
        digits = '7' + digits
    return format_phone(digits) if len(digits) == 11 and digits.startswith('7') else str(value).strip()


class RegisterSerializer(serializers.Serializer):
    last_name = serializers.CharField(max_length=100)
    first_name = serializers.CharField(max_length=100)
    middle_name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=128, write_only=True)
    role = serializers.ChoiceField(choices=('customer', 'caregiver'), default='customer')

    def validate_last_name(self, value):
        value = ' '.join(value.strip().split())
        if not value: raise serializers.ValidationError('Укажите фамилию.')
        return value

    def validate_first_name(self, value):
        value = ' '.join(value.strip().split())
        if not value: raise serializers.ValidationError('Укажите имя.')
        return value

    def validate_middle_name(self, value):
        value = ' '.join(value.strip().split())
        if not value: raise serializers.ValidationError('Укажите отчество.')
        return value

    def validate_phone(self, value):
        value = normalize_phone(value)
        if len(value) < 10:
            raise serializers.ValidationError('Укажите корректный номер телефона.')
        return value

    def validate_email(self, value):
        return value.strip().lower()


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=200)
    password = serializers.CharField(write_only=True)


def issue_token(user, request):
    raw = secrets.token_urlsafe(48)
    AuthToken.objects.create(
        user=user,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(days=30),
        user_agent=request.headers.get('User-Agent', '')[:500],
    )
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])
    return raw


def audit(actor, action, entity_type, entity_id, details=None):
    if actor:
        AuditLog.objects.create(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        # Explicit pre-check gives the frontend a stable response for the duplicate-account popup.
        phone = normalize_phone(request.data.get('phone', ''))
        email = str(request.data.get('email', '')).strip().lower()
        duplicate_fields = []
        if phone and User.objects.filter(phone=phone).exists():
            duplicate_fields.append('phone')
        if email and User.objects.filter(email=email).exists():
            duplicate_fields.append('email')
        if duplicate_fields:
            labels = {'phone': 'номер телефона', 'email': 'электронная почта'}
            joined = ' и '.join(labels[x] for x in duplicate_fields)
            return Response({
                'code': 'account_exists',
                'field': duplicate_fields[0],
                'message': f'Аккаунт с таким {joined} уже создан.',
                'can_recover': True,
            }, status=status.HTTP_409_CONFLICT)

        serializer = RegisterSerializer(data={**request.data, 'phone': phone, 'email': email})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.create(
            last_name=data['last_name'],
            first_name=data['first_name'],
            middle_name=data['middle_name'],
            full_name=f"{data['last_name']} {data['first_name']} {data['middle_name']}",
            phone=normalize_phone(data['phone']),
            email=data['email'],
            role=data['role'],
            password_hash=make_password(data['password']),
            is_verified=False,
        )
        token = issue_token(user, request)
        audit(user, 'auth.registered', 'User', user.id, {'role': user.role})
        return Response({'token': token, 'user': UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data['identifier'].strip()
        phone = normalize_phone(identifier)
        email = identifier.lower()
        user = User.objects.filter(Q(phone=phone) | Q(email=email)).first()
        if not user or not user.is_active or not check_password(serializer.validated_data['password'], user.password_hash):
            return Response({
                'code': 'invalid_credentials',
                'detail': 'Номер телефона или электронная почта, либо пароль указаны неверно.',
                'can_recover': True,
                'identifier': identifier,
            }, status=status.HTTP_401_UNAUTHORIZED)
        token = issue_token(user, request)
        audit(user, 'auth.login', 'User', user.id)
        return Response({'token': token, 'user': UserSerializer(user).data})


class RecoverAccountView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        identifier = str(request.data.get('identifier', '')).strip()
        if not identifier:
            return Response({'detail': 'Укажите телефон или электронную почту.'}, status=400)
        # Пока только подготавливаем процесс восстановления. Отправка кода будет подключена позже.
        return Response({
            'ok': True,
            'code': 'recovery_not_implemented',
            'message': 'Запрос на восстановление принят. На следующем этапе код будет отправляться на подтверждённый телефон или электронную почту.',
        }, status=status.HTTP_202_ACCEPTED)


class LogoutView(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.auth.revoked_at = timezone.now()
        request.auth.save(update_fields=['revoked_at'])
        audit(request.user, 'auth.logout', 'User', request.user.id)
        return Response({'ok': True})


class MeView(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'user': UserSerializer(request.user).data})



class ProfileView(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    ALLOWED_SKILLS = {
        'meal_preparation', 'shopping', 'household_help', 'walks', 'companionship',
        'personal_hygiene', 'mobility_support', 'dementia', 'night_work',
        'weekend_work', 'live_in', 'hospital_accompaniment', 'transport',
        'pets', 'family_communication', 'reporting', 'calm_communication',
        'memory_support', 'light_exercise', 'appointment_accompaniment',
    }

    def get(self, request):
        return Response({'user': UserSerializer(request.user).data})

    def patch(self, request):
        user = request.user
        data = request.data

        last_name = str(data.get('last_name', user.last_name)).strip()
        first_name = str(data.get('first_name', user.first_name)).strip()
        middle_name = str(data.get('middle_name', user.middle_name)).strip()
        phone = normalize_phone(data.get('phone', user.phone))
        email = str(data.get('email', user.email or '')).strip().lower()

        if not last_name or not first_name or not middle_name:
            return Response({'detail': 'Фамилия, имя и отчество обязательны.'}, status=400)
        if len(''.join(ch for ch in str(phone) if ch.isdigit())) != 11:
            return Response({'detail': 'Укажите корректный номер телефона.'}, status=400)
        if User.objects.filter(phone=phone).exclude(pk=user.pk).exists():
            return Response({'code': 'account_exists', 'field': 'phone', 'detail': 'Этот номер телефона уже используется другим аккаунтом.'}, status=409)
        if email and User.objects.filter(email=email).exclude(pk=user.pk).exists():
            return Response({'code': 'account_exists', 'field': 'email', 'detail': 'Этот адрес электронной почты уже используется другим аккаунтом.'}, status=409)

        skills = data.get('skills', user.skills or [])
        if isinstance(skills, str):
            try:
                import json
                skills = json.loads(skills)
            except Exception:
                skills = [x.strip() for x in skills.split(',') if x.strip()]
        skills = [str(x) for x in skills if str(x) in self.ALLOWED_SKILLS]

        preferences = data.get('work_preferences', user.work_preferences or {})
        if isinstance(preferences, str):
            try:
                import json
                preferences = json.loads(preferences)
            except Exception:
                preferences = {}

        user.last_name = last_name
        user.first_name = first_name
        user.middle_name = middle_name
        user.full_name = f'{last_name} {first_name} {middle_name}'
        user.phone = phone
        user.email = email
        user.about = str(data.get('about', user.about or '')).strip()[:5000]
        user.skills = skills if user.role == 'caregiver' else []
        user.work_preferences = preferences if user.role == 'caregiver' else {}
        try:
            user.experience_years = max(0, min(60, int(data.get('experience_years', user.experience_years or 0))))
        except (TypeError, ValueError):
            return Response({'detail': 'Опыт укажите целым числом лет.'}, status=400)

        avatar = request.FILES.get('avatar')
        if avatar:
            if avatar.size > 5 * 1024 * 1024:
                return Response({'detail': 'Фотография должна быть не больше 5 МБ.'}, status=400)
            allowed = {'.jpg', '.jpeg', '.png', '.webp'}
            ext = os.path.splitext(avatar.name or '')[1].lower()
            if ext not in allowed:
                return Response({'detail': 'Поддерживаются JPG, PNG и WebP.'}, status=400)
            user.avatar = avatar

        user.save()
        audit(user, 'profile.updated', 'User', user.id, {'avatar_changed': bool(avatar)})
        return Response({'user': UserSerializer(user).data})


class AdminSearchView(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request):
        q = str(request.query_params.get('q', '')).strip()
        if len(q) < 2:
            return Response({'query': q, 'results': []})

        digits = ''.join(ch for ch in q if ch.isdigit())
        normalized_phone = normalize_phone(q) if len(digits) >= 10 else ''
        results = []

        user_q = Q(last_name__icontains=q) | Q(first_name__icontains=q) | Q(middle_name__icontains=q) | Q(full_name__icontains=q) | Q(email__icontains=q)
        if normalized_phone:
            user_q |= Q(phone__icontains=normalized_phone) | Q(phone__icontains=digits[-10:])
        for u in User.objects.filter(user_q).order_by('-created_at')[:8]:
            results.append({'type': 'user', 'id': u.id, 'title': u.full_name, 'subtitle': f'{u.phone} · {u.email or "без e-mail"} · {u.get_role_display()}', 'section': 'users'})

        order_q = Q(address_area__icontains=q) | Q(exact_address__icontains=q) | Q(recipient__full_name__icontains=q) | Q(customer__full_name__icontains=q) | Q(caregiver__full_name__icontains=q)
        if digits:
            try:
                order_q |= Q(pk=int(digits))
            except ValueError:
                pass
        for o in Order.objects.filter(order_q).select_related('customer', 'recipient', 'caregiver').order_by('-created_at')[:8]:
            results.append({'type': 'order', 'id': o.id, 'title': f'Заказ #{o.id}', 'subtitle': f'{o.recipient.full_name} · {o.address_area or o.exact_address or "адрес не указан"} · {o.get_status_display()}', 'section': 'orders'})

        # Remove duplicates while keeping the most relevant first matches.
        seen = set()
        unique = []
        for item in results:
            key = (item['type'], item['id'])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return Response({'query': q, 'results': unique[:12]})

class AdminUserDetailV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request, user_id):
        user = User.objects.filter(pk=user_id).first()
        if not user:
            return Response({'detail': 'Пользователь не найден.'}, status=404)
        recipients = Recipient.objects.filter(customer=user).order_by('-id')
        customer_orders = Order.objects.filter(customer=user).select_related('recipient', 'caregiver', 'care_plan').order_by('-created_at')
        caregiver_orders = Order.objects.filter(caregiver=user).select_related('customer', 'recipient', 'care_plan').order_by('-created_at')
        return Response({
            'user': UserSerializer(user).data,
            'stats': {
                'customer_orders': customer_orders.count(),
                'caregiver_orders': caregiver_orders.count(),
                'recipients': recipients.count(),
                'completed_orders': Order.objects.filter(Q(customer=user) | Q(caregiver=user), status='completed').count(),
                'active_orders': Order.objects.filter(Q(customer=user) | Q(caregiver=user), status__in=['confirmed','en_route','arrived','started','accepted','payment_authorized']).count(),
            },
            'recipients': list(recipients.values('id','full_name','birth_year','notes','consent_confirmed')),
            'customer_orders': [serialize_order(o, request.user) for o in customer_orders],
            'caregiver_orders': [serialize_order(o, request.user) for o in caregiver_orders],
            'audit': [
                {'id': a.id, 'action': a.action, 'entity_type': a.entity_type, 'entity_id': a.entity_id, 'details': a.details, 'created_at': a.created_at.isoformat()}
                for a in AuditLog.objects.filter(actor=user).order_by('-created_at')[:100]
            ],
        })


class BootstrapV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == 'admin':
            recipients = Recipient.objects.all()
            orders = Order.objects.select_related('customer', 'recipient', 'caregiver', 'care_plan').all()
            users = User.objects.all()
            incidents = Incident.objects.all()
            audit_rows = AuditLog.objects.select_related('actor').order_by('-created_at')[:200]
        elif user.role == 'customer':
            recipients = Recipient.objects.filter(customer=user)
            orders = Order.objects.filter(customer=user).select_related('customer', 'recipient', 'caregiver', 'care_plan')
            users = User.objects.filter(role='caregiver', is_active=True, is_verified=True)
            incidents = Incident.objects.filter(order__customer=user)
            audit_rows = AuditLog.objects.filter(actor=user).select_related('actor').order_by('-created_at')[:200]
        else:
            recipients = Recipient.objects.filter(orders__caregiver=user).distinct()
            orders = Order.objects.filter(caregiver=user).select_related('customer', 'recipient', 'caregiver', 'care_plan')
            users = User.objects.filter(role='caregiver', is_active=True, is_verified=True)
            incidents = Incident.objects.filter(order__caregiver=user)
            audit_rows = AuditLog.objects.filter(actor=user).select_related('actor').order_by('-created_at')[:200]

        return Response({
            'user': UserSerializer(user).data,
            'users': UserSerializer(users, many=True).data,
            'recipients': list(recipients.values('id', 'customer_id', 'full_name', 'birth_year', 'notes', 'consent_confirmed')),
            'plans': list(CarePlan.objects.filter(recipient__in=recipients).values('id', 'recipient_id', 'version', 'status', 'tasks', 'prohibitions', 'preferences', 'created_at')),
            'orders': [serialize_order(o, request.user) for o in orders.order_by('-start_at')],
            'incidents': list(incidents.values('id', 'order_id', 'severity', 'text', 'resolved', 'created_at')),
            'audit': [{'id': a.id, 'actor': a.actor.full_name, 'action': a.action, 'entity_type': a.entity_type, 'entity_id': a.entity_id, 'details': a.details, 'created_at': a.created_at.isoformat()} for a in audit_rows],
        })


def serialize_order(o, viewer):
    can_see_exact = viewer.role == 'admin' or o.customer_id == viewer.id or o.caregiver_id == viewer.id
    return {
        'id': o.id, 'customer': o.customer.full_name, 'customer_id': o.customer_id,
        'recipient': o.recipient.full_name, 'recipient_id': o.recipient_id,
        'caregiver': o.caregiver.full_name if o.caregiver else None, 'caregiver_id': o.caregiver_id,
        'status': o.status, 'status_label': o.get_status_display(), 'start_at': o.start_at.isoformat(),
        'end_at': o.end_at.isoformat(), 'hours': float(o.hours), 'rate': float(o.hourly_rate),
        'total': float(o.total_price), 'commission': float(o.platform_commission),
        'caregiver_amount': float(o.caregiver_amount), 'area': o.address_area,
        'address': o.exact_address if can_see_exact else '', 'plan_version': o.care_plan.version,
        'plan_id': o.care_plan_id, 'incidents': list(o.incidents.values('id', 'severity', 'text', 'resolved')),
        'report': ({'condition': o.report.condition, 'tasks_done': o.report.tasks_done, 'comment': o.report.comment} if hasattr(o, 'report') else None),
    }


class CreateOrderV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsCustomer]

    def post(self, request):
        recipient = Recipient.objects.filter(id=request.data.get('recipient_id'), customer=request.user).first()
        if not recipient:
            return Response({'detail': 'Получатель не найден.'}, status=404)
        plan = recipient.plans.filter(status='active').order_by('-version').first()
        if not plan:
            return Response({'detail': 'У получателя нет активного плана ухода.'}, status=400)
        start = parse_datetime(request.data.get('start_at', ''))
        end = parse_datetime(request.data.get('end_at', ''))
        if not start or not end or end <= start:
            return Response({'detail': 'Некорректные дата и время смены.'}, status=400)
        hours = Decimal(str(request.data.get('hours', 6)))
        rate = Decimal(str(request.data.get('rate', 350)))
        total = (hours * rate).quantize(Decimal('0.01'))
        commission = (total * Decimal('0.18')).quantize(Decimal('0.01'))
        caregiver_amount = total - commission
        o = Order.objects.create(
            customer=request.user, recipient=recipient, care_plan=plan,
            start_at=start, end_at=end, hours=hours, hourly_rate=rate,
            total_price=total, platform_commission=commission, caregiver_amount=caregiver_amount,
            address_area=request.data.get('area', ''), exact_address=request.data.get('address', ''),
            status='risk_check',
        )
        audit(request.user, 'order.created', 'Order', o.id, {'total': float(total)})
        return Response(serialize_order(o, request.user), status=201)


class AssignOrderV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request, order_id):
        with transaction.atomic():
            o = Order.objects.select_for_update().select_related('customer', 'recipient', 'care_plan').get(pk=order_id)
            caregiver = User.objects.filter(id=request.data.get('caregiver_id'), role='caregiver', is_active=True).first()
            if not caregiver:
                return Response({'detail': 'Исполнитель не найден.'}, status=404)
            if Order.objects.filter(
                caregiver=caregiver,
                start_at__lt=o.end_at,
                end_at__gt=o.start_at,
            ).exclude(pk=o.id).exclude(status__in=['cancelled', 'completed', 'customer_confirmed', 'settlement']).exists():
                return Response({'detail': 'У исполнителя уже есть пересекающаяся смена.'}, status=409)
            o.caregiver = caregiver
            o.status = 'caregiver_requested'
            o.save(update_fields=['caregiver', 'status', 'updated_at'])
            audit(request.user, 'order.assigned', 'Order', o.id, {'caregiver_id': caregiver.id})
        return Response(serialize_order(o, request.user))


class CaregiverAcceptV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsCaregiver]

    def post(self, request, order_id):
        with transaction.atomic():
            o = Order.objects.select_for_update().get(pk=order_id, caregiver=request.user)
            if o.status not in ('caregiver_requested', 'replacement', 'matching'):
                return Response({'detail': 'Заказ нельзя принять в текущем статусе.'}, status=409)
            conflict = Order.objects.filter(caregiver=request.user, start_at__lt=o.end_at, end_at__gt=o.start_at).exclude(pk=o.id).exclude(status__in=['cancelled', 'completed', 'customer_confirmed', 'settlement']).exists()
            if conflict:
                return Response({'detail': 'У вас есть пересекающаяся смена.'}, status=409)
            o.status = 'accepted'
            o.save(update_fields=['status', 'updated_at'])
            audit(request.user, 'order.accepted', 'Order', o.id)
        return Response(serialize_order(o, request.user))


class StartShiftV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsCaregiver]

    def post(self, request, order_id):
        o = Order.objects.filter(pk=order_id, caregiver=request.user).first()
        if not o:
            return Response({'detail': 'Смена не найдена.'}, status=404)
        if o.status not in ('accepted', 'confirmed', 'en_route', 'arrived'):
            return Response({'detail': 'Смену нельзя начать из текущего статуса.'}, status=409)
        o.status = 'started'
        o.save(update_fields=['status', 'updated_at'])
        audit(request.user, 'shift.started', 'Order', o.id)
        return Response(serialize_order(o, request.user))


class CompleteShiftV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsCaregiver]

    def post(self, request, order_id):
        o = Order.objects.filter(pk=order_id, caregiver=request.user).first()
        if not o:
            return Response({'detail': 'Смена не найдена.'}, status=404)
        if o.status != 'started':
            return Response({'detail': 'Смену можно завершить только из статуса «Идёт».'}, status=409)
        o.status = 'completed'
        o.save(update_fields=['status', 'updated_at'])
        audit(request.user, 'shift.completed', 'Order', o.id)
        return Response(serialize_order(o, request.user))


class ReportShiftV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsCaregiver]

    def post(self, request, order_id):
        o = Order.objects.filter(pk=order_id, caregiver=request.user).first()
        if not o:
            return Response({'detail': 'Смена не найдена.'}, status=404)
        report, _ = ShiftReport.objects.update_or_create(order=o, defaults={
            'condition': request.data.get('condition', 'no_change'),
            'tasks_done': request.data.get('tasks_done', []),
            'comment': request.data.get('comment', ''),
        })
        audit(request.user, 'shift.reported', 'Order', o.id, {'report_id': report.id})
        return Response({'ok': True, 'report_id': report.id})


class ReplaceOrderV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        o = Order.objects.filter(pk=order_id).first()
        if not o:
            return Response({'detail': 'Заказ не найден.'}, status=404)
        if request.user.role == 'customer' and o.customer_id != request.user.id:
            return Response({'detail': 'Нет доступа к этому заказу.'}, status=403)
        if request.user.role == 'caregiver' and o.caregiver_id != request.user.id:
            return Response({'detail': 'Нет доступа к этому заказу.'}, status=403)
        if request.user.role not in ('customer', 'caregiver', 'admin'):
            return Response({'detail': 'Нет доступа.'}, status=403)
        o.status = 'replacement'
        o.caregiver = None
        o.save(update_fields=['status', 'caregiver', 'updated_at'])
        audit(request.user, 'order.replacement_started', 'Order', o.id)
        return Response(serialize_order(o, request.user))


class ResolveIncidentV1View(APIView):
    authentication_classes = [BearerAuthentication]
    permission_classes = [IsAdmin]

    def post(self, request, incident_id):
        incident = Incident.objects.filter(pk=incident_id).first()
        if not incident:
            return Response({'detail': 'Инцидент не найден.'}, status=404)
        incident.resolved = not incident.resolved
        incident.save(update_fields=['resolved'])
        audit(request.user, 'incident.status_changed', 'Incident', incident.id, {'resolved': incident.resolved})
        return Response({'ok': True, 'resolved': incident.resolved})
