#encoding=utf-8
from datetime import datetime

from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.contrib.auth.models import User,Group
from django.utils import simplejson
from django.db.models.query import QuerySet

from form.models import Form
from form.forms import DynamicForm
from logger import log

def make_object(d):
  """
  把字典变成可调用的对象，使得可以使用.来访问对象属性
  """
  class DictObject:
	def __init__(self,d,**kwargs):
	  print d
	  if d:
		self._dict = d
		for key,value in d.items():
		  setattr(self,key,value)
	  for key,value in kwargs.items():
		setattr(self,key,value)

  return DictObject(d)

def import_action(action):
  try:
	comps = action.split('.')
	action = __import__(action[:action.rindex('.')])
	for comp in comps[1:]:
	  action = getattr(action,comp)
	return action
  except:
	import sys
	log.error('%s:%s'%(sys.exc_info()[0],sys.exc_info()[1]))

class Workflow(models.Model):
  """
  流程定义模型
  """
  name = models.CharField(u'名称',max_length=50)
  description = models.TextField(u'描述')
  active = models.BooleanField(u'激活')

  def __unicode__(self):
	return self.name

  class Meta:
	verbose_name = u'工作流程'
	verbose_name_plural = u'工作流程'

  def find_start_transition(self):
	result = Transition.objects.filter(originating__isnull=True)
	if result:
	  return result[0]

class State(models.Model):
  """
  步骤模型，象征流程的某个步骤。
  """
  workflow = models.ForeignKey(Workflow,verbose_name='流程')
  name = models.CharField(u'名称',max_length=50)
  description = models.TextField(u'说明')
  assign_to_user = models.ForeignKey(User,verbose_name=u'默认处理人',blank=True,null=True)
  assign_to_group = models.ForeignKey(Group,verbose_name=u'默认处理组',blank=True,null=True)
  action = models.CharField(u'步骤处理器',max_length=100,help_text=u'如果指定处理器，该步骤将由计算机自动处理。',blank=True,null=True)
  end = models.BooleanField(u'结束步骤')
  icon = models.ImageField(upload_to='icons/state/',null=True,blank=True)
  is_decision = models.BooleanField(u'条件步骤',default=False)
  auto_start = models.BooleanField(u'自动开始',default=False)

  def __unicode__(self):
	return self.name

  class Meta:
	verbose_name = u'步骤'
	verbose_name_plural = u'步骤'

  def picture(self):
	if self.icon:
	  return '<img src="%s" title="%s" alt="%s"/>'%(self.icon.url,self.name,self.name)
	else:
	  return u'未定义'
  picture.allow_tags = True
  picture.short_description = u'图标'

class Transition(models.Model):
  """
  流程跳转定义
  """
  workflow = models.ForeignKey(Workflow,verbose_name=u'流程')
  name = models.CharField(u'名称',max_length=50)
  originating = models.ManyToManyField(State,verbose_name=u'原状态',related_name='source',blank=True,null=True)
  destination = models.ForeignKey(State,verbose_name=u'目标状态',related_name='to')
  condition = models.CharField(u'条件',max_length=200,blank=True,null=True)

  def __unicode__(self):
	return self.name

  class Meta:
	verbose_name = u'跳转'
	verbose_name_plural = u'跳转'

class ProcessManager(models.Manager):
  """
  流程实例的管理器
  """
  def get_by_user(self,user):
	"""
	查找与指定用户有关系的流程实例。指派给用户的、指派给用户所在组的都在查找范围内。
	"""
	exp = Q(assign_to_user=user)
	groups = user.groups.all()
	if groups:
	  exp = Q(exp | Q(assign_to_group__in=groups))
	result = super(ProcessManager,self).queryset().filter(exp).order_by('-last_modified')
	return result

