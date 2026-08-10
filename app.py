# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
# 请确保 Streamlit Secrets 已配置: FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_APP_TOKEN, TABLE_ID_STUDENTS, TABLE_ID_RECORDS
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句", "雅思", "托福", "四六级"]
WORD_ONLY_CONTENTS = ["单词", "大学单词", "雅思单词"] # 仅这些触发复习提醒
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)] # 0.5 到 10.0 小时
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# 初始化撤销记忆区
if 'undo_cache' not in st.session_state:
    st.session_state['undo_cache'] = None

# -------------------------- 2. 核心工具函数 --------------------------

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        r = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
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
    # 清理掉本地计算用的辅助字段
    forbidden_keys = ["record_id", "显示日期", "标签", "小计", "单价", "分类", "dt", "月份", "学习日期_dt"]
    clean_f = {k: v for k, v in fields.items() if k not in forbidden_keys}
    try:
        r = requests.post(url, headers=headers, json={"fields": clean_f})
        return r.json()
    except: return {"code": -1}

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.delete(url, headers=headers)
        return r.json()
    except: return {"code": -1}

def get_unit_price(content):
    """财务单价逻辑"""
    if content in ["初中阅读", "初中语法"]: return 45
    if content in ["高中阅读", "高中完型", "长难句", "雅思单词", "大学单词", "雅思", "托福", "四六级"]: return 50
    return 40 # 单词、小学阅读、旧数据

def generate_wechat_msg(name, review_date, learn_dates):
    """微信文案逻辑"""
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日单词学习内容") for d in sorted_ln])
    return f"【21天抗遗忘单词复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦[加油][加油][加油]"

# -------------------------- 3. 界面布局 --------------------------
st.set_page_config(page_title="学生管理专业版", layout="centered", page_icon="🎯")

# 手机优化样式
st.markdown("<style>.stButton>button {width: 100%; height: 3.5em; font-size: 18px !important; font-weight: bold;}</style>", unsafe_allow_html=True)

# 侧边栏：恢复功能
if st.session_state['undo_cache']:
    if st.sidebar.button("🔙 恢复上一条删除", type="primary"):
        add_feishu_record(st.session_state['undo_cache']['table'], st.session_state['undo_cache']['data'])
        st.session_state['undo_cache'] = None
        st.sidebar.success("已恢复！数据大约 5 秒后刷新")
        time.sleep(1)
        st.rerun()

menu = st.selectbox("📌 切换功能", ["📝 课时录入", "🔍 单词复习提醒", "📊 工资财务统计", "👤 学生库管理", "📜 历史明细与删除", "📄 导出21天表", "📥 导入旧数据"])

# --- 模块 1：课时录入 ---
if menu == "📝 课时录入":
    st.subheader("📝 课时快速录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        active_s = sorted(s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist())
        with st.form("lesson_f"):
            name = st.selectbox("👤 学员姓名", active_s)
            date = st.date_input("📅 学习日期", datetime.date.today())
            content = st.selectbox("📚 课程内容", LEARN_CONTENTS)
            hour = st.selectbox("⏰ 课时时长(h)", options=HOURS_OPTIONS, index=1)
            if st.form_submit_button("💾 保存并同步"):
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour})
                st.success(f"✅ 已记录！单价：{get_unit_price(content)}元")
                st.balloons()
    else: st.warning("请先在学生库中添加学员")

# --- 模块 2：单词复习提醒 ---
elif menu == "🔍 单词复习提醒":
    st.subheader("🔍 单词复习清单")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        q_date = st.date_input("选择查询日期", datetime.date.today())
        target_s = st.selectbox("指定学生查询", ["全部"] + sorted(r_df['姓名'].unique().tolist()))
        
        reminders = {}
        for _, row in r_df.iterrows():
            # 逻辑：只有单词类课程才触发提醒
            if row['学习内容'] in WORD_ONLY_CONTENTS:
                diff = (q_date - row['dt']).days + 1
                if diff in REVIEW_DAYS:
                    n = row['姓名']
                    if target_s != "全部" and n != target_s: continue
                    if n not in reminders: reminders[n] = []
                    reminders[n].append(row['dt'].strftime("%Y-%m-%d"))
        
        if reminders:
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **{name}**")
                    st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else: st.info("今日该学生无复习任务")

