from flask import Flask, render_template, url_for, request, jsonify
import traceback
import re
from sc_model import SC
import torch
import json
from utils import norm_text, find_index, reduce_wrong_word_test, handle_punctuation, parallel_index, find_true, exception_punctuation, check_cap
import time
import ast
import math
import requests
from starlette.responses import Response
import logging
import uuid
from underthesea import sent_tokenize
import rule
from rule import check_viethoa, matching_spaces, matching_predefined, mapping_cms

from fastapi import FastAPI
import nest_asyncio
import uvicorn
from pydantic import BaseModel
from utils import *
from typing import List
import torch
import logging
import os
import re
import string
import pandas as pd
import unicodedata

def is_url(input_txt):
	url_regex = r"[(http(s)?):\/\/(www\.)?a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)"
	return re.match(url_regex, input_txt) is not None

def is_valid_email(input_txt):
	email_regex = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
	return re.match(email_regex, input_txt) is not None

def norm_text(text):
	text = unicodedata.normalize('NFC', text)
	#text = text.lower()
	text = re.sub(r"òa", "oà", text)
	text = re.sub(r"óa", "oá", text)
	text = re.sub(r"ỏa", "oả", text)
	text = re.sub(r"õa", "oã", text)
	text = re.sub(r"ọa", "oạ", text)
	text = re.sub(r"òe", "oè", text)
	text = re.sub(r"óe", "oé", text)
	text = re.sub(r"ỏe", "oẻ", text)
	text = re.sub(r"õe", "oẽ", text)
	text = re.sub(r"ọe", "oẹ", text)
	text = re.sub(r"ùy", "uỳ", text)
	text = re.sub(r"úy", "uý", text)
	text = re.sub(r"ủy", "uỷ", text)
	text = re.sub(r"ũy", "uỹ", text)
	text = re.sub(r"ụy", "uỵ", text)
	return text

def separate_punctuation_with_space(text):
	text = text.replace("","-")
	for i in string.punctuation:
		text = text.replace(i, " "+i+" ")
	text = re.sub(' +', ' ', text)
	return text

def reverse(text):
	res = []
	mapping = {}
	cnt = 0
	for idx, i in enumerate(text.split(' ')):
		out = separate_punctuation_with_space(norm_text(i.lower())).strip()
		res.append(out)
		for j in out.split(' '):
			mapping[cnt] = idx
			cnt += 1
	return mapping, " ".join(res)
		

logging.basicConfig(level=logging.DEBUG)

device = "cuda" if torch.cuda.is_available() else "cpu"

from transformers import pipeline

if device == "cuda":
	logging.info("Use GPU")
	corrector = pipeline("text2text-generation", model="./models/", device=0)
else:
	logging.info("Use CPU")
	corrector = pipeline("text2text-generation", model="./models/")

app = FastAPI()
MAX_LENGTH = 512
batch_size = 32


def check_sent_new(lst):
	lst = [separate_punctuation_with_space(norm_text(x.lower())).strip() for x in lst]
	res = {}
	predictions = corrector(lst, max_length=MAX_LENGTH, batch_size=batch_size)
	for idx1, (text, pred) in enumerate(zip(lst, predictions)):
		# #print(text, pred)
		text = separate_punctuation_with_space(norm_text(text.lower())).strip()
		try:
			lst_err_pos = []
			detail = []
			for idx, (i,j) in enumerate(zip(text.lower().split(' '), pred['generated_text'].lower().split(' '))):
				if i != j:
					if "..." in j:
						continue
					lst_err_pos.append(idx)
					detail.append(i+" -> "+j)
			if len(lst_err_pos) > 0:
				res[idx1] = {"sentence": text, "generated":pred['generated_text'], "error_index" : lst_err_pos, "suggestion":detail}
			else:
				# #print(text, len(lst_err_pos))
				res[idx1] = {"sentence": text, "generated":text, "error_index" : [], "suggestion":[]}
		except Exception as e:
			print(e)
			continue
	return {"status": "Success", "data" : res}


from logging.handlers import TimedRotatingFileHandler

formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')


