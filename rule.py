import os
import json
from tqdm.notebook import tqdm
import unicodedata
import re
import string
import pandas as pd

lst_punctuation_viethoa = [".","?","!"]

with open("data/boy.txt","r", encoding="utf-8") as f:
    boy = unicodedata.normalize("NFC",f.read()).split("\n")

with open("data/girl.txt","r", encoding="utf-8") as f:
    girl = unicodedata.normalize("NFC",f.read()).split("\n")

with open("data/data.json","r", encoding="utf-8") as f:
    hoten = json.load(f)
    
ho = list(set([unicodedata.normalize("NFC",x['last_name_group']) for x in hoten]))
ho_lower = list(set([unicodedata.normalize("NFC",x['last_name_group'].lower()) for x in hoten]))

name = boy + girl
for i in tqdm(hoten):
    name.append(' '.join(x for x in i['full_name'].split(" ")[-2:]))
name.remove("")
#name.remove("Tự Do")
try:
    name.remove("")
except:
    pass

# try:
#     name.remove("Tự Do")
# except:
#     pass

with open("final_name.txt","r", encoding="utf-8") as f:
    name = unicodedata.normalize("NFC",f.read()).split("\n")

try:
    name.remove("")
except:
    pass


import json

with open("./data/sorted.json","r", encoding="utf-8") as f:
    provinces = json.load(f)
    
# remove tinh thanh gay nham lan
# miss_prov = pd.read_excel("./data/provinces_filter.xlsx")
with open("./data/provinces_filter.txt", encoding="utf-8") as f:
    miss_prov = f.read().split('\n')
    miss_prov = [x for x in miss_prov if len(x) >= 3]

    
lst_provinces = []
for i in range(len(provinces)):
    # lop1
    tmp = provinces[i][2].lower() + " " + provinces[i][1]
    lst_provinces.append(provinces[i][1])
    lst_provinces.append(tmp)
    # lop2
    for j in provinces[i][4]:
        tmp = j[2].lower() + " " + j[1]
        lst_provinces.append(j[1])
        lst_provinces.append(tmp)
        # lop3
        for g in j[4]:
            tmp = g[2].lower() + " " + g[1]
            lst_provinces.append(g[1])
            lst_provinces.append(tmp)
            
lst_provinces = list(set(lst_provinces))
lst_provinces = [x for x in lst_provinces if len(x.split()) > 1]

# filter
lst_provinces = [x for x in lst_provinces if x not in miss_prov]

with open("provinces.txt", encoding="utf-8") as f:
    miss_prov = f.read().split('\n')
    lst_provinces = [x for x in miss_prov if len(x) >= 3]


import copy

def split_punctuation(text):
    mapping = []
    # Split the text into words and punctuation
    for idx, i in enumerate(text.split(" ")):
        tokens = re.findall(r'\w+|[^\w\s]', i)
        mapping.extend([idx]*len(tokens))

    tokens = re.findall(r'\w+|[^\w\s]', text)
    new_text = ' '.join(x for x in tokens)
    new_text = new_text.strip()

    return new_text, mapping

def check_name(input_sen):
    input_sen = unicodedata.normalize("NFC", input_sen)
    tmp = input_sen.lower()
    pos = input_sen.split(" ")
    pos_idx = [0]
    for i in range(1, len(pos)):
        pos_idx.append(pos_idx[i-1]+len(pos[i-1])+1)
    lst_errors = []
    for i in name:
        if len(i) < 2:
            continue
        # print(i)
        g = input_sen
        lst_err = []
        res = [m.start() for m in re.finditer(i.lower(), g.lower())]
        if len(res) > 0:
            for s in res:
                ho_s = g[:s-1].split(" ")[-1]
                if ho_s.lower() in ho_lower:
                    # print(ho_s)
                    if ho_s in ho_lower:
                        lst_err.append(pos_idx.index(s)-1)
                    cur_s = g[s:s+len(i)]
                    idx_p = 0
                    for a,b in zip(cur_s.split(' '), i.split(" ")):
                        if a != b:
                            try:
                                lst_err.append(pos_idx.index(s + idx_p))
                            except:
                                break
                        idx_p += len(a) + 1
    
        lst_errors += lst_err
    lst_errors = list(set(lst_errors))
    lst_errors.sort()
    # print("Name : ",lst_errors)
    return lst_errors