# --- 模块 3：工资统计 ---
elif menu == "📊 工资财务统计":
    st.subheader("💰 当月工资核算")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt_obj'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt_obj'].dt.strftime('%Y-%m')
        target_m = st.selectbox("选择月份", sorted(r_df['月份'].unique().tolist(), reverse=True))
        
        m_df = r_df[r_df['月份'] == target_m].copy()
        m_df['单价'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时'] = pd.to_numeric(m_df['课时']).fillna(0)
        m_df['小计'] = m_df['课时'] * m_df['单价']
        
        st.metric("总应发薪资", f"¥{m_df['小计'].sum():,.2f}")
        st.write("核算表：")
        # 分档统计
        def categorize(p):
            if p == 45: return "初中阅读/语法 (45元)"
            if p == 50: return "高中/雅思/托福 (50元)"
            return "单词/旧录入 (40元)"
        
        m_df['分类'] = m_df['单价'].apply(categorize)
        summary = m_df.groupby(['分类', '单价']).agg({'课时': 'sum', '小计': 'sum'}).reset_index()
        st.table(summary)

# --- 模块 4：学生管理 ---
elif menu == "👤 学生库管理":
    st.subheader("👥 学员信息库")
    with st.expander("➕ 添加新学员"):
        with st.form("add_s"):
            n = st.text_input("姓名")
            s = st.selectbox("状态", STATUS_OPTIONS)
            if st.form_submit_button("确认入库"):
                if n: add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n, "状态": s})
                st.rerun()
    
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        st.write("当前名册：")
        st.dataframe(s_df[["姓名","状态"]], use_container_width=True)
        del_target = st.selectbox("🗑️ 选择要删除的学员", ["请选择"] + s_df['姓名'].tolist())
        if del_target != "请选择" and st.checkbox("确认从云端永久删除"):
            if st.button("🔥 执行彻底删除"):
                row = s_df[s_df['姓名'] == del_target].iloc[0]
                st.session_state['undo_cache'] = {"table": TABLE_ID_STUDENTS, "data": row.to_dict()}
                delete_feishu_record(TABLE_ID_STUDENTS, row['record_id'])
                st.rerun()

# --- 模块 5：历史记录 ---
elif menu == "📜 历史明细与删除":
    st.subheader("📊 历史记录明细")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['显示日期'] = pd.to_datetime(all_r['学习日期'], unit='ms').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r[["姓名","显示日期","学习内容","课时"]], use_container_width=True)
        
        st.write("---")
        target = st.selectbox("🗑️ 选择要删除的单笔记录", ["请选择"] + (all_r['姓名']+" | "+all_r['显示日期']+" | "+all_r['学习内容']).tolist())
        if target != "请选择" and st.checkbox("确认删除该笔"):
            if st.button("🔥 执行删除记录"):
                idx = (all_r['姓名']+" | "+all_r['显示日期']+" | "+all_r['学习内容']).tolist().index(target)
                row = all_r.iloc[idx].to_dict()
                st.session_state['undo_cache'] = {"table": TABLE_ID_RECORDS, "data": row}
                delete_feishu_record(TABLE_ID_RECORDS, row['record_id'])
                st.rerun()

# --- 模块 6：导出表格 ---
elif menu == "📄 导出21天表":
    st.subheader("📄 单人表导出")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt_obj'] = pd.to_datetime(r_all['学习日期'], unit='ms').dt.date
        target = st.selectbox("选择学生", sorted(r_all['姓名'].unique().tolist()))
        if st.button("生成 21 天 Excel 可用 CSV"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt_obj")
            output = [["21天抗遗忘周期表","",""], [f"姓名：{target}","",""], ["日期","复习","新学","第1天","第2天","第3天","第5天","第7天","第9+天","第12天","第14天","第17天","第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt_obj']
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"),"",""] + rvs)
            buf = io.StringIO()
            pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载 {target} 的表格", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

# --- 模块 7：批量导入 ---
elif menu == "📥 导入旧数据":
    st.subheader("📥 批量导入 (智能识别)")
    f = st.file_uploader("上传 CSV", type="csv")
    if f:
        df = pd.read_csv(f)
        st.dataframe(df.head())
        if st.button("🚀 开始同步名单与课时"):
            s_now = fetch_feishu_data(TABLE_ID_STUDENTS)
            names_in = s_now['姓名'].tolist() if not s_now.empty else []
            bar = st.progress(0)
            is_pivot = any('.' in str(c) for c in df.columns) # 识别报表格式
            
            count = 0
            if not is_pivot:
                for i, row in df.iterrows():
                    name = str(row['姓名'])
                    if name not in names_in:
                        add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"})
                        names_in.append(name)
                    ld = pd.to_datetime(row['学习日期']).date()
                    ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "导入", "课时": float(row.get('课时', 1))})
                    count += 1
                    bar.progress((i+1)/len(df))
            else:
                date_cols = [c for c in df.columns if '.' in str(c)]
                for i, row in df.iterrows():
                    name = str(row['姓名'])
                    if name not in names_in:
                        add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"})
                        names_in.append(name)
                    for d_col in date_cols:
                        val = row[d_col]
                        if pd.notna(val) and float(val) > 0:
                            date_str = f"2026-{d_col.replace('.', '-')}"
                            ld = pd.to_datetime(date_str).date()
                            ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                            add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "旧数据", "课时": float(val)})
                            count += 1
                    bar.progress((i+1)/len(df))
            st.success(f"🎊 完成！同步了 {count} 条记录")
