# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time
import random

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "高中阅读", "语法专项", "真题训练"]
WORD_BOOKS = ["中考核心", "高考3500", "四级", "六级", "雅思核心"]
STATUS_OPTIONS = ["正常", "暂停", "结课"]

ANIMAL_EMOJIS = ["🐱", "🐶", "🦊", "🐼", "🐨", "🐯", "🐰", "🦆", "🐸", "🦁"]

# 初始化状态
if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "首页"
# undo_cache：仅保存最近一次新增/删除操作，编辑更新不支持撤销
if 'undo_cache' not in st.session_state:
    st.session_state['undo_cache'] = None

# -------------------------- 2. 飞书多维表格工具函数 --------------------------
def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return resp.json().get("tenant_access_token")

def fetch_records(app_token, table_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    res = requests.get(url, headers=headers)
    return res.json()

def create_record(app_token, table_id, token, fields):
    headers = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    payload = {"fields": fields}
    r = requests.post(url, headers=headers, json=payload)
    return r.json()

def delete_record(app_token, table_id, token, record_id):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
    r = requests.delete(url, headers=headers)
    return r.json()

def update_record(app_token, table_id, token, record_id, fields):
    headers = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
    payload = {"fields": fields}
    r = requests.put(url, headers=headers, json=payload)
    return r.json()

# -------------------------- 撤销逻辑 --------------------------
def do_undo():
    cache = st.session_state.get("undo_cache")
    if not cache:
        return
    token = get_tenant_access_token()
    op = cache["op"]
    table_id = cache["table_id"]
    if op == "add":
        record_id = cache["record_id"]
        delete_record(APP_TOKEN, table_id, token, record_id)
    elif op == "delete":
        ori_fields = cache["ori_fields"]
        create_record(APP_TOKEN, table_id, token, ori_fields)
    st.session_state["undo_cache"] = None
    emoji = random.choice(ANIMAL_EMOJIS)
    st.toast(f"{emoji} 已撤销上一步操作！", icon="✅")
    time.sleep(1)
    st.rerun()

# -------------------------- 3. 页面样式 --------------------------
st.set_page_config(page_title="FishTeacher", layout="wide", page_icon="🐟")

st.markdown("""
<style>
.block-container { max-width: 1400px !important; padding-top:1rem !important; padding-left:2rem; padding-right:2rem;}
@media (max-width:768px){
    .block-container {padding-left:0.5rem !important; padding-right:0.5rem !important;}
}
.brand-title{font-size:36px;font-weight:bold;text-align:center;margin:0.2rem 0;}
.brand-subtitle{font-size:20px;color:#444;text-align:center;margin-bottom:1.5rem;}
</style>
""",unsafe_allow_html=True)

st.markdown('<p class="brand-title">🐟 FishTeacher</p>', unsafe_allow_html=True)
st.markdown('<p class="brand-subtitle">高效学员管理 & 21天抗遗忘系统</p>', unsafe_allow_html=True)

# -------------------------- 导航菜单 --------------------------
def back_home():
    st.session_state.menu_choice = "首页"
    st.rerun()

menu = st.session_state.get("menu_choice","首页")

# -------------------------- 首页 --------------------------
if menu == "首页":
    col1,col2,col3 = st.columns(3)
    with col1:
        if st.button("🔍 复习提醒", use_container_width=True):
            st.session_state.menu_choice = "提醒"
            st.rerun()
    with col2:
        if st.button("📊 账目&流水核算", use_container_width=True):
            st.session_state.menu_choice = "account"
            st.rerun()
    with col3:
        if st.button("👥 学生档案管理", use_container_width=True):
            st.session_state.menu_choice = "名册"
            st.rerun()
    c1,c2 = st.columns(2)
    with c1:
        if st.button("✍️ 快速录入课时", use_container_width=True):
            st.session_state.menu_choice = "录入"
            st.rerun()
    with c2:
        if st.button("📤 导出数据", use_container_width=True):
            st.session_state.menu_choice = "导出"
            st.rerun()

# -------------------------- 复习提醒页面 --------------------------
elif menu == "提醒":
    st.markdown('<div class="back-btn-wrap"></div>',unsafe_allow_html=True)
    if st.button("← 返回首页"):
        back_home()
    r_df = fetch_records(APP_TOKEN,TABLE_ID_RECORDS,get_tenant_access_token())
    st.info("复习提醒模块")

# ========== 账目&流水核算页面 ==========
elif menu == "account":
    if st.button("← 返回首页"):
        back_home()

    # ========== 撤销区域：复选框+按钮确认，防止误触 ==========
    if st.session_state["undo_cache"] is not None:
        st.divider()
        st.info("⚠️ 存在可撤销的上一步操作（仅最近一次新增/删除）")
        undo_confirm = st.checkbox("确认执行撤销", key="undo_confirm_account")
        if undo_confirm and st.button("🔙 撤销上次操作", key="btn_undo_account", type="secondary"):
            do_undo()

    st.divider()
    r_df = fetch_records(APP_TOKEN,TABLE_ID_RECORDS,get_tenant_access_token())
    st.subheader("📊 账目&流水核算")

    target_m = st.selectbox("📅 选择月份",["2026‑01","2026‑02"])

    col_stat,col_flow = st.columns([1,1])
    with col_stat:
        st.markdown("### 📈 统计汇总")
        st.metric("总课时","0")
        st.metric("总薪资","0")
    with col_flow:
        st.markdown("### 📜 流水明细")
        st.dataframe(pd.DataFrame(),use_container_width=True)

# ========== 快速录入课时页面 ==========
elif menu == "录入":
    if st.button("← 返回首页"):
        back_home()

    # ========== 撤销区域 ==========
    if st.session_state["undo_cache"] is not None:
        st.divider()
        st.info("⚠️ 存在可撤销的上一步操作（仅最近一次新增/删除）")
        undo_confirm = st.checkbox("确认执行撤销", key="undo_confirm_input")
        if undo_confirm and st.button("🔙 撤销上次操作", key="btn_undo_input", type="secondary"):
            do_undo()

    st.divider()
    st.subheader("✍️ 快速录入课时记录")
    token = get_tenant_access_token()
    stu_raw = fetch_records(APP_TOKEN,TABLE_ID_STUDENTS,token)
    s_df = pd.DataFrame([x["fields"] for x in stu_raw.get("data",{}).get("items",[])])
    student_list = s_df["学生姓名"].tolist() if "学生姓名" in s_df.columns else []

    with st.form("add_record_form"):
        sel_stu = st.selectbox("学生",student_list)
        lesson_date = st.date_input("上课日期",datetime.date.today())
        content = st.selectbox("学习内容",LEARN_CONTENTS)
        submit_ok = st.form_submit_button("✅ 提交本节课记录")
        if submit_ok:
            # 简单模拟提交，真实业务对接飞书接口
            new_fields = {"学生姓名":sel_stu,"上课日期":str(lesson_date),"学习内容":content}
            resp = create_record(APP_TOKEN,TABLE_ID_RECORDS,token,new_fields)
            if resp.get("code") ==0:
                rid = resp["data"]["record_id"]
                st.session_state["undo_cache"] = {"op":"add","table_id":TABLE_ID_RECORDS,"record_id":rid,"ori_fields":new_fields}
                st.success("课时记录提交成功")
                time.sleep(1)
                st.rerun()

# ========== 学生档案名册页面 ==========
elif menu == "名册":
    if st.button("← 返回首页"):
        back_home()

    # ========== 撤销区域 ==========
    if st.session_state["undo_cache"] is not None:
        st.divider()
        st.info("⚠️ 存在可撤销的上一步操作（仅最近一次新增/删除）")
        undo_confirm = st.checkbox("确认执行撤销", key="undo_confirm_student")
        if undo_confirm and st.button("🔙 撤销上次操作", key="btn_undo_student", type="secondary"):
            do_undo()

    st.divider()
    st.subheader("👥 学生档案管理")
    token = get_tenant_access_token()
    stu_raw = fetch_records(APP_TOKEN,TABLE_ID_STUDENTS,token)
    items = stu_raw.get("data",{}).get("items",[])
    s_df = pd.DataFrame([{"record_id":i["record_id"],**i["fields"]} for i in items])
    st.dataframe(s_df,use_container_width=True)

# ========== 导出页面 ==========
elif menu == "导出":
    if st.button("← 返回首页"):
        back_home()
    st.subheader("📤 导出21天系统数据")