class Process(models.Model):
  """
  流程实例。
  """
  workflow = models.ForeignKey(Workflow,verbose_name=u'流程')
  form = models.ForeignKey(Form,verbose_name=u'表单',blank=True,null=True)
  title = models.CharField(u'标题',max_length=200)
  requester = models.ForeignKey(User,verbose_name=u'发起人')
  start = models.DateTimeField(u'发起时间',auto_now_add=True)
  end = models.DateTimeField(u'结束时间',null=True,blank=True,editable=False)
  description = models.TextField(u'说明',null=True,blank=True)
  state = models.ForeignKey(State,verbose_name=u'状态',null=True,blank=True)
  form_version = models.IntegerField(u'表单版本',default=0,null=True,editable=False)
  last_modified = models.DateTimeField(u'最后修改时间',auto_now=True)

  objects = ProcessManager()

  def __unicode__(self):
	return self.title

  def state_icon(self):
	if self.state.icon:
	  return self.state.picture()
	else :
	  return self.state.name

  state_icon.allow_tags = True
  state_icon.short_description = u'状态'

  def set_property(self,name,value):
	property = self.get_property(name,True)
	if property:
	  log.debug(type(property))
	  property.value = value
	else:
	  property = Property(process=self,type=2,name=name,value=value,value_type=type(value).__name__)
	property.save()
	return property

  def get_property(self,name,model=False):
	try:
	  property = self.property_set.get(type=2,name=name)
	  if model:
		log.debug('return a property object')
		return property
	  else:
		log.debug('return a exact_value')
		return property.exact_value
	except:
	  return None

  def get_properties(self):
	properties = self.property_set.filter(type=2)
	if properties:
	  data = {}
	  for prop in properties:
		data.update({prop.name:prop.exact_value})
	  return data
	return {}

  def history(self):
	"""
	查找该流程实例的历史，使用按时间倒序的方法搜索。
	"""
	history = self.step_set.all().select_related().order_by('-enter_time')
	return history

  def handlers(self):
	"""
	找到该流程所牵涉到的所有人或组
	"""
	users = [self.requester]
	groups = []
	history = self.history()
	for step in history:
	  if step.assign_to_user and step.assign_to_user not in users:
		users.append(step.assign_to_user)
	  if step.assign_to_group and step.assign_to_group not in groups:
		groups.append(step.assign_to_group)
	  if step.user and step.user not in users:
		users.append(step.user)
	return users,groups

  def decide(self):
	"""
	根据流程的信息决定，下一次应该执行的操作，如果没有可用的操作，则返回空值。
	"""
	transitions = self. available_transition()
	for transition in transitions:
	  process = make_object(self.get_properties())
	  form = self.get_form()
	  if form.is_valid():
		form = make_object(form.cleaned_data)
	  else:
		form = None
	  log.debug('tansition.condition:%s'%transition.condition)
	  if eval(transition.condition): # form.fieldname == 10  或 process.propname < 100 ，condition可以是任意合法的python条件表达式
		return transition
	return None

  def next(self,user,transition=None,comment=None):
	"""
	走流程的下一步。
	做一些啥？如果有指定操作，则找到下一步的状态，创建一个新步骤。
	"""
	# step1: 找到下一步的操作和验证操作的合法性
	if not transition:
	  # 如果没有指定，则有可能是流程开始或当前步骤是decision步骤
	  if self.state and self.state.is_decision:
		transition = self.decide()
		if not transition:
		  return None #TODO raise an Exception intead
	  elif not self.state:
		# 如果是第一步
		transition = self.workflow.find_start_transition()
	  else:
		# 既不是第一步，又不是decision步骤，不能这样做的噢。
		return None
	else:
	  # 如果指定了操作，则要检验一下是否合法
	  if transition not in self.available_transition():
		return None # TODO raise an Exception instead

	# step2: 更新流程的状态
	last = self.state #旧状态
	state = transition.destination
	self.state = state
	# 如果当前步骤是结束步骤，则将流程标识为结束
	if self.state.end:
	  self.end = datetime.now()
	self.save()

	# step3:如果存在当前步骤，则离开当前步骤
	c_step = self.current_step()
	if c_step:
	  c_step.leave()

	# step4:开始新的步骤
	step = Step(process=self,transition=transition,last=last,state=state,user=user,assign_to_user=state.assign_to_user,assign_to_group=state.assign_to_group,comment=comment)
	step.start()#处理该步骤的处理人
	return step

  def available_transition(self):
	return self.state.source.all()

  def current_step(self):
	steps = Step.objects.filter(process=self).order_by('-enter_time')
	if steps:
	  return steps[0]

  def current_handler(self):
	"""
	获得流程当前步骤的处理人
	"""
	c_step = self. current_step()
	return c_step.assign_to_user,c_step.assign_to_group

  def get_form(self):
	"""
	获得该流程的表单
	"""
	properties = self.property_set.filter(type=1,version=self.form_version)
	data = {}
	for prop in properties:
	  value = prop.value
	  if value.startswith('[') and value.endswith(']'):
		value = simplejson.loads(value)
	  data[prop.name] = value
	form = DynamicForm(fields=self.form.sorted_fields(),data=data)
	return form

  def save_form(self,form):
	"""
	保存流程的表单
	"""
	data = form.cleaned_data
	version = self.form_version + 1
	for key in data.keys():
	  if data[key]: #只保存有值的表单项
		log.debug(data[key])
		if type(data[key]) == list or type(data[key]) == QuerySet:
		  value = [str(item) for item in data[key]]
		  value = simplejson.dumps(value)
		else:
		  value = str(data[key])
		prop = Property(process=self,version=version,type=1,name=key,value=value)
		prop.save()
	self.form_version = version
	self.save()

  class Meta:
	verbose_name = u'工单'
	verbose_name_plural = u'工单'

