#encoding=utf-8
from django import forms

class ProcessForm(forms.Form):
  process_title = forms.CharField(label=u'标题')
  process_description = forms.CharField(label=u'说明',widget=forms.Textarea,required=False)
