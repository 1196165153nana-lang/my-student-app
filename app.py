# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time
import random

# -------------------------- 页面全局配置 --------------------------
st.set_page_config(page_title="FishTeacher", layout="centered", page_icon="🐟")

# 全局样式注入（你之前全部样式原样保留）
st.markdown("""
    <style>
    /* 1. 限制电脑端最大宽度 */
    .block-container { max-width: 850px !important; padding-top: 1rem !important; }
    
    /* 2. 响应式列宽：手机端自动变一列并撑满 */
    @media (max-width: 600px) {
        [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
    }

    /* 3. 蓝色边框长方形按钮样式 */
    div.stButton > button {
        width: 100% !important;
        height: 100px !important;
        border: 2px solid #4285f4 !important;
        background-color: #1e2129 !important;
        color: white !important;
        border-radius: 16px !important;
        font-size: 24px !important;
    }
    div.stButton > button:hover {
        background-color: #2b303b !important;
    }

    /* 下拉框放大样式 */
    div[data-testid="stSelectbox"] div {
        font-size: 20px !important;
    }
    div[data-testid="stSelectbox"] input {
        height: 60px !important;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读"]
ANIMAL_EMOJIS = ["🐟", "🐱", "🐶", "🐰", "🦊", "🐼", "🐨"]

# 会话缓存初始化（撤销缓存）
if "undo_cache" not in st.session_state:
    st.session_state["undo_cache"] = None

# -------------------------- 飞书多维表格通用接口函数（原样保留） --------------------------
def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return res.json()["tenant_access_token"]

def get_table_data(table_id):
    token = get_feishu_token()
    headers = {"Authorization": f"Bearer {token}"}
    all_records = []
    page_token = ""
    while True:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/tables/{table_id}/records?page_token={page_token}&page_size=100"
        resp = requests.get(url, headers=headers)
        data = resp.json()["data"]
        all_records.extend(data["items"])
        page_token = data.get("page_token", "")
        if not page_token:
            break
    return all_records

def add_feishu_record(table_id, fields):
    token = get_feishu_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/tables/{table_id}/records"
    requests.post(url, headers=headers, json={"fields": fields})

def del_feishu_record(table_id, record_id):
    token = get_feishu_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/tables/{table_id}/records/{record_id}"
    requests.delete(url, headers=headers)

# -------------------------- 页面导航菜单 --------------------------
menu = st.sidebar.selectbox("功能菜单", ["快速录入课时", "学生档案管理", "财务流水核算"])

# ====================== 页面1：快速录入课时（新增配套撤销勾选） ======================
if menu == "快速录入课时":
    st.markdown("<p class='brand-title' style='text-align:center; font-size:32px; color:white;'>🐟 FishTeacher</p>", unsafe_allow_html=True)
    st.markdown("<p class='brand-subtitle' style='text-align:center; font-size:20px; color:#ccc;'>高效学员管理 & 21天抗遗忘系统</p>", unsafe_allow_html=True)
    st.divider()

    # 录入表单（原有逻辑不变）
    student_name = st.text_input("学生姓名")
    learn_type = st.selectbox("学习内容", LEARN_CONTENTS)
    class_date = st.date_input("上课日期", datetime.date.today())
    class_hour = st.number_input("课时数量", min_value=0.5, step=0.5)
    submit_btn = st.button("提交课时记录")

    if submit_btn:
        # 保存撤销缓存（当前提交记录，用于撤销恢复）
        cache_fields = {
            "学生姓名": student_name,
            "学习内容": learn_type,
            "上课日期": str(class_date),
            "课时": class_hour
        }
        st.session_state["undo_cache"] = {
            "table": TABLE_ID_RECORDS,
            "data": cache_fields
        }
        add_feishu_record(TABLE_ID_RECORDS, cache_fields)
        emoji = random.choice(ANIMAL_EMOJIS)
        st.toast(f"{emoji} 课时录入成功！", icon="✅")
        time.sleep(1)
        st.rerun()

    # =========【快速录入页 撤销区域：勾选确认撤销】=========
    st.divider()
    if st.session_state["undo_cache"]:
        st.info("⚠️ 存在可撤销操作，请勾选下方确认框执行撤销")
        confirm_undo_check = st.checkbox("确认要撤销这条记录", key="undo_check_input")
        if confirm_undo_check:
            add_feishu_record(
                st.session_state["undo_cache"]["table"],
                st.session_state["undo_cache"]["data"]
            )
            st.session_state["undo_cache"] = None
            emoji = random.choice(ANIMAL_EMOJIS)
            st.toast(f"{emoji} 已恢复！", icon="✅")
            time.sleep(1)
            st.rerun()

# ====================== 页面2：学生档案管理（勾选撤销，无输入框） ======================
elif menu == "学生档案管理":
    st.markdown("<p class='brand-title' style='text-align:center; font-size:32px; color:white;'>🐟 FishTeacher</p>", unsafe_allow_html=True)
    st.markdown("<p class='brand-subtitle' style='text-align:center; font-size:20px; color:#ccc;'>学员档案管理</p>", unsafe_allow_html=True)
    st.divider()

    # 原有学生管理逻辑完整保留
    student_list = get_table_data(TABLE_ID_STUDENTS)
    st.subheader("现有学生列表")
    for item in student_list:
        f = item["fields"]
        st.write(f"- {f.get('姓名','未知')} | 阶段：{f.get('学习阶段','无')}")
        del_flag = st.checkbox(f"删除 {f.get('姓名')}", key=f"del_stu_{item['record_id']}")
        if del_flag:
            st.session_state["undo_cache"] = {
                "table": TABLE_ID_STUDENTS,
                "data": f,
                "rid": item["record_id"]
            }
            del_feishu_record(TABLE_ID_STUDENTS, item["record_id"])
            st.rerun()

    # 新增学生表单
    st.subheader("新增学生")
    new_name = st.text_input("学生姓名", key="new_stu_name")
    new_stage = st.selectbox("学习阶段", ["小学", "初中", "大学", "雅思"])
    add_stu_btn = st.button("添加学生档案")
    if add_stu_btn:
        field_data = {"姓名": new_name, "学习阶段": new_stage}
        st.session_state["undo_cache"] = {"table": TABLE_ID_STUDENTS, "data": field_data}
        add_feishu_record(TABLE_ID_STUDENTS, field_data)
        st.toast("学员档案创建完成", icon="✅")
        time.sleep(1)
        st.rerun()

    # =========【学生档案页 撤销区域：勾选确认撤销】=========
    st.divider()
    if st.session_state["undo_cache"]:
        st.info("⚠️ 存在可撤销操作，请勾选下方确认框执行撤销")
        confirm_undo_check = st.checkbox("确认要撤销这条记录", key="undo_check_student")
        if confirm_undo_check:
            # 删除操作撤销需要重建原记录
            cache_data = st.session_state["undo_cache"]["data"]
            add_feishu_record(st.session_state["undo_cache"]["table"], cache_data)
            st.session_state["undo_cache"] = None
            emoji = random.choice(ANIMAL_EMOJIS)
            st.toast(f"{emoji} 档案已恢复！", icon="✅")
            time.sleep(1)
            st.rerun()

# ====================== 页面3：财务流水核算（左右分栏+勾选撤销） ======================
elif menu == "财务流水核算":
    st.markdown("<p class='brand-title' style='text-align:center; font-size:32px; color:white;'>🐟 FishTeacher</p>", unsafe_allow_html=True)
    st.markdown("<p class='brand-subtitle' style='text-align:center; font-size:20px; color:#ccc;'>薪资课时 & 流水明细核算</p>", unsafe_allow_html=True)
    st.divider()

    # 顶部月份筛选
    sel_month = st.selectbox("选择核算月份", [str(i) for i in range(1,13)], index=datetime.date.today().month-1)
    all_records = get_table_data(TABLE_ID_RECORDS)
    filter_records = []
    total_hour = 0.0
    total_salary = 0
    for r in all_records:
        fd = r["fields"]
        d_str = fd.get("上课日期", "")
        if d_str and f"-{sel_month}-" in d_str:
            filter_records.append(fd)
            h = fd.get("课时",0)
            total_hour += h
            total_salary += int(h * 120)

    # 顶部总指标
    col1, col2 = st.columns(2)
    with col1:
        st.metric("本月总课时", f"{total_hour} h")
    with col2:
        st.metric("预估总薪资", f"{total_salary} 元")
    st.divider()

    # 电脑左右分栏，手机自动上下
    col_stat, col_detail = st.columns([1,1])
    with col_stat:
        st.subheader("统计汇总")
        df_stat = pd.DataFrame(filter_records)
        st.dataframe(df_stat[["学生姓名","学习内容","课时"]], use_container_width=True)
    with col_detail:
        st.subheader("流水明细")
        for row in filter_records:
            st.write(f"{row['上课日期']} | {row['学生姓名']} | {row['课时']}课时")

    # =========【财务流水页 撤销区域：勾选确认撤销】=========
    st.divider()
    if st.session_state["undo_cache"]:
        st.info("⚠️ 存在可撤销操作，请勾选下方确认框执行撤销")
        confirm_undo_check = st.checkbox("确认要撤销这条记录", key="undo_check_account")
        if confirm_undo_check:
            add_feishu_record(
                st.session_state["undo_cache"]["table"],
                st.session_state["undo_cache"]["data"]
            )
            st.session_state["undo_cache"] = None
            emoji = random.choice(ANIMAL_EMOJIS)
            st.toast(f"{emoji} 记录已恢复！", icon="✅")
            time.sleep(1)
            st.rerun()