class Property(models.Model):
  """
  每次信令或数据提取请求的查询条件。
  """
  VALUE_TYPES = (
	  ('int',u'整数'),
	  ('float',u'浮点数'),
	  ('long',u'长整型'),
	  ('complex',u'复数'),
	  ('bool',u'布尔值'),
	  ('str',u'字符串')
  )
  process = models.ForeignKey(Process,verbose_name=u'请求')
  type = models.IntegerField(u'类型',choices=((1,u'表单'),(2,u'流程属性')))
  version = models.IntegerField(u'版本',default=0)
  name = models.CharField(u'条件名',max_length=20)
  value = models.TextField(u'条件值')
  value_type = models.CharField(u'值类型',max_length=50,blank=True,null=True,choices=VALUE_TYPES)

  class Meta:
	verbose_name = u'属性'
	verbose_name_plural = u'属性'

  @property
  def exact_value(self):
	"""
	获得property的真实值。
	目前为止，所支持的类型都是可以通过简单的类型转换即可
	"""
	if not self.value_type:
	  return self.value

	if self.value_type == 'str':
	  return self.value
	# 以后有增加其他类型的数值支持，在此添加转换方法即可

	convert = '%s(\'%s\')'%(self.value_type,self.value)
	try:
	  return eval(convert)
	except:
	  log.warn('unknow type,return string value')
	  return self.value #未能识别的类型


class Step(models.Model):
  """
  State的实例，实际上是流程的一个步骤。
  """
  last = models.ForeignKey(State,verbose_name=u'上一步骤',related_name=u'before',null=True,blank=True)
  state = models.ForeignKey(State,verbose_name=u'步骤',related_name=u'after')
  comment = models.TextField(u'备注',null=True,blank=True)
  process = models.ForeignKey(Process,verbose_name=u'流程实例')
  user = models.ForeignKey(User,verbose_name=u'修改人',related_name='assign_from',null=True,blank=True)
  assign_to_user = models.ForeignKey(User,verbose_name=u'处理人',blank=True,null=True,related_name='assign_to')
  assign_to_group = models.ForeignKey(Group,verbose_name=u'处理组',blank=True,null=True)
  transition = models.ForeignKey(Transition,verbose_name=u'操作')
  enter_time = models.DateTimeField(u'进入时间',auto_now_add=True)
  leave_time = models.DateTimeField(u'离开时间',null=True,blank=True)

  def __unicode__(self):
	return self.state.name

  class Meta:
	verbose_name = u'步骤实例'
	verbose_name_plural = u'步骤实例'

  def start(self):
	"""
	本步骤开始执行，最主要的工作是找到处理本步骤的人或组。
	"""
	log.info('entering step %s'%self.state.name)
	# step1,不管三七二十一，脚本一定要调用D。
	result = False #默认脚本的处理结果是没有处理步骤assign的问题。
	if self.state.action:
	  action = import_action(self.state.action)
	  if action:
		result = action(self) # 调用脚本，得到返回结果。这个是可以实时添加脚本并调用的。
	  else:
		pass #没能成功import指定的方法，不执行脚本

	if not self.state.end:
	  #如果该流程没有结束，则设置一下该步骤的处理人。如果结束则无需再处理。
	  if not self.state.is_decision: # 本步骤是条件跳转步骤，不需要人工处理
		if not (self.assign_to_user or self.assign_to_group or result):
		  self.assign_to_user = self.process.requester

	self.save()
	# 有可能需要通知一下用户？那在这里加上处理逻辑吧。

	if self.state.is_decision and self.state.auto_start:
	  self.process.next()

  def leave(self):
	"""
	离开本步骤
	"""
	log.info('leaving step step %s'%self.state.name)
	self.leave_time = datetime.now()
	self.save()
