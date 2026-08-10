# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# -------------------------- 2. 基础业务配置 --------------------------
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句"]
HOURS_OPTIONS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# -------------------------- 3. 飞书 API 核心工具函数 --------------------------

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    try:
        r = requests.post(url, headers=headers, json=payload)
        return r.json().get("tenant_access_token")
    except Exception: return None

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
            fields["record_id"] = item["record_id"] # 保留用于删除
            data.append(fields)
        return pd.DataFrame(data)
    except Exception: return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json={"fields": fields})
        return r.json()
    except Exception as e: return {"code": -1, "msg": str(e)}

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.delete(url, headers=headers)
    return r.json()

def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日学习内容") for d in sorted_ln])
    return f"""【21天抗遗忘复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦[加油][加油][加油]\n\n也请家长把复习视频发到群里🌹"""

# -------------------------- 4. 界面配置 --------------------------

st.set_page_config(page_title="21天抗遗忘云端专业版", layout="centered", page_icon="🎯")

st.markdown("""
    <style>
    .stButton > button { width: 100%; height: 3.5em; font-size: 18px !important; }
    .stSelectbox label, .stDateInput label { font-size: 16px !important; font-weight: bold; }
    code { font-size: 15px !important; line-height: 1.5; }
    </style>
    """, unsafe_allow_html=True)

today = datetime.date.today()

menu = st.selectbox("📌 切换功能模块", 
    ["🔍 复习提醒查询", "📝 录入课时记录", "👤 学生名单管理", "📊 历史数据总表", "📄 导出21天表", "📥 批量导入旧CSV"])

# -------------------------- 5. 功能模块 --------------------------

# --- 模块 1：复习提醒查询 ---
if menu == "🔍 复习提醒查询":
    st.subheader("🔍 复习提醒查询")
    with st.spinner('正在同步云端记录...'):
        r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    
    if not r_df.empty and "学习日期" in r_df.columns:
        r_df['学习日期_dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        mask = r_df['学习日期_dt'].isna()
        if mask.any(): r_df.loc[mask, '学习日期_dt'] = pd.to_datetime(r_df.loc[mask, '学习日期']).dt.date
            
        col1, col2 = st.columns(2)
        with col1: q_date = st.date_input("查询日期", today)
        with col2:
            all_names = ["全部学生"] + sorted(r_df['姓名'].unique().tolist())
            target_student = st.selectbox("筛选指定学生", all_names)

        reminders = {}
        for _, row in r_df.iterrows():
            diff = (q_date - row['学习日期_dt']).days + 1
            if diff in REVIEW_DAYS:
                name = row['姓名']
                if target_student != "全部学生" and name != target_student: continue
                if name not in reminders: reminders[name] = []
                reminders[name].append(row['学习日期_dt'].strftime("%Y-%m-%d"))
        
        if reminders:
            st.error(f"🚨 今日共有 {len(reminders)} 位学员有任务")
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **学生：{name}**")
                    st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else: st.info("💡 该日期暂无复习任务")
    else: st.info("💡 云端尚无课时记录，请先录入或导入。")

# --- 模块 2：录入课时记录 ---
elif menu == "📝 录入课时记录":
    st.subheader("📝 课时录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    active_students = []
    if not s_df.empty and "状态" in s_df.columns:
        active_students = s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist()
    
    if not active_students:
        st.warning("⚠️ 库中无在读学员，请先去'学生名单管理'录入。")
    else:
        with st.form("input_form"):
            name = st.selectbox("👤 选择学生", active_students)
            date = st.date_input("📅 学习日期", today)
            content = st.selectbox("📚 学习内容", LEARN_CONTENTS)
            hour = st.select_slider("⏰ 课时数", options=HOURS_OPTIONS, value=1.0)
            
            if st.form_submit_button("💾 保存并同步到云端"):
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                fields = {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour}
                res = add_feishu_record(TABLE_ID_RECORDS, fields)
                if res.get("code") == 0:
                    st.success("✅ 已存入飞书云端！")
                    st.balloons()
                else: st.error(f"存入失败: {res.get('msg')}")

# --- 模块 3：学生名单管理 ---
elif menu == "👤 学生名单管理":
    st.subheader("👥 学生名单管理")
    with st.expander("➕ 添加新学员"):
        with st.form("add_student"):
            n_name = st.text_input("学生姓名")
            n_status = st.selectbox("当前状态", STATUS_OPTIONS)
            if st.form_submit_button("提交入库"):
                if n_name:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n_name, "状态": n_status})
                    st.success(f"✅ {n_name} 已成功入库")
                    st.reru
