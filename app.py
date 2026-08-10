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
            fields["record_id"] = item["record_id"]  # 获取云端唯一ID用于删除
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
    """从飞书云端物理删除记录"""
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

st.markdown("<style>.stButton>button {width: 100%; height: 3.5em; font-size: 16px !important;}</style>", unsafe_allow_html=True)

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
            st.error(f"🚨 今日共有 {len(reminders)} 位学员有任务")
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
    st.subheader("👥 学员名册管理")
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
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        st.write("📋 当前云端名单：")
        st.dataframe(s_df[["姓名", "状态"]], use_container_width=True)
        
        st.write("🗑️ **删除学员**")
        del_target = st.selectbox("选择要删除的学生", ["请选择"] + s_df['姓名'].tolist())
        if del_target != "请选择":
            if st.button("❌ 彻底从云端名册删除"):
                rid = s_df[s_df['姓名'] == del_target]['record_id'].values[0]
                delete_feishu_record(TABLE_ID_STUDENTS, rid)
                st.success(f"已删除：{del_target}")
                st.rerun()

# --- 模块 4：历史数据总表 ---
elif menu == "📊 历史数据总表":
    st.subheader("📊 历史明细")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['显示日期'] = pd.to_datetime(all_r['学习日期'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r[["姓名", "显示日期", "学习内容", "课时"]], use_container_width=True)
        
        st.write("🗑️ **删除单条错误记录**")
        all_r['删除标签'] = all_r['姓名'] + " | " + all_r['显示日期'] + " | " + all_r['record_id']
        target_label = st.selectbox("选择要删除的记录", ["请选择"] + all_r['删除标签'].tolist())
        if target_label != "请选择":
            target_rid = target_label.split(" | ")[-1]
            if st.button("🔥 确认删除该条课时"):
                delete_feishu_record(TABLE_ID_RECORDS, target_rid)
                st.success("删除成功")
                st.rerun()

# --- 模块 5：导出21天表 ---
elif menu == "📄 导出21天表":
    st.subheader("📄 单人表导出")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt'] = pd.to_datetime(r_all['学习日期'], unit='ms', errors='coerce').dt.date
        target = st.selectbox("选择学生", r_all['姓名'].unique())
        if st.button("生成表格"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt")
            output = [["21天抗遗忘表", "", ""], [f"学生姓名：{target}", "", ""], ["日期", "复习", "新学", "第1天", "第2天", "第3天", "第5天", "第7天", "第9天", "第12天", "第14天", "第17天", "第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt']
                if pd.isna(ld): continue
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"), "", ""] + rvs)
            buf = io.StringIO()
            pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载 {target}_21天表.csv", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

# --- 模块 6：批量导入旧数据 ---
elif menu == "📥 批量导入旧数据":
    st.subheader("📥 批量搬运旧数据到云端")
    file = st.file_uploader("上传 CSV 文件", type="csv")
    
    if file:
        df = pd.read_csv(file)
        st.write("📄 预览预览：", df.head())
        is_pivot = any('.' in str(col) for col in df.columns) # 识别 08.01 这种报表格式
        
        if st.button("🚀 确认搬家（同步名单+课时）"):
            # 1. 先获取现有名单
            existing_s = fetch_feishu_data(TABLE_ID_STUDENTS)
            names_in_db = existing_s['姓名'].tolist() if not existing_s.empty else []
            
            bar = st.progress(0)
            count = 0
            
            # --- 定义一个简单的同步逻辑 (不使用报错的 nonlocal) ---
            if not is_pivot:
                # 格式 1：纵向清单
                total = len(df)
                for i, row in df.iterrows():
                    name = str(row['姓名'])
                    if name not in names_in_db:
                        add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"})
                        names_in_db.append(name)
                    ld = pd.to_datetime(row['学习日期']).date()
                    ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "历史导入", "课时": float(row.get('课时', 1))})
                    count += 1
                    bar.progress((i + 1) / total)
            else:
                # 格式 2：横向报表 (08.01...)
                date_cols = [c for c in df.columns if '.' in str(c)]
                total_steps = len(df) * len(date_cols)
                step = 0
                for _, row in df.iterrows():
                    name = str(row['姓名'])
                    if name not in names_in_db:
                        add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"})
                        names_in_db.append(name)
                    for d_col in date_cols:
                        step += 1
                        val = row[d_col]
                        if pd.notna(val) and float(val) > 0:
                            date_str = f"2026-{d_col.replace('.', '-')}"
                            ld = pd.to_datetime(date_str).date()
                            ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                            add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "历史导入", "课时": float(val)})
                            count += 1
                        bar.progress(step / total_steps)
            
            st.success(f"🎊 搬家成功！同步了 {count} 条课时，并自动补全了学生名册。")
