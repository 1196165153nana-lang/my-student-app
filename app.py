# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import json
import time

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]

# 所有的课程内容
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句"]

# 定义哪些内容需要复习提醒（仅限单词类）
WORD_RELATED_CONTENTS = ["单词", "大学单词", "雅思单词"]

# 【关键改进】课时选项：0.5 到 10 小时，步长 0.5
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)] 
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# --- 课时费定价逻辑 ---
def get_unit_price(content):
    if content in ["初中阅读", "初中语法"]:
        return 45
    elif content in ["高中阅读", "高中完型", "长难句", "雅思单词", "大学单词", "雅思", "托福", "四六级"]:
        return 50
    elif content in ["单词", "小学阅读", "旧数据补录", "导入"]:
        return 40
    return 40

if 'last_deleted' not in st.session_state:
    st.session_state['last_deleted'] = None

# -------------------------- 2. 飞书 API 核心工具 --------------------------

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    try:
        r = requests.post(url, json=payload)
        return r.json().get("tenant_access_token")
    except: return None

def fetch_feishu_data(table_id):
    token = get_tenant_access_token()
    if not token: return pd.DataFrame()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=500"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        items = r.json().get("data", {}).get("items", [])
        if not items: return pd.DataFrame()
        data = []
        for item in items:
            fields = item["fields"]
            fields["record_id"] = item["record_id"]
            data.append(fields)
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    clean_fields = {k: v for k, v in fields.items() if k not in ["record_id", "显示日期", "标签", "小计", "单价", "分类", "dt", "月份", "学习日期_dt"]}
    r = requests.post(url, headers=headers, json={"fields": clean_fields})
    return r.json()

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization":
