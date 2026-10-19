import json
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import User, Recipient, CarePlan, Order, ShiftReport, Incident, AuditLog

def index(request): return render(request,'index.html')

def serialize_order(o):
    return {'id':o.id,'customer':o.customer.full_name,'customer_id':o.customer_id,'recipient':o.recipient.full_name,'recipient_id':o.recipient_id,'caregiver':o.caregiver.full_name if o.caregiver else None,'caregiver_id':o.caregiver_id,'status':o.status,'status_label':o.get_status_display(),'start_at':o.start_at.isoformat(),'end_at':o.end_at.isoformat(),'hours':float(o.hours),'rate':float(o.hourly_rate),'total':float(o.total_price),'commission':float(o.platform_commission),'caregiver_amount':float(o.caregiver_amount),'area':o.address_area,'address':o.exact_address,'plan_version':o.care_plan.version,'plan_id':o.care_plan_id,'incidents':list(o.incidents.values('id','severity','text','resolved')),'report':({'condition':o.report.condition,'tasks_done':o.report.tasks_done,'comment':o.report.comment} if hasattr(o,'report') else None)}

def bootstrap(request):
    return JsonResponse({'users':list(User.objects.values('id','full_name','role','phone','email','is_verified')),'recipients':list(Recipient.objects.values('id','customer_id','full_name','birth_year','notes','consent_confirmed')),'plans':list(CarePlan.objects.values('id','recipient_id','version','status','tasks','prohibitions','preferences')),'orders':[serialize_order(o) for o in Order.objects.select_related('customer','recipient','caregiver','care_plan').prefetch_related('incidents').order_by('-start_at')],'incidents':list(Incident.objects.values('id','order_id','severity','text','resolved','created_at')),'audit':[{'id':a.id,'actor':a.actor.full_name,'action':a.action,'entity_type':a.entity_type,'entity_id':a.entity_id,'details':a.details,'created_at':a.created_at.isoformat()} for a in AuditLog.objects.select_related('actor').order_by('-created_at')[:200]]})

def audit(actor,action,entity,details=None): AuditLog.objects.create(actor=actor,action=action,entity_type=entity.__class__.__name__,entity_id=entity.id,details=details or {})

@csrf_exempt
def create_order(request):
    d=json.loads(request.body or '{}'); customer=User.objects.get(id=d['customer_id']); recipient=Recipient.objects.get(id=d['recipient_id']); plan=recipient.plans.filter(status='active').latest('version'); hours=Decimal(str(d.get('hours',6))); rate=Decimal(str(d.get('rate',350))); total=hours*rate; commission=total*Decimal('0.18'); caregiver=total-commission
    from django.utils.dateparse import parse_datetime
    start=parse_datetime(d['start_at']); end=parse_datetime(d['end_at']); o=Order.objects.create(customer=customer,recipient=recipient,care_plan=plan,start_at=start,end_at=end,hours=hours,hourly_rate=rate,total_price=total,platform_commission=commission,caregiver_amount=caregiver,address_area=d.get('area','Центральный район'),exact_address=d.get('address',''))
    audit(customer,'order.created',o,{'total':float(total)}); return JsonResponse(serialize_order(o))

@csrf_exempt
def assign_order(request,order_id):
    d=json.loads(request.body or '{}'); o=get_object_or_404(Order,pk=order_id); c=get_object_or_404(User,pk=d['caregiver_id'],role='caregiver'); o.caregiver=c; o.status='assigned'; o.save(); admin=User.objects.filter(role='admin').first(); audit(admin,'order.assigned',o,{'caregiver_id':c.id}); return JsonResponse(serialize_order(o))

@csrf_exempt
def start_shift(request,order_id):
    o=get_object_or_404(Order,pk=order_id); o.status='started'; o.save(); audit(o.caregiver,'shift.started',o); return JsonResponse(serialize_order(o))

@csrf_exempt
def complete_shift(request,order_id):
    o=get_object_or_404(Order,pk=order_id); o.status='completed'; o.save(); audit(o.caregiver,'shift.completed',o); return JsonResponse(serialize_order(o))

@csrf_exempt
def report_shift(request,order_id):
    o=get_object_or_404(Order,pk=order_id); d=json.loads(request.body or '{}'); r, _=ShiftReport.objects.update_or_create(order=o,defaults={'condition':d.get('condition','no_change'),'tasks_done':d.get('tasks_done',[]),'comment':d.get('comment','')}); audit(o.caregiver,'shift.reported',o,{'report_id':r.id}); return JsonResponse({'ok':True,'report_id':r.id})

@csrf_exempt
def replace_order(request,order_id):
    o=get_object_or_404(Order,pk=order_id); o.status='replacement'; o.caregiver=None; o.save(); admin=User.objects.filter(role='admin').first(); audit(admin,'order.replacement_started',o); return JsonResponse(serialize_order(o))

@csrf_exempt
def resolve_incident(request,incident_id):
 i=get_object_or_404(Incident,pk=incident_id); i.resolved=not i.resolved; i.save(); actor=User.objects.filter(role='admin').first(); audit(actor,'incident.status_changed',i,{'resolved':i.resolved}); return JsonResponse({'ok':True,'resolved':i.resolved})