def setup_logger(name, log_file, level=logging.INFO):
	"""To setup as many loggers as you want"""

	handler = TimedRotatingFileHandler(log_file,
									   when="d",
									   interval=30,
									   backupCount=5)      
	handler.setFormatter(formatter)

	logger = logging.getLogger(name)
	logger.setLevel(level)
	logger.addHandler(handler)

	return logger

with open("app_logger.log","w") as f:
    f.write("")

mylogger = setup_logger("app_logger","app_logger.log")

def create_timed_rotating_log(path):
	""""""
	logger = logging.getLogger("Rotating Log")
	logger.setLevel(logging.INFO)
	
	handler = TimedRotatingFileHandler(path,
									   when="d",
									   interval=30,
									   backupCount=5)
	logger.addHandler(handler)

	return logger

log_file = "/logs/requests.log"

os.makedirs("/logs/", exist_ok=True)
if not os.path.exists(log_file):
    with open(log_file,"w") as f:
        f.write("")

logger = create_timed_rotating_log(log_file)


batch_size = 16
id_doc = 0
device = "cuda" if torch.cuda.is_available() else "cpu"
model_path = "model.bin"
model = SC.load(model_path).to(device)
model.eval()
with open('started.txt','w') as f:
	f.write('1')

error_message = {
	2000 : {
			"errorCode": 2000,
			"errorMessage": "Success"
		},
	4000:{
			"errorCode": 4000,
			"errorMessage": "Request is invalid"
		},
	4150:{
			"errorCode": 4150,
			"errorMessage": "Bad data"
		},
	5000:{
			"errorCode": 5000,
			"errorMessage": "Internal server error"
		}
}

def check_and_reduce(word):
	if word not in model.vocab:
		return reduce_wrong_word_test(word)
	else:
		return word

def write_file(s):
	if len(s)>1:
		path = "documents.txt" 
		f = open(path, "a")
		for sent in s:
			f.write(sent + "\n")
		f.close()

		
def sep_paragraph(text, max_len_per_paragraph=300):
	lst_sen = sent_tokenize(text)
	# #print(len(lst_sen))
	lst_p = []
	lst_idx = [0]
	cur_par = lst_sen[0]
	for idx, i in enumerate(lst_sen[1:]):
		l = len(i.split(' '))
		if len(cur_par.split(' ')) + l > max_len_per_paragraph:
			lst_p.append(cur_par)
			lst_idx.append(lst_idx[-1] + len(cur_par.split(' ')))
			cur_par = i
		else:
			cur_par += " "+ i
		if idx == len(lst_sen) - 2:
			cur_par += " "+ i
			lst_p.append(cur_par)
			lst_idx.append(lst_idx[-1] + len(cur_par.split(' ')))
			break
	return lst_p, lst_idx[:-1]
		
def predict_sent(text, start_idx = 0):
	s = []
	raw_text = text
	text = exception_punctuation(text)
	text = handle_punctuation(text)
	##print(text)
	# #print(text)
	s.append(text)
	s1 = [sent.split() for sent in s]
	s2 = [[check_and_reduce(norm_text(word.lower())) for word in sent] for sent in s1]
	##print(s2)
#     #print(s2)
	# check maximum length
	# s2 = s2[:100]
	check, _, _ = model(s2)
	##print(check.shape)
	if check.dim() == 0:
		check = torch.unsqueeze(check,dim=0)
		##print(check.shape)
	# add detach to remove memory consuming in GPU 
	check = check.detach().cpu()
	c = torch.round(check)
	if len(c.shape) == 1:
		c = c.unsqueeze(0)
	c = list(c[0])
	idx = []
	for i in range(len(c)):
		if c[i] == 1:
			idx.append(i)
	# empty cache
	torch.cuda.empty_cache()
	return {"error_index" : [x + start_idx for x in parallel_index(raw_text, idx)], "text": raw_text}


