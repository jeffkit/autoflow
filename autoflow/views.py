#encoding=utf-8
# Create your views here.
from django.forms.formsets import formset_factory
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse,HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template.context import RequestContext
from workflow.models import Workflow,Process,Step,State,Transition
from form.models import Form
from form.forms import DynamicForm
from workflow.forms import ProcessForm
from attachments.models import Attachment
from attachments.forms import AttachmentForm
from logger import log

Attachment_Formset = formset_factory(AttachmentForm)

@login_required
def create_process(request,flowID,formID=None,template='workflow/create_process.html',context={}):
  """
  创建一个新的流程实例，根据传入的flowID,FormID。
  """
  workflow =  Workflow.objects.get(pk=flowID)
  form = formID and Form.objects.get(pk=formID)
  if request.method == 'GET':
	# 创建表单
	process_form = ProcessForm()
	dynamic_form = DynamicForm(fields=form.sorted_fields(),data=None)
	attachment_formset = Attachment_Formset()
	context.update({'workflow':workflow,'form':dynamic_form,'process_form':process_form,'attachment_formset':attachment_formset})
	return render_to_response(template,RequestContext(request,context))
  else:
	#如果有表单则先保存表单，然后创建一个process，启动第一步。
	process_form = ProcessForm(request.POST)
	df = DynamicForm(fields=form.sorted_fields(),data=request.POST)

	if not process_form.is_valid():
	  context.update({'workflow':workflow,'form':df,'process_form':process_form})
	  return render_to_response(template,RequestContext(request,context))

	process = Process(workflow=workflow,requester=request.user,title=process_form.cleaned_data['process_title'],description=process_form.cleaned_data['process_description'])

	if df:
	  if not df.is_valid():
		context.update({'workflow':workflow,'form':df})
		return render_to_response(template,RequestContext(request,context))
	  else:
		process.form = form
		process.save()
		process.save_form(df)#保存表单数据

	step = process.next(user=request.user,comment = process.description)
	attachment_formset = Attachment_Formset(request.POST,request.FILES)
	for form in attachment_formset.forms:
	  if form.is_valid():
		form.save(request,step)

	return HttpResponseRedirect('/workflow/process/%d/'%process.id)

@login_required
def view_process(request,id,template='workflow/view_process.html',context={}):
  """
  查看流程详情：
  显示表单
  显示历史
  显示可用的操作(transition)
  如果当前用户是流程当前步骤的处理人，表单可编辑
  """
  def group_match(user,groups):
	user_groups = user.groups.all()
	for group in groups:
	 if group in user_groups:
	   return True
	return False

  process = Process.objects.get(pk=id)
  participators = process.handlers()
  log.debug(participators)

  if not (request.user in participators[0] or group_match(request.user,participators[1])):
	return HttpResponseForbidden("<h1>Permission Denied</h1>")

  if request.method == 'GET':
	form = process.get_form()
	history = process.history()
	assign = process. current_handler()
	history_ids = [step.pk for step in history]
	object_type = ContentType.objects.get_for_model(history[0])
	attachments = Attachment.objects.filter(content_type__pk=object_type.id,object_id__in=history_ids)

	#只有当前处理该步骤的人才可以编辑表单以及使用transitions
	handler = False
	transitions = None
	attachment_formset = None
	if assign[0] == request.user or (assign[1] and assign[1] in request.user.groups.all()):
	  handler = True
	  transitions = process.available_transition()
	  attachment_formset = Attachment_Formset()

	context.update({'process':process,
					'form':form,
					'history':history,
					'transitions':transitions,
					'handler':handler,
					'title':process.title,
					'last_step':history and history[0],
					'attachments':attachments,
					'attachment_formset':attachment_formset})

	return render_to_response(template,RequestContext(request,context))
  else:
	# 更新表单、处理transition
	if process.form:
	  df = DynamicForm(fields=process.form.sorted_fields(),data=request.POST)
	  if not df.is_valid():
		context.update({'form':df})
		return render_to_response(template,RequestContext(request,context)) #TODO 还有很多参数要传回去页面
	  else:
		process.save_form(df)#保存表单数据

	comment = request.POST.get('__comment__',None)
	transition_name = request.POST.get('__transition__',None)
	transition = Transition.objects.get(name=transition_name)
	if transition:
	  step = process.next(request.user,transition,comment)
	  attachment_formset = Attachment_Formset(request.POST,request.FILES)
	  for form in attachment_formset.forms:
		if form.is_valid():
		  form.save(request,step)
	return HttpResponseRedirect('/workflow/process/')


@login_required
def list_process(request,template='workflow/list_process.html',context={}):
  """
  列出与我有关的流程，不管是分配给我，还是分配给我所在的组，也不管状态如何。
  """
  process_list = Process.objects.get_by_user(request.user)
  return render_to_response(template,{'process_list':process_list})


@login_required
def worklist(request,template='workflow/worklist.html',context={}):
  """
  仅列出现在指派给我或我所在的组的流程
  """
  pass
