from rest_framework.permissions import BasePermission


class IsAuthenticated(BasePermission):
    message = 'Требуется авторизация.'

    def has_permission(self, request, view):
        return bool(request.user and request.auth)


class IsAdmin(IsAuthenticated):
    message = 'Доступ разрешён только администратору.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == 'admin'


class IsCustomer(IsAuthenticated):
    message = 'Доступ разрешён только заказчику.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == 'customer'


class IsCaregiver(IsAuthenticated):
    message = 'Доступ разрешён только исполнителю.'

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == 'caregiver'
