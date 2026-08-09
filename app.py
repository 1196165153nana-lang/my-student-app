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
    token = get_tenant_access_token()
    if not token: return pd.DataFrame()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=500"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        items = r.json().get("data", {}).get("items", [])
        return pd.DataFrame([item["fields"] for item in items]) if items else pd.DataFrame()
    except: return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json={"fields": fields})
    return r.json()

def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日学习内容") for d in sorted_ln])
    return f"【21天抗遗忘复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦[加油][加油][加油]\n\n也请家长把复习视频发到群里🌹"

# -------------------------- 3. 界面自适应配置 --------------------------
st.set_page_config(page_title="学生管理云端专业版", layout="centered", page_icon="🎯")

st.markdown("<style>.stButton>button {width: 100%; height: 3.5em; font-size: 18px !important;}</style>", unsafe_allow_html=True)

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

# --- 模块 3：学生名单管理 ---
elif menu == "👤 学生名单管理":
    st.subheader("👥 学员库管理")
    with st.expander("➕ 添加新学员"):
        with st.form("add_student"):
            n_name = st.text_input("学生姓名")
            n_status = st.selectbox("状态", STATUS_OPTIONS)
            if st.form_submit_button("确认入库"):
                if n_name:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n_name, "状态": n_status})
                    st.success(f"✅ {n_name} 已入库")
                    st.rerun()
    s_view = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_view.empty: st.dataframe(s_view[["姓名", "状态"]], use_container_width=True)

# --- 模块 4：历史数据总表 ---
elif menu == "📊 历史数据总表":
    st.subheader("📊 历史明细 (云端同步)")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['学习日期'] = pd.to_datetime(all_r['学习日期'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r, use_container_width=True)

# --- 模块 5：导出21天表 ---
elif menu == "📄 导出21天表":
    st.subheader("📄 单人21天记录表导出")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt'] = pd.to_datetime(r_all['学习日期'], unit='ms', errors='coerce').dt.date
        target = st.selectbox("选择学生", r_all['姓名'].unique())
        if st.button("生成表格"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt")
            output = [["21天抗遗忘周期记录表", "", "", "", "", "", "", "", "", "", "", "", ""], [f"学生姓名：{target}", "", "", "", "", "", "", "", "", "", "", "", ""], ["日期", "复习", "新学", "第1天", "第2天", "第3天", "第5天", "第7天", "第9天", "第12天", "第14天", "第17天", "第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt']
                if pd.isna(ld): continue
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"), "", ""] + rvs)
                output.append([""]*13)
            buf = io.StringIO()
            pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载表格", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

# --- 模块 6：批量导入旧数据 (智能识别版) ---
elif menu == "📥 批量导入旧数据":
    st.subheader("📥 批量搬运旧数据到云端")
    st.info("支持两种格式：\n1. 原始清单表 (含姓名, 学习日期, 课时...)\n2. 统计报表 (含姓名, 08.01, 08.02...)")
    file = st.file_uploader("点击上传 CSV 文件", type="csv")
    
    if file:
        df = pd.read_csv(file)
        st.write("📄 数据预览：", df.head())
        
        # 智能识别逻辑
        is_pivot = any('.' in str(col) for col in df.columns) # 检查是否有 08.01 这种带点的列
        
        if st.button("🚀 确认开始同步到飞书"):
            bar = st.progress(0)
            count = 0
            
            if not is_pivot:
                # 格式 1：标准纵向表
                for i, row in df.iterrows():
                    try:
                        ld = pd.to_datetime(row['学习日期']).date()
                        ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                        add_feishu_record(TABLE_ID_RECORDS, {"姓名": str(row['姓名']), "学习日期": ts, "学习内容": str(row.get('学习内容','补录')), "课时": float(row.get('课时',1))})
                        count += 1
                        bar.progress((i + 1) / len(df))
                    except: pass
            else:
                # 格式 2：横向报表 (08.01, 08.02...)
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
                                # 报表里的日期是 08.01，补齐为 2026-08-01
                                date_str = f"2026-{d_col.replace('.', '-')}"
                                ld = pd.to_datetime(date_str).date()
                                ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "旧数据补录", "课时": float(val)})
                                count += 1
                            except: pass
                        bar.progress(step / total_steps)
            
            st.success(f"🎊 同步完成！共向飞书存入 {count} 条有效记录。")