def fix_index(json_data):
	lst_data = []
	text_block = json_data['text_blocks']
	for item in text_block:
		for t in item:
			text = t['text']
			##print(text)
			lst_p, lst_idx = sep_paragraph(text,200)
			if len(lst_p) == 0:
				lst_p = [text]
				lst_idx = [0]
			final_text = ""
			lst_error = []
			##print(lst_idx)
			# #print("FIX")
			for i,j in zip(lst_p, lst_idx):
				# norm cms
				# #print(i,j)
				norm_error = []
				match_spaces = matching_spaces(i)
				# #print("matching spaces : ",match_spaces)
				#for ms in match_spaces:
					
				out = predict_sent(i,j)
				final_text += out['text']
				final_text += " "
				lst_error += out['error_index']
			if len(lst_error) > 0:
				t['error_index'] = lst_error
				lst_data.append(t)
	text_block = json_data['table_cells']
	for t in text_block:
		text = t['text']
		##print(text)
		lst_p, lst_idx = sep_paragraph(text,200)
		if len(lst_p) == 0:
			lst_p = [text]
			lst_idx = [0]
		final_text = ""
		lst_error = []
		##print(lst_idx)
		for i,j in zip(lst_p, lst_idx):
			out = predict_sent(i,j)
			final_text += out['text']
			final_text += " "
			lst_error += out['error_index']
		if len(lst_error) > 0:
			t['error_index'] = lst_error
			lst_data.append(t)
	return lst_data, 200
		

	
def find_index_line_vtnet(json_data):
	ori_box = []
	len_line = []
	len_sent = []
	s = []
	rep = []
	sent = ""
	prep_len_line = []
	prep_ori_box = []
	try:
		for line in json_data:
			prep_len_line = []
			prep_ori_box = []
			line["value"] = " ".join(line["value"].split())
			text = exception_punctuation(line["value"])
			text = handle_punctuation(text)
			prep_len_line.append(len(text.split()))
			prep_ori_box.append(line)
			if len(text.split())<=512 and len(text.split()) >= 2:
				s.append(text)
				len_line += prep_len_line
				ori_box += prep_ori_box
	except:
		logging.error('Failed to process text', exc_info=True)
		return error_message[4000], 400
	write_file(s)
	
	# fix loi dau cau
#     punctuation_check = [".",":","?","!"]
#     for idx, query in enumerate(ori_box):
#         flag = 0
#         tmp = []
#         for idx2, itm in enumerate(query['value'].split(' ')):
#             if flag == 1:
#                 if not itm[0].isupper():
#                     #print(idx2)
#                     tmp.append(idx2)
#                 flag = 0
#             #print(itm, itm.strip()[-1], itm.strip()[-1] in punctuation_check)
#             if itm.strip()[-1] in punctuation_check:
#                 flag = 1
#         ori_box[idx]['error_index'] = tmp
#         ori_box[idx]['capital_error_index'] = tmp
#         ori_box[idx]['spell_error_index'] = []
	
#     for i in ori_box:
#         #print("item ",i)
	
	s1 = [sent.split()[:500] for sent in s]
	len_sent = list(map(len, s1))
	s2 = [[check_and_reduce(norm_text(word.lower())) for word in sent] for sent in s1]
	
	# cms and rule here
	s_rule = [' '.join(x) for x in s1]
	rule_err = []
	for i in s_rule:
		# err = check_viethoa(i)
		# #print("Viet hoa ",i,err)
		err = []
		# err2 = mapping_cms(i)
		err2 = []
		err.extend(err2)
		rule_err.append(list(set(err)))
		
	
	batch = math.ceil(len(s)/batch_size)
	if batch == 0:
		batch = 1
	error_index = []
	with torch.no_grad():
		for i in range(0,batch,1):
			check, _, _ = model(s2[(batch_size*i):(batch_size*(i+1))])
			check = check.cpu().detach()
			c = torch.round(check)
			if len(c.shape) == 1:
				c = c.unsqueeze(0)
			idx_= find_true(c,  s1[(batch_size*i):(batch_size*(i+1))], s[(batch_size*i):(batch_size*(i+1))], model.vocab)
			error_index += idx_