def check_provinces(input_sen):
    input_sen = unicodedata.normalize("NFC", input_sen)
    tmp = input_sen.lower()
    pos = input_sen.split(" ")
    pos_idx = [0]
    for i in range(1, len(pos)):
        pos_idx.append(pos_idx[i-1]+len(pos[i-1])+1)
    lst_errors = []
    for i in lst_provinces:
        if len(i) < 3:
            continue
        # print(i)
        g = input_sen
        lst_err = []
        res = [m.start() for m in re.finditer(i.lower(), g.lower())]
        if len(res) > 0:
            for s in res:
                cur_s = g[s:s+len(i)]
                idx_p = 0
                for a,b in zip(cur_s.split(' '), i.split(" ")):
                    if a != b:
                        try:
                            lst_err.append(pos_idx.index(s + idx_p))
                        except:
                            break
                    idx_p += len(a) + 1
    
        lst_errors += lst_err
    lst_errors = list(set(lst_errors))
    lst_errors.sort()
    # print("Provinces : ",lst_errors)
    return lst_errors

def check_viethoa(sen):
    new_text , mapping = split_punctuation(sen)
    # check dau cau
    flag = 0
    lst_err = []
    # check từ đầu textbox: OCR đảm bảo mỗi textbox là 1 câu hoàn chỉnh
    # nên từ đầu tiên phải viết hoa
    words = new_text.split()
    if words and words[0] not in string.punctuation:
        if words[0][0] != words[0][0].upper():
            lst_err.append(mapping[0])
    # print(new_text.split(),mapping)
    for idx, i in enumerate(new_text.split()):
        if flag == 1:
            if i not in string.punctuation:
                if i[0] != i[0].upper():
                    lst_err.append(mapping[idx])
            flag = 0
        else:
            if i in lst_punctuation_viethoa:
                flag = 1
            else:
                flag = 0
    # print("Dấu câu : ", lst_err)
    # check error provinces and name
    err = check_provinces(new_text)
    # print("Province", err)
    for i in err:
        lst_err.append(mapping[i])
    err = check_name(new_text)
    # print("Name", err)
    for i in err:
        lst_err.append(mapping[i])
    lst_err = list(set(lst_err))
    lst_err.sort()
    return lst_err

def mapping_position_bytes_to_str(x):
    lst_bytes = str.encode(x)
    pos = 1
    c_pos = 0
    x_pos = 0
    mapping_byte = []
    while True:
        try:
            lst_bytes[c_pos:pos].decode()
            mapping_byte.append(x_pos)
            c_pos = pos
            pos += 1
            x_pos += 1
        except:
            mapping_byte.append(x_pos)
            pos += 1
        if x_pos >= len(x):
            break
    return mapping_byte

import requests
import json

proxies = {
   'http': '',
   'https': '',
}

def matching_spaces(x):
    url = "http://192.168.101.144:9696/v6/matchingspaces"

    payload = json.dumps({
      "inputText": x
    })
    headers = {
      'accept': 'application/json',
      'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload, proxies=proxies)

    out = json.loads(response.text)
    return out['data']

def matching_predefined(x):
    url = "http://192.168.101.144:9696/v6/matchingpredefined"

    payload = json.dumps({
      "contexts": [
        "predefined"
      ],
      "inputText": x
    })
    headers = {
      'accept': 'application/json',
      'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload, proxies=proxies)

    out = json.loads(response.text)
    return out['data']


def mapping_cms(x):
    mp_byte = mapping_position_bytes_to_str(x)
    mapping = x.split(' ')
    mp = [0]
    for i in mapping:
        mp.append(mp[-1]+len(i)+1)
#     mp = mp[:-1]
    # print(mp)
    res = matching_predefined(x)
    pos = []
    for x in res:
        if type(x) == list:
            for i in range(len(mp)-1):
                if mp_byte[x[0]] >= mp[i] and mp_byte[x[0]] < mp[i+1]:
                    pos.append(i)
                    break
    return pos

#print(check_viethoa("nguyễn Anh đức là cầu thủ hay hơn Hà PHƯƠNG THảO? không thể bàn cãi. nhể"))