# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import json
import time

# -------------------------- 1. 核心安全配置 --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句"]
HOURS_OPTIONS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# -------------------------- 2. 飞书 API 核心工具 --------------------------

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    try:
        r = requests.post(url, json=payload)
        return r.json().get("tenant_access_token")
    except: return None

def fetch_feishu_data(table_id):
    """从飞书读取数据，保留 record_id 以供删除"""
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
            fields["record_id"] = item["record_id"]  # 关键：获取云端唯一ID
            data.append(fields)
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json={"fields": fields})
    return r.json()

def delete_feishu_record(table_id, record_id):
    """从飞书云端物理删除一条记录"""
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.delete(url, headers=headers)
    return r.json()

def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日学习内容") for d in sorted_ln])
    return f"【21天抗遗忘复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦[加油][加油][加油]\n\n也请家长把复习视频发到群里🌹"

# -------------------------- 3. 界面自适应配置 --------------------------
st.set_page_config(page_title="学生管理云端专业版", layout="centered", page_icon="🎯")

st.markdown("""
    <style>
    .stButton > button { width: 100%; height: 3em; }
    .delete-btn > button { background-color: #ff4b4b !important; color: white; }
    </style>
    """, unsafe_allow_html=True)

today = datetime.date.today()

menu = st.selectbox("📌 切换功能模块", ["🔍 复习提醒查询", "📝 录入课时记录", "👤 学生名单管理", "📊 历史数据总表", "📄 导出21天表", "📥 批量导入旧数据"])

# --- 模块 1：复习提醒查询 ---
if menu == "🔍 复习提醒查询":
    st.subheader("🔍 复习提醒查询")
    with st.spinner('同步云端数据中...'):
        r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    
    if not r_df.empty:
        r_df['学习日期_dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        mask = r_df['学习日期_dt'].isna()
        if mask.any(): r_df.loc[mask, '学习日期_dt'] = pd.to_datetime(r_df.loc[mask, '学习日期']).dt.date
            
        col1, col2 = st.columns(2)
        with col1: q_date = st.date_input("选择查询日期", today)
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
            st.error(f"🚨 今日共有 {len(reminders)} 位学员有复习任务")
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **学生：{name}**")
                    st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else:
            st.info("💡 该日期暂无复习任务")
    else: st.info("💡 云端尚无课时记录。")

# --- 模块 2：录入课时记录 ---
elif menu == "📝 录入课时记录":
    st.subheader("📝 课时录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty and "状态" in s_df.columns:
        active_students = s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist()
        if active_students:
            with st.form("input_form"):
                name = st.selectbox("👤 选择学生", active_students)
                date = st.date_input("📅 学习日期", today)
                content = st.selectbox("📚 学习内容", LEARN_CONTENTS)
                hour = st.select_slider("⏰ 课时数", options=HOURS_OPTIONS, value=1.0)
                if st.form_submit_button("💾 保存并同步到云端"):
                    ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour})
                    st.success(f"✅ 已存入飞书！学员：{name}")
                    st.balloons()
        else: st.warning("请先在名单管理中添加'在读'学生")

# --- 模块 3：学生名单管理 (增加删除学生功能) ---
elif menu == "👤 学生名单管理":
    st.subheader("👥 学员信息库管理")
    with st.expander("➕ 添加新学员"):
        with st.form("add_student"):
            n_name = st.text_input("学生姓名")
            n_status = st.selectbox("状态", STATUS_OPTIONS)
            if st.form_submit_button("确认入库"):
                if n_name:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n_name, "状态": n_status})
                    st.success(f"✅ {n_name} 已入库")
                    st.rerun()

    st.write("---")
    st.write("📋 **当前名册（删除学生请点下方按钮）**")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        st.dataframe(s_df[["姓名", "状态"]], use_container_width=True)
        
        # 删除学生逻辑
        st.write("🗑️ **危险操作：删除学员**")
        del_name = st.selectbox("选择要从名册删除的学生", ["请选择"] + s_df['姓名'].tolist())
        if del_name != "请选择":
            if st.button("❌ 彻底从云端删除该学生"):
                target_id = s_df[s_df['姓名'] == del_name]['record_id'].values[0]
                res = delete_feishu_record(TABLE_ID_STUDENTS, target_id)
                st.success(f"已删除学生：{del_name}")
                st.rerun()
    else: st.info("库中无学生。")

# --- 模块 4：历史数据总表 (增加删除课时记录功能) ---
elif menu == "📊 历史数据总表":
    st.subheader("📊 历史明细 (云端同步)")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        # 格式化日期显示
        all_r['显示日期'] = pd.to_datetime(all_r['学习日期'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
        display_df = all_r[["姓名", "显示日期", "学习内容", "课时", "record_id"]]
        st.dataframe(display_df.drop(columns=["record_id"]), use_container_width=True)
        
        st.write("🗑️ **删除课时记录**")
        target_del_id = st.selectbox("选择要删除的记录 ID", ["请选择"] + display_df['record_id'].tolist())
        if target_del_id != "请选择":
            info = display_df[display_df['record_id'] == target_del_id].iloc[0]
            st.warning(f"确认删除：{info['姓名']} 在 {info['显示日期']} 的记录吗？")
            if st.button("🔥 确认删除"):
                delete_feishu_record(TABLE_ID_RECORDS, target_del_id)
                st.success("记录已删除")
                st.rerun()
    else: st.info("尚无记录")

# --- 模块 6：批量导入旧数据 (智能识别 + 自动补全名单) ---
elif menu == "📥 批量导入旧数据":
    st.subheader("📥 批量搬运旧数据到云端")
    st.info("智能模式：导入课时时，如果学生不在名单中，会自动帮您创建名单。")
    file = st.file_uploader("点击上传 CSV 文件", type="csv")
    
    if file:
        df = pd.read_csv(file)
        st.write("📄 数据预览：", df.head())
        
        is_pivot = any('.' in str(col) for col in df.columns) # 识别横向报表
        
        if st.button("🚀 确认开始同步"):
            bar = st.progress(0)
            count = 0
            
            # 获取现有学生名单，避免重复创建
            existing_s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
            existing_names = existing_s_df['姓名'].tolist() if not existing_s_df.empty else []

            def sync_student_and_record(name, date_ts, val):
                nonlocal count
                # 1. 检查并补全学生名单
                if name not in existing_names:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"})
                    existing_names.append(name) # 内存中更新，防止同批次重复写
                # 2. 写入课时记录
                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": date_ts, "学习内容": "历史导入", "课时": float(val)})
                count += 1

            if not is_pivot:
                # 格式 1：清单表
                for i, row in df.iterrows():
                    try:
                        ld = pd.to_datetime(row['学习日期']).date()
                        ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                        sync_student_and_record(str(row['姓名']), ts, row.get('课时', 1))
                        bar.progress((i + 1) / len(df))
                    except: pass
            else:
                # 格式 2：横向报表 (08.01...)
                date_cols = [c for c in df.columns if '.' in str(c)]
                total_steps = len(df) * len(date_cols)
                step = 0
                for _, row in df.iterrows():
                    name = str(row['姓名'])
                    for d_col in date_cols:
                        step += 1
                        val = row[d_col]
                        if pd.notna(val) and float(val) > 0:
                            try:
                                date_str = f"2026-{d_col.replace('.', '-')}"
                                ld = pd.to_datetime(date_str).date()
                                ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                                sync_student_and_record(name, ts, val)
                            except: pass
                        bar.progress(step / total_steps)
            
            st.success(f"🎊 搬家完成！同步了 {count} 条记录，并补全了学生名单。")