#     #print("find index ", len_line, len_sent, error_index)
	
	ans = find_index(len_line, len_sent, error_index)
	lst_err_idx = []
	for i, j in zip(error_index, rule_err):
		# #print(i,j)
		if i == []:
			tmp = j
		elif j == []:
			tmp = i
		else:
			tmp = i
			tmp.extend(j)
		tmp = list(set(tmp))
		tmp.sort()
		lst_err_idx.append(tmp)
		
	# verify spell error index 
	for i in range(len(ori_box)):
		try:
			if ans[i]:
				# #print("parallel spell ",parallel_index(ori_box[i]["value"], ans[i]))
				if ori_box[i]["error_index"] == [] or 'error_index' not in ori_box[i]:
					ori_box[i]["error_index"] = parallel_index(ori_box[i]["value"], ans[i])
					ori_box[i]["spell_error_index"] = ori_box[i]["error_index"]
				else:
					tmp = parallel_index(ori_box[i]["value"], ans[i])
					for g in tmp:
						if g not in ori_box[i]["error_index"]:
							ori_box[i]["error_index"].append(g)
							ori_box[i]["spell_error_index"].append(g)
				# #print(ori_box[i],ori_box[i]["value"], ans[i])
				
				# #print(ori_box[i],ori_box[i]["value"], ans[i])
				# rep.append(ori_box[i])
		except Exception as e:
			print("Done ",ans[i],ori_box[i]["value"])
	ans = find_index(len_line, len_sent, lst_err_idx)
	# #print("after get cap ",ans, lst_err_idx)
	# #print("dan", ans)
	# ans = find_index(len_line, len_sent, error_index)
	for i in range(len(ori_box)):
		try:
			if ans[i]:
				tmp = parallel_index(ori_box[i]["value"], ans[i])
				if "error_index" not in ori_box[i]:
					ori_box[i]["error_index"] = []
					ori_box[i]["spell_error_index"] = []
					ori_box[i]["capital_error_index"] = []
				for j in tmp:
					if j not in ori_box[i]["error_index"]:
						ori_box[i]["capital_error_index"].append(j)
						ori_box[i]["error_index"].append(j)
					else:
						ori_box[i]["spell_error_index"].remove(j)
						ori_box[i]["capital_error_index"].append(j)
							
		except Exception as e:
			print(e)
			# #print("Done ",ans[i],ori_box[i])
	for i in ori_box:
		# #print("item ",i)
		if 'error_index' in i:
			i['error_index'] = list(set(i['error_index']))
			i['spell_error_index'] = list(set(i['spell_error_index']))
			i['capital_error_index'] = list(set(i['capital_error_index']))
			rep.append(i)
	torch.cuda.empty_cache()
	return rep, 200

def find_index_line(json_data):
#     if "threshold" in json_data.keys():
#         threshold = json_data['threshold']
#     else:
#         threshold = 0.5
	ori_box = []
	len_line = []
	len_sent = []
	s = []
	rep = []
	sent = ""
	prep_len_line = []
	prep_ori_box = []
	try:
		for line in json_data:
#             if d[0]["bbox"][1] <0:
#                 continue
			prep_len_line = []
			prep_ori_box = []
			line["text"] = " ".join(line["text"].split())
			text = exception_punctuation(line["text"])
			text = handle_punctuation(text)
			sent = sent + " "  + text
			prep_len_line.append(len(text.split()))
			prep_ori_box.append(line)
			if len(sent.split())<=512:
				s.append(sent)
				len_line += prep_len_line
				ori_box += prep_ori_box
			sent = ""
	except:
		return error_message[4000], 400
	s1 = [sent.split()[:500] for sent in s]
	len_sent = list(map(len, s1))
	s2 = [[check_and_reduce(norm_text(word.lower())) for word in sent] for sent in s1]
	# cms and rule here
	s_rule = [' '.join(x) for x in s1]
	rule_err = []
	for i in s_rule:
		err = check_viethoa(i)
		# #print("Viet hoa ",i,err)
		# err = []
		# err2 = mapping_cms(i)
		err2 = []
		err.extend(err2)
		rule_err.append(list(set(err)))
		
	
	batch = math.ceil(len(s)/batch_size)
	if batch == 0:
		batch = 1
	error_index = []
	with torch.no_grad():
		for i in range(0,batch,1):
			check, _, _ = model(s2[(batch_size*i):(batch_size*(i+1))])
			check = check.cpu().detach()
			c = torch.round(check)
			if len(c.shape) == 1:
				c = c.unsqueeze(0)
			idx_= find_true(c,  s1[(batch_size*i):(batch_size*(i+1))], s[(batch_size*i):(batch_size*(i+1))], model.vocab)
			error_index += idx_
			
