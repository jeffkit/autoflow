#encoding=utf-8
from django.contrib import admin
from workflow import models
from django.db.models import Q

class StateInline(admin.TabularInline):
  model = models.Transition

class WorkflowAdmin(admin.ModelAdmin):
  list_display = ['name','description','active']
  list_filter = ['name','active']
  search_fields = ['name','description']
  inlines = [StateInline]

admin.site.register(models.Workflow,WorkflowAdmin)

class StateAdmin(admin.ModelAdmin):
  list_display = ['name','picture','workflow','description','end']
  list_filter = ['workflow']
  search_fields = ['name','description']

admin.site.register(models.State,StateAdmin)

class TransitionAdmin(admin.ModelAdmin):
  list_display = ['name','workflow','destination']
  list_filter = ['workflow']
  search_fields = ['name']

admin.site.register(models.Transition,TransitionAdmin)

class StepAdmin(admin.ModelAdmin):
  list_display = ['process','state','last','transition','user','enter_time']
  list_filter = ['enter_time','leave_time']
  search_fields = ['comment']

admin.site.register(models.Step,StepAdmin)

class PropertyInline(admin.TabularInline):
  model = models.Property

class ProcessAdmin(admin.ModelAdmin):
  list_display = ['title','workflow','form','description','start','requester','state_icon']
  list_filter = ['workflow','state','start']
  search_fields = ['title','description']

  def queryset(self,request):
	qs = super(ProcessAdmin,self).queryset(request)
	if request.user.is_superuser:
	  return qs
	exp = Q(step__assign_to_user=request.user)
	groups = request.user.groups.all()
	if groups:
	  exp = Q(exp | Q(requester=request.user) | Q(step__assign_to_group__in=groups))
	else:
	  exp = Q(exp | Q(requester=request.user))
	return qs.filter(exp).distinct()

admin.site.register(models.Process,ProcessAdmin)