#     #print("find index ", len_line, len_sent, error_index)
	
	ans = find_index(len_line, len_sent, error_index)
	lst_err_idx = []
	for i, j in zip(error_index, rule_err):
		#print(i,j)
		if i == []:
			tmp = j
		elif j == []:
			tmp = i
		else:
			tmp = i
			tmp.extend(j)
		tmp = list(set(tmp))
		tmp.sort()
		lst_err_idx.append(tmp)
		
	# verify spell error index 
	for i in range(len(ori_box)):
		if 'error_index' not in ori_box[i]:
			ori_box[i]["error_index"] = []
			ori_box[i]["spell_error_index"] = []
			ori_box[i]["capital_error_index"] = []
		try:
			if ans[i]:
				# #print("parallel spell ",parallel_index(ori_box[i]["text"], ans[i]))
				# #print(ori_box[i])
				if ori_box[i]["error_index"] == []:
					ori_box[i]["error_index"] = parallel_index(ori_box[i]["text"], ans[i])
					ori_box[i]["spell_error_index"] = ori_box[i]["error_index"].copy()
					ori_box[i]["capital_error_index"] = []
				else:
					tmp = parallel_index(ori_box[i]["text"], ans[i])
					for g in tmp:
						if g not in ori_box[i]["error_index"]:
							ori_box[i]["error_index"].append(g)
							ori_box[i]["spell_error_index"].append(g)
				# #print(ori_box[i],ori_box[i]["value"], ans[i])
				
				# rep.append(ori_box[i])
		except Exception as e:
			print(e)
			# #print("Done ",ans[i],ori_box[i]["text"])
	
#     #print(lst_err_idx)
	# #print(len_line, len_sent, lst_err_idx)
	ans = find_index(len_line, len_sent, rule_err)
	# #print("after get cap ",ans, rule_err)
	# #print("dan", ans)
	# ans = find_index(len_line, len_sent, error_index)
	for i in range(len(ori_box)):
		try:
			# #print("before add cap : ",ori_box[i])
			if ans[i]:
				tmp = parallel_index(ori_box[i]["text"], ans[i])
				# #print(ori_box[i], tmp)
				for j in tmp:
					if j not in ori_box[i]["error_index"]:
						ori_box[i]["capital_error_index"].append(j)
						ori_box[i]["error_index"].append(j)
					else:
						ori_box[i]["spell_error_index"].remove(j)
						ori_box[i]["capital_error_index"].append(j)
							
		except Exception as e:
			print(e)
			# #print("Done ",ans[i],ori_box[i])
	for i in ori_box:
		# #print("item ",i)
		if 'error_index' in i and len(i['error_index']) > 0:
			i['error_index'] = list(set(i['error_index']))
			i['spell_error_index'] = list(set(i['spell_error_index']))
			i['capital_error_index'] = list(set(i['capital_error_index']))
			rep.append(i)
	torch.cuda.empty_cache()
	return rep, 200

from langdetect import detect_langs

def check_lang_doc(json_data):
	sum_v = 0
	fk = 0
	cnt = 0
	
	try:
		for d in json_data["text_blocks"]:
			for j in d:
				if j['id_page'] < 3:
					if len(j['text'].split(' ')) >= 10:
						res = detect_langs(j['text'])
						sum_v += 1
						if res[0].lang != 'vi':
							cnt += 1
				else:
					fk = 1
					break
			if fk == 1:
				break
		if 1.0 * cnt / sum_v > 0.3:
			# #print(cnt, sum_v)
			return 1
		return 0
	except Exception as e:
		print(e)
		return 0


	
# def find_index_line(json_data):
#     if "threshold" in json_data.keys():
#         threshold = json_data['threshold']
#     else:
#         threshold = 0.5
#     ori_box = []
#     len_line = []
#     len_sent = []
#     s = []
#     rep = []
#     sent = ""
#     prep_len_line = []
#     prep_ori_box = []
#     try:
#         for d in json_data["text_blocks"]:
#             if d[0]["bbox"][1] <0:
#                 continue
#             prep_len_line = []
#             prep_ori_box = []
#             for line in d:
#                 line["text"] = " ".join(line["text"].split())
#                 text = exception_punctuation(line["text"])
#                 text = handle_punctuation(text)
#                 sent = sent + " "  + text
#                 prep_len_line.append(len(text.split()))
#                 prep_ori_box.append(line)
#             if len(sent.split())<=512:
#                 s.append(sent)
#                 len_line += prep_len_line
#                 ori_box += prep_ori_box
#             sent = ""
#         try:
#             for d in json_data["table_cells"]:
#                 sent = exception_punctuation(d["text"])
#                 sent = handle_punctuation(sent)
#                 len_line.append(len(sent.split()))
#                 ori_box.append(d)
#                 s.append(sent)
#                 sent = ""
#         except:
#             sent = ""
#     except:
#         return error_message[4000], 400
#     s1 = [sent.split()[:500] for sent in s]
#     len_sent = list(map(len, s1))
#     s2 = [[check_and_reduce(norm_text(word.lower())) for word in sent] for sent in s1]
#     # cms and rule here
#     s_rule = [' '.join(x) for x in s1]
#     rule_err = []
#     for i in s_rule:
#         # err = check_viethoa(i)
#         # #print("Viet hoa ",i,err)
#         err = []
#         # err2 = mapping_cms(i)
#         # err.extend(err2)
#         # #print("final ", err)
#         rule_err.append(list(set(err)))
		
	
#     batch = math.ceil(len(s)/batch_size)
#     if batch == 0:
#         batch = 1
#     error_index = []
#     with torch.no_grad():
#         for i in range(0,batch,1):
#             check, check_upper, _ = model(s2[(batch_size*i):(batch_size*(i+1))])
#             check = check.cpu().detach()
#             c = torch.round(check)
# #             c_upper = torch.round(check_upper)
# #             #print("Check upper : ",c_upper)
#             if len(c.shape) == 1:
#                 c = c.unsqueeze(0)
#             idx_= find_true(c,  s1[(batch_size*i):(batch_size*(i+1))], s[(batch_size*i):(batch_size*(i+1))], model.vocab)
#             # #print("IDX : ",idx_)
#             error_index += idx_
# #     #print("Err index ",error_index)
# #     #print("find index ", len_line, len_sent, error_index)
	
#     lst_err_idx = []
#     for i, j in zip(error_index, rule_err):
#         #print(i,j)
#         if i == []:
#             tmp = j
#         elif j == []:
#             tmp = i
#         else:
#             tmp = i
#             tmp.extend(j)
#         tmp = list(set(tmp))
#         tmp.sort()
#         lst_err_idx.append(tmp)
# #     #print(lst_err_idx)
#     # #print(len_line, len_sent, lst_err_idx)
#     ans = find_index(len_line, len_sent, lst_err_idx)
#     # #print("dan", ans)
#     # ans = find_index(len_line, len_sent, error_index)
#     for i in range(len(ori_box)):
#         try:
#             if ans[i]:
#                 ori_box[i]["error_index"] = parallel_index(ori_box[i]["text"], ans[i])
#                 rep.append(ori_box[i])
#         except Exception as e:
#             #print("Done ",ans[i],ori_box[i]["text"])
#     torch.cuda.empty_cache()
#     return rep, 200

logging_format = '"","","",{},"","","","","","",0,{},"","","","","","","","","","","","","","","","","VIEW","",0,"",""'


flask_app = Flask(__name__)

flask_app.config['JSON_AS_ASCII'] = False

@flask_app.route('/ready', methods=['GET'])
def check_ready():
	uid = uuid.uuid1()
	with open('started.txt','r') as f:
		data = f.read().split('\n')[0]
	if data == '1':
		logger.info(logging_format.format(uid,200))
		return Response(status_code=200)
	else:
		logger.info(logging_format.format(uid,503))
		return Response(status_code=503)

	
@flask_app.route('/live', methods=['GET'])
def check_live():
	uid = uuid.uuid1()
	logger.info(logging_format.format(uid,200))
	return Response(status_code=200)

@flask_app.route('/process2', methods=["POST"])
def process2():
	uid = uuid.uuid1()
	# file_content = request.files['file'].read()
	# json_data = json.loads(file_content)
	try:
		json_data = request.get_json()
	except Exception as e:
		#print(e)
		mylogger.info(e)
		mylogger.info(traceback.format_exc())
		logger.info(logging_format.format(uid,415))
		return jsonify(error_message[4150]), 415
	try:
		j, status_code = fix_index(json_data)
		mylogger.info(str(j)+" "+str(status_code))
		logger.info(logging_format.format(uid,200))
		return jsonify(j), status_code
	except Exception as e:
		#print(e)
		mylogger.info(e)
		mylogger.info(traceback.format_exc())
		logger.info(logging_format.format(uid,500))
		return jsonify(error_message[5000]), 500

@flask_app.route('/process', methods=["POST"])
async def process():
	uid = uuid.uuid1()
	# file_content = request.files['file'].read()
	# json_data = json.loads(file_content)
	try:
		# json_data = ast.literal_eval(request.data.decode("utf-8"))
		# #print(request.data.decode("utf-8"))
		json_data = ast.literal_eval(request.get_data(as_text=True))
		# #print(json_data)
		# res = check_lang_doc(json_data)
		# #print(res)
		# if res == 1:
		#     return jsonify({}), 200
	except Exception as e:
		#print(e)
		mylogger.info(e)
		mylogger.info(traceback.format_exc())
		logger.info(logging_format.format(uid,415))
		return jsonify(error_message[4150]), 415
	try:
		j, status_code = find_index_line(json_data)
		# #print(j)
		
		# Process new format
		
		for idx, i in enumerate(j):
			j[idx]['result'] = [{'index': x, "type": "GRAMMAR","suggestion":""} for x in i['spell_error_index']]
			j[idx]['result'] += [{'index': x, "type": "STYLE","suggestion":""} for x in i['capital_error_index']]
			del j[idx]['error_index']
			del j[idx]['spell_error_index']
			del j[idx]['capital_error_index']
			
		t = j
		# map: bbox -> textbox truoc co ket thuc cau khong (dua tren json_data GOC, day du)
		_prev_end_by_bbox = {}
		for _k in range(len(json_data)):
			if not isinstance(json_data[_k], dict):
				continue
			_cur_bbox = tuple(json_data[_k].get('bbox', []))
			_prev = json_data[_k-1].get('text','').strip() if _k > 0 and isinstance(json_data[_k-1], dict) else ''
			_prev_end_by_bbox[_cur_bbox] = (_prev == '' or _prev.endswith(('.','?','!',':')))
		for a in t:
			a['_prev_end_ok'] = _prev_end_by_bbox.get(tuple(a.get('bbox', [])), True)
		logger.info(logging_format.format(uid,200))
		# suggestion model
		lst_check_suggestion = []
		for i in t:
			lst_check_suggestion.append(i['text'])
		res = check_sent_new(lst_check_suggestion)['data']
		# #print("RES",res)
		for a, b in zip(t, res):
			s1, s2 = reverse(a['text'])
			for g in a['result']:
				err_idx = g['index']
				tmp = ""
				for h in s1.keys():
					if s1[h] == err_idx:
						# #print(s1,h)
						# #print("Text : ",a['text'])
						# #print("Generate : ",res[b]['generated'])
						# #print(len(res[b]['generated'].split(' ')))
						try:
							tmp += res[b]['generated'].split(' ')[h]
						except:
							continue
				if tmp.lower() != a['text'].split()[err_idx].lower():
					g['suggestion'] = tmp
		for a in t:
			for g in a['result']:
				if g['type'] == 'STYLE':
					word = a['text'].split()[g['index']]
					g['suggestion'] = word[0].upper() + word[1:]
		for a in t:
			a['result'] = list(filter(lambda x : x['suggestion'] != "", a['result']))
		t = list(filter(lambda x : len(x['result']) > 0, t))

		# fix the email
		for idx, i in enumerate(t):
			tmp_txt = i['text'].split(' ')
			t[idx]['result'] = [item for item in i['result'] if not is_valid_email(tmp_txt[item['index']])]

		# fix the url
		for idx, i in enumerate(t):
			tmp_txt = i['text'].split(' ')
			t[idx]['result'] = [item for item in i['result'] if not is_url(tmp_txt[item['index']])]

		# fix the suggestion same
		for idx, i in enumerate(t):
			tmp_txt = i['text'].split(' ')
			t[idx]['result'] = [item for item in i['result'] if item['suggestion'] != tmp_txt[item['index']]]

		for a in t:
			a['result'] = list(filter(lambda x : x['suggestion'] != "", a['result']))
		t = list(filter(lambda x : len(x['result']) > 0, t))

		# === HẬU XỬ LÝ: sửa hoa/thường cho suggestion ===
		for a in t:
			words = a['text'].split()
			# tách vị trí các dấu câu kết thúc để xác định đầu câu
			for g in a['result']:
				idx = g['index']
				if idx >= len(words):
					continue
				original = words[idx]
				sug = g['suggestion']
				if not sug:
					continue
				# 1) Từ gốc viết hoa chữ đầu (tên riêng) -> suggestion cũng phải viết hoa
				is_proper = original[:1].isupper()
				# 2) Từ đứng đầu câu (sau . ? ! hoặc là từ đầu tiên) -> viết hoa
				is_sentence_start = False
				if idx > 0:
					prev = words[idx-1]
					if prev and prev[-1] in ".?!":
						is_sentence_start = True
				if (is_proper or is_sentence_start) and sug[:1].islower():
					g['suggestion'] = sug[0].upper() + sug[1:]

		# [THÊM] Lọc STYLE bị bật nhầm ở textbox cắt vụn (dựa ngữ cảnh textbox trước)
		for a in t:
			if not a.get('_prev_end_ok', True):
				a['result'] = [g for g in a['result'] if not (g['type']=='STYLE' and g['index']==0)]
		for a in t:
			a.pop('_prev_end_ok', None)
		t = list(filter(lambda x: len(x['result']) > 0, t))
		logger.info("Response : "+str(t))
		return jsonify(t), status_code
	except Exception as e:
		#print(e)
		#print(traceback.format_exc())
		mylogger.info(e)
		mylogger.info(traceback.format_exc())
		logger.info(logging_format.format(uid,500))
		return jsonify(error_message[5000]), 500
	
@flask_app.route('/check_sent', methods=["POST"])
def check_sent():
	##print("SENT")
	uid = uuid.uuid1()
	# file_content = request.files['file'].read()
	# json_data = json.loads(file_content)
	try:
		text = request.get_json()["text"]
	except:
		logger.info(logging_format.format(uid,415))
		return jsonify(error_message[4150]), 415
	try:
		logger.info(logging_format.format(uid,200))
		lst_p, lst_idx = sep_paragraph(text,200)
		if len(lst_p) == 0:
			lst_p = [text]
			lst_idx = [0]
		final_text = ""
		lst_error = []
		##print(lst_idx)
		for i,j in zip(lst_p, lst_idx):
			##print(i,j)
			out = predict_sent(i,j)
			final_text += out['text']
			final_text += " "
			lst_error += out['error_index']
		return jsonify({"error_index" : lst_error, "text": final_text}, 200)
#         return jsonify(predict_sent(text)), 200
	except Exception as e:
		mylogger.info(e)
		mylogger.info(traceback.format_exc())
		logger.info(logging_format.format(uid,500))
		return jsonify(error_message[5000]), 500
	
@flask_app.route('/nlp/api/spell_checking', methods=["POST"])
async def spell_checking():
	# #print("Hello")
	# file_content = request.files['file'].read()
	# json_data = json.loads(file_content)
	try:
		json_data = request.get_json()
#         #print(type(json_data))
	except:
		logging.error('Failed to get file', exc_info=True)
		return jsonify(error_message[4150]), 415
	try:
		j, status_code = find_index_line_vtnet(json_data)
		return jsonify(j), status_code
	except:
		logging.error('Failed to get file', exc_info=True)
		return jsonify(error_message[5000]), 500




if __name__ == '__main__':
	flask_app.run(host='0.0.0.0',port ='8080')
